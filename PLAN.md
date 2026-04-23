# Instagram PR Agency Audit Automation

## Context
Automate auditing of a PR agency's Instagram account on a daily schedule, logging each new post's metadata (date, time, URL, post ID) and downloading post media into a Google Sheet. Account is public-only — no official Instagram API credentials available. Using open-source scrapers to avoid paid third-party services.

---

## Feasibility Assessment

**Challenge**: Instagram has no official public API for reading another account's posts. Unauthenticated scraping is fragile — Instagram actively rate-limits and blocks bots.

**Recommended scraper**: **Instaloader** — actively maintained Python library, returns full metadata, most reliable of the open-source options. Requires a throwaway/burner Instagram account (credentials stored as GitHub secrets). Daily schedule keeps request volume low and avoids blocks.

**Fallback**: **gallery-dl** with a stored session cookie — no dedicated account needed, but breaks more often when Instagram changes their internals.

| Approach | Login required | Reliability | Cost |
|---|---|---|---|
| **Instaloader** (recommended) | Burner IG account | High | Free |
| **gallery-dl + cookies** | Session cookie | Medium | Free |
| Ask PR agency for Graph API | Their account grants access | Highest | Free |

---

## Architecture

```
GitHub Actions cron (once daily, e.g. 09:00 UTC)
        │
        ▼
  audit.py (Python 3.12)
        │
        ├─► Instaloader → authenticates with burner account
        │       └─ fetches recent posts from target profile
        │
        ├─► Google Sheets API  (read logged shortcodes → detect new posts)
        │
        └─► For each new post:
                ├─ Download media (instaloader saves image/video thumbnail locally)
                ├─ Upload file to Google Drive folder
                └─ Append row to Google Sheet
```

---

## Files to Create

```
instagramaudit/
├── .github/
│   └── workflows/
│       └── instagram-audit.yml      # daily cron + secrets wiring
├── audit.py                          # main logic
└── requirements.txt
```

---

## File: `.github/workflows/instagram-audit.yml`

```yaml
name: Instagram Audit
on:
  schedule:
    - cron: '0 9 * * *'   # 09:00 UTC daily
  workflow_dispatch:        # manual trigger for testing

jobs:
  audit:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: python audit.py
        env:
          IG_USERNAME:              ${{ secrets.IG_USERNAME }}
          IG_PASSWORD:              ${{ secrets.IG_PASSWORD }}
          INSTAGRAM_HANDLE:         ${{ secrets.INSTAGRAM_HANDLE }}
          GOOGLE_CREDENTIALS_JSON:  ${{ secrets.GOOGLE_CREDENTIALS_JSON }}
          GOOGLE_SHEET_ID:          ${{ secrets.GOOGLE_SHEET_ID }}
          GOOGLE_DRIVE_FOLDER_ID:   ${{ secrets.GOOGLE_DRIVE_FOLDER_ID }}
```

---

## File: `audit.py` — Logic Outline

```
1. Load env vars
2. Auth with Instaloader using burner IG account (IG_USERNAME / IG_PASSWORD)
3. Fetch recent posts for INSTAGRAM_HANDLE
   - instaloader.Profile.from_username(L.context, handle).get_posts()
   - Limit to posts from last 48 hours (safety buffer over daily run)
4. Init Google Sheets client from service account JSON
5. Read column D (shortcodes) from the Sheet → build set of already-logged IDs
6. For each post NOT in logged set:
   a. Download media: instaloader saves to temp dir (post.url for image, post.video_url for video)
      → for videos, use the thumbnail (post.url) to keep file sizes small
   b. Upload file to Google Drive folder via Drive API → get webViewLink
   c. Build row:
        date      = post.date_utc.strftime("%Y-%m-%d")
        time      = post.date_utc.strftime("%H:%M")
        post_url  = f"https://www.instagram.com/p/{post.shortcode}/"
        post_id   = post.shortcode
        media     = Drive webViewLink
   d. Append row to Sheet
7. Clean up temp dir
```

---

## Google Sheet Structure

| A: Date | B: Time (UTC) | C: Post URL | D: Post ID (shortcode) | E: Media (Drive link) |
|---|---|---|---|---|
| 2026-04-23 | 14:32 | https://instagram.com/p/ABC123/ | ABC123 | https://drive.google.com/... |

Column D is the dedup key — no separate state file needed; the Sheet itself tracks what's been logged.

---

## Requirements

```
instaloader==4.13
google-auth==2.29.0
google-api-python-client==2.126.0
requests==2.32.3
```

---

## Required Secrets (GitHub Actions → Settings → Secrets → Actions)

| Secret | Value |
|---|---|
| `IG_USERNAME` | Username of your burner/throwaway Instagram account |
| `IG_PASSWORD` | Password of that burner account |
| `INSTAGRAM_HANDLE` | The PR agency's IG username (no @) |
| `GOOGLE_CREDENTIALS_JSON` | GCP service account key JSON, base64-encoded |
| `GOOGLE_SHEET_ID` | From Sheet URL: `docs.google.com/spreadsheets/d/<ID>` |
| `GOOGLE_DRIVE_FOLDER_ID` | From Drive folder URL: `drive.google.com/drive/folders/<ID>` |

---

## One-Time Setup Checklist

### Burner Instagram Account
1. Create a new Instagram account on a personal device (use a throwaway email)
2. Log in manually at least once to complete any verification prompts
3. Do NOT use your main account — repeated programmatic logins can trigger 2FA or suspension

### Google Cloud
1. Create GCP project
2. Enable: **Google Sheets API** + **Google Drive API**
3. Create a Service Account → generate JSON key
4. Base64-encode the JSON: `base64 -w 0 service-account.json`
5. Share the Google Sheet **and** Drive folder with the service account email as Editor

### GitHub
1. Add all 6 secrets under Settings → Secrets and variables → Actions

---

## Verification

1. Trigger manually via "Run workflow" in GitHub Actions
2. Check the Actions log — confirm Instaloader authenticates and fetches posts
3. Open the Google Sheet — verify rows appear with correct date/time/URL/ID
4. Click a Drive link in column E — verify the correct post image opens
5. Run again — confirm no duplicate rows are added for already-logged posts

---

## Limitations & Known Risks

- **Instagram rate limiting**: Running daily (not every 30 min) keeps this low. If you see `429` or login challenges in logs, add a delay between posts in the script.
- **Burner account risk**: Instagram may flag programmatic logins. If the account gets locked, create a new one. Using a 2FA-free account is easiest.
- **2-factor auth**: Do not enable 2FA on the burner account — it breaks automated login.
- **Instaloader session file**: Instaloader can save a session file to avoid repeated password logins. This can be serialized and stored as a secret, but for simplicity the initial plan will re-authenticate each run.
- **Better alternative**: Ask the PR agency to grant Graph API access via their Instagram Business account — eliminates all scraping risk and is the cleanest long-term solution.
