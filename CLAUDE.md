# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Instagram Audit** is an automated monitoring tool that:
- Runs on GitHub Actions every 6 hours (via Apify API, not direct scraping — Instagram blocks datacenter IPs)
- Detects new posts (images, carousels, reels, stories) from a public Instagram account
- Logs metadata to a Google Sheet (date, time, URL, post ID, type, captions, comments)
- Preserves thumbnails locally in `docs/images/` and in Google Sheets via IMAGE formulas
- Updates a JSON data file (`docs/data.json`) that powers a GitHub Pages dashboard

## Development Setup

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # or: .venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Set environment variables for local testing
export APIFY_API_KEY=...
export INSTAGRAM_HANDLE=...
export GOOGLE_CREDENTIALS_JSON=...  # Base64-encoded service account JSON
export GOOGLE_SHEET_ID=...
```

## Running & Testing

```bash
# Run the main audit script locally
python audit.py

# Run backfill scripts (one-off operations, manual-only)
python backfill_comments.py
python backfill_captions.py
```

## Architecture

### Core Components

**`audit.py`** (main script)
- Authenticates with Google Sheets API using base64-decoded service account credentials
- Fetches posts via three Apify actors:
  - `apify/instagram-profile-scraper` → grid posts (last 12)
  - `apify/instagram-reel-scraper` → reels
  - `apify/instagram-story-scraper` → stories
- Deduplicates by shortcode against already-logged posts in Google Sheets
- For each new post:
  - Downloads thumbnail to `docs/images/<date>-<id>.jpg`
  - Appends row to Google Sheets "Post Details" tab with IMAGE formula
  - Extracts latest comments and logs to "Comments" tab
  - Updates `docs/data.json` with post metadata (keeps last 20)
- Timezone: IST (India Standard Time, UTC+5:30)
- Post types: Image, Video, Carousel (Sidecar), Reel, Story

**`backfill_captions.py`** (manual, one-off)
- Reads all posts from "Post Details" sheet
- Fetches missing captions via `apify/instagram-scraper` using directUrls
- Batch-updates column H (captions) for posts that don't have one
- Skips stories

**`backfill_comments.py`** (manual, one-off)
- Reads all posts from "Post Details" sheet
- Fetches comments via `apify/instagram-comments-scraper` (up to 100 per post)
- Deduplicates by comment ID
- Appends to "Comments" sheet
- Skips stories

### Google Sheets Schema

**"Post Details" tab** (columns A–H)
- A: Date (YYYY-MM-DD)
- B: Time (HH:MM IST)
- C: Post URL
- D: Post ID (shortcode or story_id)
- E: Thumbnail (=IMAGE() formula referencing Apify CDN + scaled dimensions)
- F: Post type (Image, Video, Carousel, Reel, Story)
- G: Empty (reserved)
- H: Caption

**"Comments" tab** (columns A–G)
- A: Post ID (shortcode)
- B: Post URL
- C: Comment date (YYYY-MM-DD)
- D: Comment time (HH:MM)
- E: Comment author username
- F: Comment text
- G: Comment ID (for deduplication)

**"Summary" tab** (queried live by dashboard)
- User-maintained sheet with aggregated statistics, displayed on GitHub Pages

### Data Files

**`docs/data.json`**
- JSON object with `posts` array (last 20 posts) and `updated` timestamp
- Powers the GitHub Pages dashboard
- Structure: `{posts: [{date, time, url, id, imageUrl (local path), type}, ...], updated}`

**`docs/images/`**
- Cached thumbnails: `<date>-<id>.jpg`
- Permanent record (git history preserves even if Instagram deletes)
- Image dimensions scaled down to max 500px to keep repo size manageable

### GitHub Actions

**`.github/workflows/instagram-audit.yml`** (automatic)
- Runs on schedule: `0 */6 * * *` (every 6 hours)
- Also supports `workflow_dispatch` for manual triggering
- Steps: checkout, setup Python 3.12, install deps, run audit.py, commit & push data.json + images/

**`.github/workflows/backfill-captions.yml`** (manual)
**`.github/workflows/backfill-comments.yml`** (manual)
- Both marked as `workflow_dispatch`-only (no schedule)
- Explicitly documented: backfills are manual-only operations

## Key Technical Decisions

1. **Apify instead of direct scraping**: Instagram blocks datacenter IP ranges (GitHub Actions, Azure). Apify uses residential proxies (~$0.01–$0.03 per run, well within free tier $5/month).

2. **12-post lookback limit**: Profile scraper returns only latest 12 grid posts per run. Posts published before continuous monitoring started may be incomplete.

3. **Stories expire after 24h**: Story scraper can only capture live stories. 6-hour cadence maximizes coverage but doesn't guarantee capture.

4. **Image formula with CDN URL**: Uses Apify CDN URL in IMAGE() formula, but falls back to local path if download succeeds. Local images in git are the permanent record.

5. **IST timezone**: All timestamps logged in IST (UTC+5:30), not UTC.

6. **Deduplication strategy**: 
   - Posts deduplicated by shortcode before fetching
   - Comments deduplicated by comment ID
   - Prevents duplicate rows on re-runs

7. **Comment capture in main flow**: `audit.py` now extracts latest comments (3–5 per post) from grid posts and logs them. Backfill script available for retroactive backfilling.

## Environment Variables & Secrets

All required for GitHub Actions and local testing:
- `APIFY_API_KEY`: Apify account token
- `INSTAGRAM_HANDLE`: Target account username (no @)
- `GOOGLE_CREDENTIALS_JSON`: GCP service account key JSON, base64-encoded
- `GOOGLE_SHEET_ID`: Google Sheet ID from URL

Service account must have Editor access to the target Google Sheet.

## Common Tasks

**Add a new post type**: Update `TYPE_MAP` in `audit.py` to map Apify post type to display name.

**Change audit frequency**: Edit cron in `.github/workflows/instagram-audit.yml`.

**Increase image cache**: Modify `MAX_PX` in `audit.py` (currently 500px) or fetch full-resolution (risk repo size growth).

**Extend data.json history**: Increase the `[:20]` slice in `update_data_json()` (currently keeps last 20 posts).

**Retry failed runs**: Use GitHub Actions "Re-run jobs" button, or trigger manually via `workflow_dispatch`.

## Testing Notes

- Local testing requires all four environment variables set
- Apify API calls incur free-tier cost (~$0.01–$0.03 per run)
- Google Sheets API calls are free
- Test against a dummy Instagram account or small sheet first to verify credentials
