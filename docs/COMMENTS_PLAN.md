# Plan: Capture Instagram Post Comments → Google Sheet

## Context
The audit already logs new posts to a "Post Details" tab every 6 hours. The user wants all comments on each post captured and appended to a sheet whenever new comments appear. This plan addresses (1) the sheet structure decision and (2) the implementation approach.

---

## Sheet Structure Recommendation: Flat "Comments" Tab in the Existing Workbook

**Recommended:** One new tab called **"Comments"** in the same Google Sheet (`GOOGLE_SHEET_ID`) — flat table, one row per comment.

| Col | Header | Example |
|-----|--------|---------|
| A | Post ID | `DXdxFRuAZMn` |
| B | Post URL | `https://www.instagram.com/p/DXdxFRuAZMn/` |
| C | Comment Date | `2026-04-23` |
| D | Comment Time | `14:35` |
| E | Commenter | `@username` |
| F | Comment | `Great post!` |
| G | Comment ID | `17858893269000001` (used for deduplication, hidden column) |

**Why NOT one workbook per month / one tab per post:**
- One workbook/month requires rotating the `GOOGLE_SHEET_ID` secret each month — operational burden
- One tab per post → 12–24 new tabs/month, unwieldy by month 2, and Google Sheets caps at 200 tabs
- A flat table is trivially filterable by Post ID (column A) to see all comments on one post
- Matches the existing "Post Details" pattern — one flat log, append-only

---

## Apify Actor for Comments

The existing scrapers return only a handful of `latestComments` (not all). Full comment fetching requires:

**`apify/instagram-comment-scraper`**
- Input: `{"directUrls": ["https://instagram.com/p/<shortcode>/"], "resultsLimit": 500}`
- Returns: per-comment objects with `id`, `text`, `ownerUsername`, `timestamp`, `likesCount`
- Pricing: ~$1.50/1,000 comments (pay-per-result on free plan)

---

## Scope Strategy (Cost Control)

Running the comments scraper on every post every 6 hours would be expensive. Strategy:

**Only scrape comments on posts from the last 30 days.**

- On each audit run, read "Post Details" tab to find posts within the last 30 days
- Call the comments scraper for those posts only
- Read already-logged comment IDs from the "Comments" tab (column G) to deduplicate
- Append only new comments

---

## Files to Modify

**`/home/ameya/repo/instagramaudit/audit.py`** — all changes here:

1. **New function `get_recent_post_ids(sheets, sheet_id)`** — reads "Post Details!A:C" (Date + Post ID + URL), returns list of `(post_id, url)` tuples for posts within last 30 days

2. **New function `get_logged_comment_ids(sheets, sheet_id)`** — reads "Comments!G:G" (Comment ID column), returns set of already-logged comment IDs

3. **New function `fetch_comments(client, post_url)`** — calls `apify/instagram-comment-scraper` for one post URL, returns list of comment dicts

4. **New function `append_comments(sheets, sheet_id, rows)`** — appends a batch of comment rows to "Comments!A:G"

5. **`main()`** — after the existing post-logging loop, add a comments block:
   - Get recent post IDs from sheet
   - Get already-logged comment IDs from sheet
   - For each recent post, fetch comments, filter out already-logged, append new ones
   - Print summary

---

## GitHub Actions

No changes needed to `.github/workflows/instagram-audit.yml` — the comments job runs inside the same `python audit.py` call, using the same secrets (`APIFY_API_KEY`, `GOOGLE_SHEET_ID`, `GOOGLE_CREDENTIALS_JSON`).

---

## Verification

1. Manually trigger the workflow via `workflow_dispatch`
2. Check the "Comments" tab was created (or pre-create it) with the correct headers
3. Confirm rows appear with correct Post ID, date, commenter, and text
4. Run again — confirm no duplicate rows are added
5. Check Apify usage dashboard to validate cost per run stays within free tier

---

## Pre-requisite

The "Comments" tab must exist in the Google Sheet before the first run (the script will append to it but not create the tab). Either create it manually or add a one-time `ensure_comments_tab()` helper that calls `spreadsheets.batchUpdate` to add the sheet if absent.
