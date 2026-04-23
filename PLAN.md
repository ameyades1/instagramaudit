# Instagram PR Agency Audit — Implementation Plan

Track a PR agency's public Instagram account daily. Log each new post (date, time, URL, post ID, media image) into a Google Sheet, with images stored in Google Drive.

**Stack:** Python · Instaloader · Google Sheets API · Google Drive API · GitHub Actions (free)  
**Cost:** $0/month

---

## Legend
- `[CODE]` — Claude writes the code / files
- `[YOU]` — You do this manually (account setup, credentials, etc.)
- `[ ]` — not started · `[x]` — done

---

## Phase 1 — Code

- [ ] `[CODE]` **Step 1** — Create project structure  
  Create `.github/workflows/` directory and placeholder files

- [ ] `[CODE]` **Step 2** — Create `requirements.txt`  
  Pin versions: `instaloader`, `google-auth`, `google-api-python-client`, `requests`

- [ ] `[CODE]` **Step 3** — Create GitHub Actions workflow  
  File: `.github/workflows/instagram-audit.yml`  
  Daily cron at 09:00 UTC + `workflow_dispatch` for manual testing. Wires all 6 secrets as env vars.

- [ ] `[CODE]` **Step 4** — Create `audit.py`  
  Full implementation:
  - Authenticate with Instaloader using burner IG account
  - Fetch posts from target profile (48-hour lookback window)
  - Read already-logged shortcodes from Google Sheet (column D) for dedup
  - For each new post: download media → upload to Google Drive → append row to Sheet
  - Columns: Date | Time (UTC) | Post URL | Post ID | Media (Drive link)

- [ ] `[CODE]` **Step 5** — Commit and push all code to GitHub

---

## Phase 2 — Google Cloud Setup

- [ ] `[YOU]` **Step 6** — Create a GCP project  
  Go to [console.cloud.google.com](https://console.cloud.google.com) → New Project

- [ ] `[YOU]` **Step 7** — Enable APIs  
  In the project: enable **Google Sheets API** and **Google Drive API**

- [ ] `[YOU]` **Step 8** — Create a Service Account  
  IAM & Admin → Service Accounts → Create → no role needed → Create key (JSON) → download file

- [ ] `[YOU]` **Step 9** — Base64-encode the service account key  
  Run: `base64 -w 0 service-account.json`  
  Save the output — this becomes the `GOOGLE_CREDENTIALS_JSON` secret

---

## Phase 3 — Google Sheet & Drive Setup

- [ ] `[YOU]` **Step 10** — Create a Google Sheet  
  Add a header row: `Date | Time (UTC) | Post URL | Post ID | Media`  
  Copy the Sheet ID from the URL: `docs.google.com/spreadsheets/d/`**`<SHEET_ID>`**`/edit`

- [ ] `[YOU]` **Step 11** — Share the Sheet with the service account  
  Click Share → paste the service account email (from the JSON key, field `client_email`) → Editor

- [ ] `[YOU]` **Step 12** — Create a Google Drive folder  
  This is where post images will be stored.  
  Copy the folder ID from the URL: `drive.google.com/drive/folders/`**`<FOLDER_ID>`**

- [ ] `[YOU]` **Step 13** — Share the Drive folder with the service account  
  Right-click folder → Share → paste service account email → Editor

---

## Phase 4 — Instagram Burner Account

- [ ] `[YOU]` **Step 14** — Create a throwaway Instagram account  
  Use a spare email. Log in manually once to clear any verification prompts.  
  **Do NOT enable 2FA** — it breaks automated login.  
  Do NOT use your personal or agency account.

---

## Phase 5 — GitHub Secrets

Add these 6 secrets at: `github.com/ameyades1/instagramaudit` → Settings → Secrets and variables → Actions

- [ ] `[YOU]` **Step 15** — Add `IG_USERNAME` — burner account username
- [ ] `[YOU]` **Step 16** — Add `IG_PASSWORD` — burner account password
- [ ] `[YOU]` **Step 17** — Add `INSTAGRAM_HANDLE` — PR agency's IG username (no @)
- [ ] `[YOU]` **Step 18** — Add `GOOGLE_CREDENTIALS_JSON` — base64 string from Step 9
- [ ] `[YOU]` **Step 19** — Add `GOOGLE_SHEET_ID` — from Step 10
- [ ] `[YOU]` **Step 20** — Add `GOOGLE_DRIVE_FOLDER_ID` — from Step 12

---

## Phase 6 — Test & Verify

- [ ] `[YOU]` **Step 21** — Trigger the workflow manually  
  Go to Actions tab → "Instagram Audit" → Run workflow

- [ ] `[YOU]` **Step 22** — Check the Actions run log  
  Confirm Instaloader authenticated, posts were fetched, no errors

- [ ] `[YOU]` **Step 23** — Verify the Google Sheet  
  New rows should appear with correct date, time, URL, post ID

- [ ] `[YOU]` **Step 24** — Verify Google Drive  
  Images should appear in the folder. Click a Drive link in column E — correct image should open.

- [ ] `[YOU]` **Step 25** — Run again to confirm dedup  
  Trigger a second manual run — no duplicate rows should be added for already-logged posts

---

## Risks & Notes

| Risk | Mitigation |
|---|---|
| Instagram blocks the burner account | Create a new one; keep request volume low (daily only) |
| Instaloader breaks after Instagram update | `pip install --upgrade instaloader` and re-push |
| Drive storage fills up | Free tier is 15 GB; at ~1 MB/post this lasts years |
| Better long-term option | Ask PR agency to link their Business account to a Facebook Developer App — official Graph API, no scraping |
