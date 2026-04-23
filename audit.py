import base64
import json
import os
import tempfile
from datetime import datetime, timezone, timedelta

import requests
from apify_client import ApifyClient
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

IST = timezone(timedelta(hours=5, minutes=30))
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_google_clients():
    raw = base64.b64decode(os.environ["GOOGLE_CREDENTIALS_JSON"])
    info = json.loads(raw)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    sheets = build("sheets", "v4", credentials=creds)
    drive = build("drive", "v3", credentials=creds)
    return sheets, drive


def get_logged_shortcodes(sheets, sheet_id):
    result = (
        sheets.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range="D:D")
        .execute()
    )
    rows = result.get("values", [])
    return {row[0] for row in rows[1:] if row}


def upload_to_drive(drive, folder_id, file_path, filename):
    metadata = {"name": filename, "parents": [folder_id]}
    media = MediaFileUpload(file_path, resumable=False)
    file = (
        drive.files()
        .create(body=metadata, media_body=media, fields="id,webViewLink")
        .execute()
    )
    drive.permissions().create(
        fileId=file["id"],
        body={"type": "anyone", "role": "reader"},
    ).execute()
    return file["webViewLink"]


def append_row(sheets, sheet_id, row):
    sheets.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range="A:E",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()


def main():
    handle = os.environ["INSTAGRAM_HANDLE"]
    sheet_id = os.environ["GOOGLE_SHEET_ID"]
    folder_id = os.environ["GOOGLE_DRIVE_FOLDER_ID"]

    sheets, drive = get_google_clients()
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

    with tempfile.TemporaryDirectory() as tmpdir:
        for post in new_posts:
            shortcode = post["shortCode"]
            filename = f"{shortcode}.jpg"
            file_path = os.path.join(tmpdir, filename)

            response = requests.get(post["displayUrl"], timeout=30)
            response.raise_for_status()
            with open(file_path, "wb") as f:
                f.write(response.content)

            drive_link = upload_to_drive(drive, folder_id, file_path, filename)

            ts = datetime.fromisoformat(post["timestamp"].replace("Z", "+00:00"))
            post_ist = ts.astimezone(IST)

            row = [
                post_ist.strftime("%Y-%m-%d"),
                post_ist.strftime("%H:%M"),
                f"https://www.instagram.com/p/{shortcode}/",
                shortcode,
                drive_link,
            ]
            append_row(sheets, sheet_id, row)
            print(f"Logged: {shortcode} ({row[0]} {row[1]})")


if __name__ == "__main__":
    main()
