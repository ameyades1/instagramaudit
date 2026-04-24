import base64
import json
import os
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

DATA_JSON  = Path("docs/data.json")
IMAGES_DIR = Path("docs/images")

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
    "Story":   "Story",
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


def download_image(url, dest_path):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(resp.read())
        return True
    except Exception as e:
        print(f"Image download failed ({dest_path.name}): {e}")
        return False


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


def fetch_stories(client, handle):
    try:
        run = client.actor("apify/instagram-story-scraper").call(
            run_input={"usernames": [handle]}
        )
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        normalized = []
        for item in items:
            story_id = str(item.get("id", ""))
            if not story_id:
                continue
            normalized.append({
                "shortCode": f"story_{story_id}",
                "displayUrl": item.get("displayUrl", item.get("thumbnailUrl", "")),
                "timestamp": item.get("takenAtTimestamp",
                             item.get("timestamp", "")),
                "dimensions": item.get("dimensions", {}),
                "postType": "Story",
            })
        return normalized
    except Exception as e:
        print(f"Stories fetch skipped: {e}")
        return []


def main():
    handle = os.environ["INSTAGRAM_HANDLE"]
    sheet_id = os.environ["GOOGLE_SHEET_ID"]

    sheets = get_sheets_client()
    logged = get_logged_shortcodes(sheets, sheet_id)

    client = ApifyClient(os.environ["APIFY_API_KEY"])

    # combine grid posts + reels + stories, deduplicate by shortcode/id
    all_posts = {p["shortCode"]: p for p in fetch_grid_posts(client, handle)}
    for p in fetch_reels(client, handle):
        if p["shortCode"] and p["shortCode"] not in all_posts:
            all_posts[p["shortCode"]] = p
    for p in fetch_stories(client, handle):
        if p["shortCode"] and p["shortCode"] not in all_posts:
            all_posts[p["shortCode"]] = p

    new_posts = [p for p in all_posts.values() if p["shortCode"] not in logged]

    if not new_posts:
        print("No new posts found.")
        if DATA_JSON.exists():
            with open(DATA_JSON) as f:
                data = json.load(f)
        else:
            data = {"posts": []}
            DATA_JSON.parent.mkdir(parents=True, exist_ok=True)
        data["updated"] = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
        with open(DATA_JSON, "w") as f:
            json.dump(data, f, indent=2)
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

        if post_type == "Story":
            story_id = shortcode.replace("story_", "")
            post_url = f"https://www.instagram.com/stories/{handle}/{story_id}/"
            display_id = story_id
        else:
            post_url = f"https://www.instagram.com/p/{shortcode}/"
            display_id = shortcode

        date_str = post_ist.strftime("%Y-%m-%d")
        cdn_url  = post.get("displayUrl", "")
        img_filename = f"{date_str}-{display_id}.jpg"
        saved = download_image(cdn_url, IMAGES_DIR / img_filename)
        local_url = f"images/{img_filename}" if saved else cdn_url

        row = [
            date_str,
            post_ist.strftime("%H:%M"),
            post_url,
            display_id,
            f'=IMAGE("{cdn_url}", 4, {img_h}, {img_w})',
            post_type,
        ]
        append_row(sheets, sheet_id, row, img_h, img_w)
        update_data_json({
            "date":     row[0],
            "time":     row[1],
            "url":      post_url,
            "id":       display_id,
            "imageUrl": local_url,
            "type":     post_type,
        })
        print(f"Logged: {shortcode} ({row[0]} {row[1]}) [{post_type}]")


def update_data_json(new_entry):
    if DATA_JSON.exists():
        with open(DATA_JSON) as f:
            data = json.load(f)
    else:
        data = {"posts": []}

    data["posts"].insert(0, new_entry)
    data["posts"] = data["posts"][:20]
    data["updated"] = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")

    DATA_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_JSON, "w") as f:
        json.dump(data, f, indent=2)


if __name__ == "__main__":
    main()
