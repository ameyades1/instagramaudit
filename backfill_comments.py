"""
Backfill comments into the Comments sheet.

Reads posts from the Post Details sheet and fetches all comments via Apify,
deduplicating by comment ID to avoid duplicate rows in the sheet.

Usage:
    # Full backfill (all posts from a given date onward)
    APIFY_API_KEY=... GOOGLE_SHEET_ID=... GOOGLE_CREDENTIALS_JSON=... \
        python backfill_comments.py --posts-since-date 2026-03-01

    # Daily incremental run (capture comments on recent posts)
    python backfill_comments.py --posts-since-date 2026-05-06
"""

import argparse
import base64
import json
import os
from datetime import datetime, timezone, timedelta

from apify_client import ApifyClient
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
IST = timezone(timedelta(hours=5, minutes=30))


def get_sheets_client():
    raw = base64.b64decode(os.environ["GOOGLE_CREDENTIALS_JSON"])
    info = json.loads(raw)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def get_logged_comment_ids(sheets, sheet_id):
    try:
        result = (
            sheets.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range="Comments!G:G")
            .execute()
        )
        rows = result.get("values", [])
        return {row[0] for row in rows[1:] if row}
    except Exception as e:
        print(f"Could not read Comments tab: {e}")
        return set()


def get_post_details(sheets, sheet_id, posts_since_date=None):
    """Read posts from Post Details sheet, optionally filtering by date."""
    result = (
        sheets.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range="Post Details!A:D")
        .execute()
    )
    rows = result.get("values", [])
    posts = []
    for row in rows[1:]:  # Skip header
        if len(row) >= 4 and row[2]:  # Need post_url and post_id
            post_date_str = row[0]
            try:
                post_date = datetime.strptime(post_date_str, "%Y-%m-%d").date()
            except (ValueError, IndexError):
                continue

            # Filter by posts_since_date if provided
            if posts_since_date and post_date < posts_since_date:
                continue

            posts.append({
                "date": post_date_str,
                "url": row[2],
                "id": row[3],
            })
    return posts


def fetch_comments_for_posts(client, post_urls):
    """Fetch all comments for a list of post URLs using instagram-comment-scraper."""
    if not post_urls:
        return {}

    print(f"Fetching comments for {len(post_urls)} posts (unlimited per post)...")
    try:
        run = client.actor("apify/instagram-comment-scraper").call(
            run_input={
                "directUrls": post_urls,
                # No resultsLimit — fetch ALL comments per post
            }
        )
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    except Exception as e:
        print(f"Comments scraper error: {e}")
        return {}

    # Group comments by post URL (more reliable than extracting shortcode)
    comments_by_url = {}
    for item in items:
        # Try multiple URL field names from Apify
        url = item.get("url") or item.get("postUrl") or item.get("post_url") or ""

        if not url or "/p/" not in url:
            continue

        if url not in comments_by_url:
            comments_by_url[url] = []

        comments_by_url[url].append(item)

    return comments_by_url


def append_comments(sheets, sheet_id, rows):
    """Append comment rows to Comments sheet."""
    if not rows:
        return
    sheets.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range="Comments!A:G",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()


def main():
    parser = argparse.ArgumentParser(
        description="Backfill comments into the Comments sheet."
    )
    parser.add_argument(
        "--posts-since-date",
        type=str,
        default=None,
        help="Only fetch comments for posts published on or after this date (YYYY-MM-DD). "
             "If omitted, fetches for all posts.",
    )
    args = parser.parse_args()

    posts_since_date = None
    if args.posts_since_date:
        try:
            posts_since_date = datetime.strptime(args.posts_since_date, "%Y-%m-%d").date()
            print(f"Filtering posts from {posts_since_date} onward")
        except ValueError:
            print(f"Error: Invalid date format '{args.posts_since_date}'. Use YYYY-MM-DD.")
            return

    sheet_id = os.environ["GOOGLE_SHEET_ID"]
    handle = os.environ["INSTAGRAM_HANDLE"]

    sheets = get_sheets_client()
    client = ApifyClient(os.environ["APIFY_API_KEY"])

    # Get already-logged comment IDs (for deduplication)
    logged_comment_ids = get_logged_comment_ids(sheets, sheet_id)
    print(f"Already logged: {len(logged_comment_ids)} comment IDs")

    # Get posts from the sheet, optionally filtered by date
    posts_in_sheet = get_post_details(sheets, sheet_id, posts_since_date)
    print(f"Found {len(posts_in_sheet)} posts to process")

    # Extract post URLs (skip stories)
    post_urls = [p["url"] for p in posts_in_sheet if "/stories/" not in p["url"]]
    print(f"Fetching comments for {len(post_urls)} posts (excluding stories)...")

    # Fetch comments for all posts via instagram-comment-scraper
    comments_by_shortcode = fetch_comments_for_posts(client, post_urls)
    print(f"Got comments for {len(comments_by_shortcode)} posts")

    # Extract new comments (only those not already in the sheet)
    comment_rows = []
    duplicate_count = 0

    for post_detail in posts_in_sheet:
        post_id = post_detail["id"]
        post_url = post_detail["url"]

        # Skip stories
        if "/stories/" in post_url:
            continue

        # Look up comments by post URL (more reliable than shortcode)
        comments = comments_by_url.get(post_url, [])
        print(f"Post {post_id}: {len(comments)} comments from scraper")

        for comment in comments:
            comment_id = comment.get("id", "")
            if comment_id in logged_comment_ids:
                duplicate_count += 1
                continue

            ts = datetime.fromisoformat(comment["timestamp"].replace("Z", "+00:00"))
            comment_ist = ts.astimezone(IST)

            comment_rows.append([
                post_id,
                post_url,
                comment_ist.strftime("%Y-%m-%d"),
                comment_ist.strftime("%H:%M"),
                comment.get("ownerUsername", ""),
                comment.get("text", ""),
                comment_id,
            ])

    print(f"Skipped {duplicate_count} duplicate comments (already in sheet)")

    if comment_rows:
        append_comments(sheets, sheet_id, comment_rows)
        print(f"Appended {len(comment_rows)} new comments.")
    else:
        print("No new comments to add.")


if __name__ == "__main__":
    main()
