# Apify Research — Instagram Audit

## Free Tier

- **$5 real credit/month** included on the free plan (no rollover, resets each billing cycle)
- Compute units priced at $0.20/CU, but Instagram scrapers use a pay-per-result (PPR) model — platform usage is included in the per-result price, so the $5 goes directly toward results

---

## Best Actor for This Use Case

**`apify/instagram-profile-scraper`**

- Pricing: **$2.60 / 1,000 profiles** (free plan)
- One run on one username = **1 result** = **last 12 posts** included in payload
- Cost per run: **~$0.0026**
- With $5 free credit: ~1,923 runs/month before exhausting the budget

This is the most cost-efficient actor — we pay per profile, not per post, and get the last 12 posts in a single call.

---

## Sustainable Cadence on Free Tier

| Cadence | Runs/month | Cost/month | % of $5 credit |
|---|---|---|---|
| Every 6 hours | ~120 | $0.31 | 6% |
| Every 12 hours | ~60 | $0.16 | 3% |
| Daily | ~30 | $0.08 | 1.6% |

You would need to run every ~20 minutes continuously all month to exhaust the $5 credit.

**Recommended cadence: every 6 hours** — catches new posts within 6 hours of publishing, costs $0.31/month (well within free tier), and the 12-post payload is more than sufficient for a daily audit.

---

## Why Apify vs Instaloader on GitHub Actions

GitHub Actions runs on Azure datacenter IPs, which Instagram permanently blocks at the network level for the mobile API endpoints that Instaloader uses. Apify maintains residential proxy infrastructure that routes requests through real home IPs, so Instagram does not block it. The Apify API call from GitHub Actions is just a standard HTTPS request — not a direct Instagram request — so it is never blocked.

---

## Implementation Changes Required

| Item | Current (Instaloader) | With Apify |
|---|---|---|
| `runs-on` | `self-hosted` | `ubuntu-latest` |
| Login/session | Instaloader session file | None |
| Secrets | `IG_USERNAME`, `IG_SESSION` | `APIFY_API_KEY` |
| Library | `instaloader` | `apify-client` |
| Cron | `0 9 * * *` (daily) | `0 */6 * * *` (every 6h) |
| PC needs to be on | Yes | No |

Everything else — Google Sheets logging, Drive upload, deduplication — stays the same.
