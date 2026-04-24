"""
One-off script: backfill captions into column H of the Post Details sheet.

Reads all existing rows, fetches captions for non-story posts via Apify
instagram-scraper (supports directUrls), and writes captions into column H.

Run once:
    APIFY_API_KEY=... GOOGLE_SHEET_ID=... GOOGLE_CREDENTIALS_JSON=... \
        python backfill_captions.py
"""

import base64
import json
import os

from apify_client import ApifyClient
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_sheets_client():
    raw = base64.b64decode(os.environ["GOOGLE_CREDENTIALS_JSON"])
    info = json.loads(raw)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def fetch_captions(client, post_urls):
    """Fetch captions for a list of post URLs via apify/instagram-scraper."""
    run = client.actor("apify/instagram-scraper").call(
        run_input={
            "directUrls": post_urls,
            "resultsType": "posts",
            "resultsLimit": len(post_urls),
        }
    )
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    # Build a map of shortcode -> caption
    caption_map = {}
    for item in items:
        shortcode = item.get("shortCode") or item.get("shortcode", "")
        caption = (item.get("caption") or "").strip()
        if shortcode:
            caption_map[shortcode] = caption
    return caption_map


def main():
    sheet_id = os.environ["GOOGLE_SHEET_ID"]
    sheets = get_sheets_client()
    client = ApifyClient(os.environ["APIFY_API_KEY"])

    # Read all rows from Post Details (cols A–H)
    result = (
        sheets.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range="Post Details!A:H")
        .execute()
    )
    rows = result.get("values", [])
    if not rows:
        print("Sheet is empty.")
        return

    # Row 0 is the header; data starts at row index 1 (sheet row 2)
    header = rows[0]
    data_rows = rows[1:]

    # Collect posts that need a caption (column H is absent or empty)
    # Columns: A=date, B=time, C=url, D=post_id, E=image, F=type, G=empty, H=caption
    to_fetch = []  # list of (sheet_row_number, post_id, post_url)
    for i, row in enumerate(data_rows):
        sheet_row = i + 2  # 1-indexed, header is row 1
        post_url = row[2] if len(row) > 2 else ""
        post_id  = row[3] if len(row) > 3 else ""
        caption  = row[7] if len(row) > 7 else ""

        # Skip stories (they have no caption) and rows that already have one
        if not post_url or "/stories/" in post_url:
            continue
        if caption:
            print(f"Row {sheet_row} ({post_id}): already has caption, skipping.")
            continue

        to_fetch.append((sheet_row, post_id, post_url))

    if not to_fetch:
        print("All rows already have captions.")
        return

    print(f"Fetching captions for {len(to_fetch)} posts...")

    # Fetch in one batch (Apify handles multiple directUrls)
    post_urls = [url for _, _, url in to_fetch]
    caption_map = fetch_captions(client, post_urls)

    # Build batchUpdate data: list of {range, values} for each row
    updates = []
    for sheet_row, post_id, post_url in to_fetch:
        # Derive shortcode from URL: .../p/<shortcode>/
        parts = post_url.rstrip("/").split("/")
        shortcode = parts[-1] if parts else post_id

        caption = caption_map.get(shortcode, "")
        print(f"Row {sheet_row} ({shortcode}): {repr(caption[:60])}")
        updates.append({
            "range": f"Post Details!H{sheet_row}",
            "values": [[caption]],
        })

    if not updates:
        print("No captions found from Apify.")
        return

    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=sheet_id,
        body={
            "valueInputOption": "RAW",
            "data": updates,
        },
    ).execute()

    print(f"Done. Updated {len(updates)} rows.")


if __name__ == "__main__":
    main()
