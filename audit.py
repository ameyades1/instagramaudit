import base64
import json
import os
from datetime import datetime, timezone, timedelta

from apify_client import ApifyClient
from google.oauth2 import service_account
from googleapiclient.discovery import build

IST = timezone(timedelta(hours=5, minutes=30))
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

TYPE_MAP = {
    "Image":   "Image",
    "Video":   "Video",
    "Sidecar": "Carousel",
    "Reel":    "Reel",
}


def get_sheets_client():
    raw = base64.b64decode(os.environ["GOOGLE_CREDENTIALS_JSON"])
    info = json.loads(raw)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def get_logged_shortcodes(sheets, sheet_id):
    result = (
        sheets.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range="D:D")
        .execute()
    )
    rows = result.get("values", [])
    return {row[0] for row in rows[1:] if row}


MAX_PX = 500


def scale_dimensions(width, height, max_px=MAX_PX):
    scale = min(max_px / width, max_px / height)
    return int(width * scale), int(height * scale)


def append_row(sheets, sheet_id, row, row_height, col_width):
    response = sheets.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range="A:F",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()

    updated_range = response["updates"]["updatedRange"]
    row_index = int(updated_range.split("!")[1].split(":")[0].lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")) - 1
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [
            {"updateDimensionProperties": {
                "range": {"sheetId": 0, "dimension": "ROWS",
                          "startIndex": row_index, "endIndex": row_index + 1},
                "properties": {"pixelSize": row_height},
                "fields": "pixelSize",
            }},
            {"updateDimensionProperties": {
                "range": {"sheetId": 0, "dimension": "COLUMNS",
                          "startIndex": 4, "endIndex": 5},
                "properties": {"pixelSize": col_width},
                "fields": "pixelSize",
            }},
        ]},
    ).execute()


def fetch_grid_posts(client, handle):
    run = client.actor("apify/instagram-profile-scraper").call(
        run_input={"usernames": [handle]}
    )
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    if not items:
        return []
    posts = items[0].get("latestPosts", [])
    for p in posts:
        p.setdefault("postType", p.get("type", "Image"))
    return posts


def fetch_reels(client, handle):
    try:
        run = client.actor("apify/instagram-reel-scraper").call(
            run_input={"username": handle, "resultsLimit": 12}
        )
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        for item in items:
            item.setdefault("postType", "Reel")
            item.setdefault("shortCode", item.get("shortcode", ""))
            item.setdefault("displayUrl", item.get("thumbnailUrl", item.get("displayUrl", "")))
            item.setdefault("timestamp", item.get("timestamp", ""))
            item.setdefault("dimensions", item.get("dimensions", {}))
        return items
    except Exception as e:
        print(f"Reels fetch skipped: {e}")
        return []


def main():
    handle = os.environ["INSTAGRAM_HANDLE"]
    sheet_id = os.environ["GOOGLE_SHEET_ID"]

    sheets = get_sheets_client()
    logged = get_logged_shortcodes(sheets, sheet_id)

    client = ApifyClient(os.environ["APIFY_API_KEY"])

    # combine grid posts + reels, deduplicate by shortcode
    all_posts = {p["shortCode"]: p for p in fetch_grid_posts(client, handle)}
    for p in fetch_reels(client, handle):
        if p["shortCode"] and p["shortCode"] not in all_posts:
            all_posts[p["shortCode"]] = p

    new_posts = [p for p in all_posts.values() if p["shortCode"] not in logged]

    if not new_posts:
        print("No new posts found.")
        return

    new_posts.sort(key=lambda p: p["timestamp"])

    for post in new_posts:
        shortcode = post["shortCode"]
        ts = datetime.fromisoformat(post["timestamp"].replace("Z", "+00:00"))
        post_ist = ts.astimezone(IST)

        dims = post.get("dimensions", {})
        orig_w = dims.get("width") or 1080
        orig_h = dims.get("height") or 1080
        img_w, img_h = scale_dimensions(orig_w, orig_h)

        post_type = TYPE_MAP.get(post.get("postType", ""), post.get("postType", "Image"))

        row = [
            post_ist.strftime("%Y-%m-%d"),
            post_ist.strftime("%H:%M"),
            f"https://www.instagram.com/p/{shortcode}/",
            shortcode,
            f'=IMAGE("{post["displayUrl"]}", 4, {img_h}, {img_w})',
            post_type,
        ]
        append_row(sheets, sheet_id, row, img_h, img_w)
        print(f"Logged: {shortcode} ({row[0]} {row[1]}) [{post_type}]")


if __name__ == "__main__":
    main()
