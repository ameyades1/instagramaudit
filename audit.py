import base64
import json
import os
import tempfile
from datetime import datetime, timezone, timedelta

import instaloader
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

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
    # skip header row
    return {row[0] for row in rows[1:] if row}


def upload_to_drive(drive, folder_id, file_path, filename):
    metadata = {"name": filename, "parents": [folder_id]}
    media = MediaFileUpload(file_path, resumable=False)
    file = (
        drive.files()
        .create(body=metadata, media_body=media, fields="id,webViewLink")
        .execute()
    )
    # make the file readable by anyone with the link
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
    ig_username = os.environ["IG_USERNAME"]
    handle = os.environ["INSTAGRAM_HANDLE"]
    sheet_id = os.environ["GOOGLE_SHEET_ID"]
    folder_id = os.environ["GOOGLE_DRIVE_FOLDER_ID"]

    sheets, drive = get_google_clients()
    logged = get_logged_shortcodes(sheets, sheet_id)

    L = instaloader.Instaloader(download_pictures=False, download_videos=False,
                                 download_video_thumbnails=False, download_geotags=False,
                                 download_comments=False, save_metadata=False,
                                 post_metadata_txt_pattern="")

    # write session file from secret and load it (avoids checkpoint errors from raw password login)
    session_b64 = os.environ["IG_SESSION"]
    session_path = f"/tmp/session-{ig_username}"
    with open(session_path, "wb") as f:
        f.write(base64.b64decode(session_b64))
    L.load_session_from_file(ig_username, session_path)

    profile = instaloader.Profile.from_username(L.context, handle)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

    new_posts = []
    for post in profile.get_posts():
        if post.date_utc < cutoff:
            break
        if post.shortcode not in logged:
            new_posts.append(post)

    if not new_posts:
        print("No new posts found.")
        return

    # process oldest first so the sheet is in chronological order
    new_posts.reverse()

    with tempfile.TemporaryDirectory() as tmpdir:
        for post in new_posts:
            media_url = post.url  # thumbnail for both images and videos
            filename = f"{post.shortcode}.jpg"
            file_path = os.path.join(tmpdir, filename)

            response = requests.get(media_url, timeout=30)
            response.raise_for_status()
            with open(file_path, "wb") as f:
                f.write(response.content)

            drive_link = upload_to_drive(drive, folder_id, file_path, filename)

            row = [
                post.date_utc.strftime("%Y-%m-%d"),
                post.date_utc.strftime("%H:%M"),
                f"https://www.instagram.com/p/{post.shortcode}/",
                post.shortcode,
                drive_link,
            ]
            append_row(sheets, sheet_id, row)
            print(f"Logged: {post.shortcode} ({row[0]} {row[1]})")


if __name__ == "__main__":
    main()
