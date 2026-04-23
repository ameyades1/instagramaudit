import base64
import json
import os
from datetime import datetime, timezone, timedelta

from apify_client import ApifyClient
from google.oauth2 import service_account
from googleapiclient.discovery import build

IST = timezone(timedelta(hours=5, minutes=30))
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


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


IMAGE_SIZE = 150


def append_row(sheets, sheet_id, row):
    response = sheets.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range="A:E",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()

    # set row height to match image size
    updated_range = response["updates"]["updatedRange"]
    row_index = int(updated_range.split("!")[1].split(":")[0].lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")) - 1
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [{"updateDimensionProperties": {
            "range": {"sheetId": 0, "dimension": "ROWS",
                      "startIndex": row_index, "endIndex": row_index + 1},
            "properties": {"pixelSize": IMAGE_SIZE},
            "fields": "pixelSize",
        }}]},
    ).execute()


def main():
    handle = os.environ["INSTAGRAM_HANDLE"]
    sheet_id = os.environ["GOOGLE_SHEET_ID"]

    sheets = get_sheets_client()
    logged = get_logged_shortcodes(sheets, sheet_id)

    client = ApifyClient(os.environ["APIFY_API_KEY"])
    run = client.actor("apify/instagram-profile-scraper").call(
        run_input={"usernames": [handle]}
    )

    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    if not items:
        print("No data returned from Apify.")
        return

    posts = items[0].get("latestPosts", [])
    new_posts = [p for p in posts if p["shortCode"] not in logged]

    if not new_posts:
        print("No new posts found.")
        return

    new_posts.sort(key=lambda p: p["timestamp"])

    for post in new_posts:
        shortcode = post["shortCode"]
        ts = datetime.fromisoformat(post["timestamp"].replace("Z", "+00:00"))
        post_ist = ts.astimezone(IST)

        row = [
            post_ist.strftime("%Y-%m-%d"),
            post_ist.strftime("%H:%M"),
            f"https://www.instagram.com/p/{shortcode}/",
            shortcode,
            f'=IMAGE("{post["displayUrl"]}", 4, {IMAGE_SIZE}, {IMAGE_SIZE})',
        ]
        append_row(sheets, sheet_id, row)
        print(f"Logged: {shortcode} ({row[0]} {row[1]})")


if __name__ == "__main__":
    main()
