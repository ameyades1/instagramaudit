"""
One-off script: backfill comments into the Comments sheet.

Reads all grid posts from the Post Details sheet, extracts latestComments
(3-5 most recent per post), and appends new ones to the Comments sheet
(deduplicating by comment ID).

Run once:
    APIFY_API_KEY=... GOOGLE_SHEET_ID=... GOOGLE_CREDENTIALS_JSON=... \
        python backfill_comments.py
"""

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


def get_post_details(sheets, sheet_id):
    """Read all posts from Post Details sheet."""
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
            posts.append({
                "date": row[0],
                "url": row[2],
                "id": row[3],
            })
    return posts


def fetch_comments_for_posts(client, post_urls):
    """Fetch comments for a list of post URLs using instagram-comment-scraper."""
    if not post_urls:
        return {}

    print(f"Fetching comments for {len(post_urls)} posts...")
    run = client.actor("apify/instagram-comment-scraper").call(
        run_input={
            "directUrls": post_urls,
            "resultsLimit": 100,  # Get up to 100 comments per post
        }
    )
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())

    # Group comments by post shortcode
    comments_by_post = {}
    for item in items:
        # Extract shortcode from URL if available, or use the id
        url = item.get("url", "")
        if "/p/" in url:
            shortcode = url.split("/p/")[1].split("/")[0]
        else:
            shortcode = None

        if not shortcode:
            continue

        if shortcode not in comments_by_post:
            comments_by_post[shortcode] = []

        comments_by_post[shortcode].append(item)

    return comments_by_post


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
    sheet_id = os.environ["GOOGLE_SHEET_ID"]
    handle = os.environ["INSTAGRAM_HANDLE"]

    sheets = get_sheets_client()
    client = ApifyClient(os.environ["APIFY_API_KEY"])

    # Get already-logged comment IDs
    logged_comment_ids = get_logged_comment_ids(sheets, sheet_id)
    print(f"Already logged: {len(logged_comment_ids)} comment IDs")

    # Get all posts from the sheet
    posts_in_sheet = get_post_details(sheets, sheet_id)
    print(f"Found {len(posts_in_sheet)} posts in Post Details sheet")

    # Extract post URLs (skip stories)
    post_urls = [p["url"] for p in posts_in_sheet if "/stories/" not in p["url"]]
    print(f"Fetching comments for {len(post_urls)} posts (excluding stories)...")

    # Fetch comments for all posts via instagram-comments-scraper
    comments_by_shortcode = fetch_comments_for_posts(client, post_urls)
    print(f"Got comments for {len(comments_by_shortcode)} posts")

    # Extract new comments
    comment_rows = []
    for post_detail in posts_in_sheet:
        post_id = post_detail["id"]
        post_url = post_detail["url"]

        # Skip stories
        if "/stories/" in post_url:
            continue

        comments = comments_by_shortcode.get(post_id, [])
        print(f"Post {post_id}: {len(comments)} comments from scraper")

        for comment in comments:
            comment_id = comment.get("id", "")
            if comment_id in logged_comment_ids:
                print(f"  Comment {comment_id}: already logged (skipped)")
                continue

            ts = datetime.fromisoformat(comment["timestamp"].replace("Z", "+00:00"))
            comment_ist = ts.astimezone(IST)

            print(f"  Comment {comment_id}: new, will add")
            comment_rows.append([
                post_id,
                post_url,
                comment_ist.strftime("%Y-%m-%d"),
                comment_ist.strftime("%H:%M"),
                comment.get("ownerUsername", ""),
                comment.get("text", ""),
                comment_id,
            ])

    if comment_rows:
        append_comments(sheets, sheet_id, comment_rows)
        print(f"Appended {len(comment_rows)} new comments.")
    else:
        print("No new comments found.")


if __name__ == "__main__":
    main()
