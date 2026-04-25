# Instagram Audit

Automated audit tool that tracks a public Instagram account's posting activity, logs each post to a Google Sheet, and publishes a live dashboard via GitHub Pages.

Built to monitor a PR agency's Instagram output without requiring access to their account or the Instagram Graph API.

---

## Goals

- Detect every new post (images, carousels, reels, stories) within 6 hours of it being published
- Log the date, time, post URL, post ID, and post type to a Google Sheet automatically
- Capture comments from posts (up to 10 per post for posts from the last 7 days)
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
        ├─► Apify — fetches latest posts, reels, and stories via 4 actors
        │         (instagram-profile-scraper, instagram-reel-scraper, instagram-story-scraper,
        │          instagram-comment-scraper for posts from last 7 days)
        │
        ├─► Google Sheets API — reads already-logged post IDs and comment IDs to deduplicate
        │
        ├─► For each new post:
        │       ├─ Downloads thumbnail → saved to docs/images/<date>-<id>.jpg
        │       ├─ Appends a row to Google Sheet (date, time, URL, ID, IMAGE formula, type)
        │       └─ Updates docs/data.json with post metadata + local image path
        │
        ├─► For posts from the last 7 days (non-stories):
        │       └─ Fetches up to 10 comments per post and appends to Comments sheet
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
| `instagram-reel-scraper` | pay-per-result | ~$0.005 |
| `instagram-story-scraper` | pay-per-result | ~$0.005 |
| `instagram-comment-scraper` | $1.50 / 1,000 comments | ~$0.015 (7-day window, 2 active posts) |

**Monthly breakdown** (120 runs at 6-hour cadence):
- Profile + Reel + Story scrapers: **~$1.20/month**
- Comments scraper (avg 2 posts × 10 comments): **~$3.60/month**
- **Total: ~$4.80/month**, well within the $5 free credit

Budget assumptions:
- 2 posts per week (typical for PR agency) = ~2 active posts in 7-day window
- ~10 new comments per post during that 7-day period
- Comments scraper only processes posts from last 7 days to control costs

You would need significantly more posts or comment volume to approach the $5 monthly limit.

---

## Limitations

- **12-post lookback**: The profile scraper returns only the last 12 grid posts per run. Posts published more than 12 posts ago before the first run was set up will not be captured. This is why data from March 2026 (before the tool was running continuously) may be incomplete.
- **Stories expire**: Instagram stories disappear after 24 hours. The scraper can only capture stories that are still live at the time of the run. The 6-hour cadence maximises coverage but cannot guarantee every story is caught.
- **Comment window**: Comments are only captured for posts from the last 7 days. Older posts will not have new comments added. This is a cost control measure to stay within the $5/month free tier.
- **Comment limit per post**: Up to 10 comments per post are captured (due to budget constraints). High-engagement posts may have more comments that are not captured.
- **Thumbnail permanence**: `=IMAGE()` formulas in Google Sheets reference the Apify CDN URL, which may expire. The downloaded images in `docs/images/` are the permanent record — git history preserves them even if posts are deleted from Instagram.
- **Public accounts only**: This tool works only on public Instagram profiles. No Instagram credentials are required or used.
- **No likes/shares**: Only comments are tracked. Like counts, share counts, and other engagement metrics are not collected.

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

**Post Details tab** (columns A–H):

| Column | Content |
|---|---|
| A | Date (YYYY-MM-DD) |
| B | Time (HH:MM IST) |
| C | Post URL |
| D | Post ID / shortcode |
| E | Thumbnail (`=IMAGE()` formula) |
| F | Post type (Image, Video, Carousel, Reel, Story) |
| G | (reserved) |
| H | Caption |

**Comments tab** (columns A–G):

| Column | Content |
|---|---|
| A | Post ID (shortcode) |
| B | Post URL |
| C | Comment date (YYYY-MM-DD) |
| D | Comment time (HH:MM IST) |
| E | Comment author username |
| F | Comment text |
| G | Comment ID (for deduplication, hidden) |

**Summary tab** (user-maintained):
- Used for the dashboard summary table (pulled live by GitHub Pages)
- Structure: columns A–D with aggregated statistics

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
