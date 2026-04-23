# Instagram Audit

Automated audit tool that tracks a public Instagram account's posting activity, logs each post to a Google Sheet, and publishes a live dashboard via GitHub Pages.

Built to monitor a PR agency's Instagram output without requiring access to their account or the Instagram Graph API.

---

## Goals

- Detect every new post (images, carousels, reels, stories) within 6 hours of it being published
- Log the date, time, post URL, post ID, and post type to a Google Sheet automatically
- Preserve a permanent screenshot of each post thumbnail in case content is later deleted
- Surface a summary and the most recent posts on a public dashboard webpage

---

## How It Works

```
GitHub Actions (every 6 hours)
        │
        ▼
  audit.py
        │
        ├─► Apify — fetches latest posts, reels, and stories via 3 actors
        │         (instagram-profile-scraper, instagram-reel-scraper, instagram-story-scraper)
        │
        ├─► Google Sheets API — reads already-logged post IDs to deduplicate
        │
        ├─► For each new post:
        │       ├─ Downloads thumbnail → saved to docs/images/<date>-<id>.jpg
        │       ├─ Appends a row to Google Sheet (date, time, URL, ID, IMAGE formula, type)
        │       └─ Updates docs/data.json with post metadata + local image path
        │
        └─► GitHub Actions commits docs/data.json + docs/images/ back to the repo
```

The GitHub Pages site (`docs/index.html`) reads `data.json` for the post cards and queries the Google Sheets gviz API for the Summary sheet table. Both update automatically on each workflow run.

---

## Why Apify

Instagram permanently blocks all requests from datacenter IP ranges (including GitHub Actions / Azure). Direct scraping tools like Instaloader fail on GitHub Actions regardless of authentication method.

Apify maintains a residential proxy network that routes requests through real home IPs, so Instagram does not block them. The workflow only makes a standard HTTPS call to the Apify API — never a direct Instagram request.

### Free Tier Cost

Apify's free plan includes **$5 of credit per month** (no rollover).

| Actor | Pricing | Cost per run |
|---|---|---|
| `instagram-profile-scraper` | $2.60 / 1,000 profiles | ~$0.0026 |
| `instagram-reel-scraper` | pay-per-result | ~$0.01 |
| `instagram-story-scraper` | pay-per-result | ~$0.01 |

Running every 6 hours = ~120 runs/month ≈ **$0.31–$1.50/month**, well within the $5 free credit.

You would need to run every ~5 minutes continuously all month to exhaust the free tier.

---

## Limitations

- **12-post lookback**: The profile scraper returns only the last 12 grid posts per run. Posts published more than 12 posts ago before the first run was set up will not be captured. This is why data from March 2026 (before the tool was running continuously) may be incomplete.
- **Stories expire**: Instagram stories disappear after 24 hours. The scraper can only capture stories that are still live at the time of the run. The 6-hour cadence maximises coverage but cannot guarantee every story is caught.
- **Thumbnail permanence**: `=IMAGE()` formulas in Google Sheets reference the Apify CDN URL, which may expire. The downloaded images in `docs/images/` are the permanent record — git history preserves them even if posts are deleted from Instagram.
- **Public accounts only**: This tool works only on public Instagram profiles. No Instagram credentials are required or used.
- **No engagement metrics**: Only post existence (date, time, type) is tracked. Like/comment counts are not collected.

---

## Dashboard

The GitHub Pages dashboard shows:

- A **Summary table** pulled live from the Google Sheet (Sheet: `Summary`, columns A–D)
- The **5 most recent posts** with thumbnails, post type badges, and links
- Last post detected timestamp and page last updated timestamp

---

## Required Secrets

Set these under **Settings → Secrets and variables → Actions** in the GitHub repo:

| Secret | Description |
|---|---|
| `APIFY_API_KEY` | Apify account API token |
| `INSTAGRAM_HANDLE` | Target account username (no @) |
| `GOOGLE_CREDENTIALS_JSON` | GCP service account key JSON, base64-encoded |
| `GOOGLE_SHEET_ID` | ID from the Google Sheet URL |

### Base64-encoding the service account key

```bash
base64 -w 0 service-account.json
```

---

## Google Sheet Setup

The sheet must be shared with the service account email as **Editor**.

| Column | Content |
|---|---|
| A | Date (YYYY-MM-DD) |
| B | Time (HH:MM IST) |
| C | Post URL |
| D | Post ID / shortcode |
| E | Thumbnail (`=IMAGE()` formula) |
| F | Post type (Image, Video, Carousel, Reel, Story) |

A separate sheet named **Summary** is used for the dashboard summary table.

---

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export APIFY_API_KEY=...
export INSTAGRAM_HANDLE=...
export GOOGLE_CREDENTIALS_JSON=...
export GOOGLE_SHEET_ID=...

python audit.py
```
