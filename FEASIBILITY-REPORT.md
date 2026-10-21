# Feasibility & Architecture Assessment
## AI-Powered Early Trend Discovery — Wellness / Hypnosis / Personal Development Vertical

**Prepared:** 21 October 2026
**Status:** Research only. Nothing has been built, installed, or deployed.
**Method:** Every endpoint claimed as "available today" was tested live from this machine unless explicitly marked otherwise. Claims about *quotas, pricing, and terms* were read from primary vendor documentation. Claims about *existing open-source projects* were read from their repositories.

---

## 0. Verification legend

| Marker | Meaning |
|---|---|
| **[V]** | I executed this against the live endpoint from this machine on 2026-10-21 |
| **[D]** | Read from primary vendor documentation (URL given) |
| **[R]** | Delegated to a research subagent and reported with a citation; I did not independently re-verify the document text |
| **[U]** | Could not verify — flagged explicitly |

---

# A. FEASIBILITY

## A.1 Verdict by capability

| Capability | Feasibility | Why |
|---|---|---|
| **Basic trend monitoring** (what's trending now, per niche) | **9/10** | Multiple keyless, legal, stable endpoints exist and were verified working. |
| **Early trend discovery** (before it's obvious) | **6/10** | Achievable — but the early signal must come from *search intent and emerging concepts*, not social engagement. Lead time is realistically **hours-to-days**, not minutes. |
| **Cross-platform analysis** | **5/10** | TikTok and Instagram have **no legal, free, stable trend API**. Cross-confirmation will be across Google/YouTube/Wikipedia/Pinterest/Mastodon, not TikTok↔Instagram. |
| **Automated intelligence** (clustering, summarising, intent classification) | **8/10** | Local multilingual embeddings + a free LLM tier handle this at near-zero cost. |
| **Predictive trend detection** ("before it goes viral") | **3/10** | Cannot be validated without historical data. Must ship as a *ranked, evidence-linked probability*, never as a prediction. |
| **Fully automated dashboard** | **7/10** | Fully achievable on Netlify + Cloudflare, but Netlify **must not** be the compute plane. |

## A.2 The honest reframing of the brief

The brief asks for an early-warning system over **TikTok and Instagram**. Live testing shows:

- **TikTok has no public trend API.** The Creative Center's internal endpoint (`ads.tiktok.com/creative_radar_api/v1/popular_trend/hashtag/list`) returns `{"code":40101,"msg":"no permission"}` from a datacenter IP **[V]**; the trending-sounds endpoint now returns **404** — TikTok removed that feed **[V]**. TikTok's *only* official trend-shaped APIs are the Research API (academic/nonprofit only, invite-gated) and Business API (your own account only).
- **Instagram's official API cannot discover trends.** The Graph API hashtag-search surface requires App Review + Business Verification, and is capped at **30 unique hashtags per rolling 7 days per account**. It can only re-query tags you already know. There is no trending-hashtag endpoint and no hashtag time series. **[R, Meta docs]**
- **TikTok's own ToS prohibits commercial screen-scraping** (verified against the live ToS text by research) **[R]**, and the brief itself forbids bypassing access controls.

**Therefore: the concept is feasible, but not on the brief's assumed data plane.** A defensible, free, sustainable system gets its early signal from **search-intent surfaces (Google Trends, Google/YouTube autocomplete, YouTube Data API), emerging-concept surfaces (Wikipedia pageviews, Pinterest Trends), and adjacent social surfaces (Mastodon, Threads, News RSS)** — and uses **TikTok Creative Center manually** as the *validation baseline* the brief asks for in §10, not as an automated feed.

This is not a downgrade. It is where the earliest signal actually lives, and it is legally clean.

---

# B. DATA SOURCES

## B.1 Tier 1 — Free, keyless, legally clean, verified working today

| Source | Endpoint | Verified | What it gives | Cadence | Limits |
|---|---|---|---|---|---|
| **Google Trends "Trending Now" (full)** | `POST trends.google.com/_/TrendsUi/data/batchexecute?rpcids=i0OFE` | **[V]** HTTP 200, **188 KB**, **565 rows** for US/24h | `title`, `search_volume`, `pct_increase`, **`start_ts`/`end_ts`**, `breakout_keywords`, `category_ids` | Hourly | Undocumented internal endpoint; no official API; may change. Includes ~48 h lag semantics on some fields |
| **Google Trends RSS** | `trends.google.com/trending/rss?geo=FI` | **[V]** HTTP 200, 10 items, localised titles for FI/ES/US | keyword, `ht:approx_traffic`, news links, rank | Hourly (feed refreshes hourly-ish) | Only 10 items/geo; no volume precision; `hours`/`category`/`sort` params are inert **[V]** |
| **Google / YouTube Autocomplete** | `suggestqueries.google.com/complete/search?client=firefox&hl=fi` | **[V]** working; `hl=en/fi/es` return **different** lists | Long-tail query phrases; YouTube variant returns **weighted** popularity buckets `[512,433,131]` | Hourly | `gl=` country param is **ignored** (byte-identical across US/GB/IN) — only `hl` localises **[V/R]**. No official API; low-volume use only |
| **Wikipedia pageviews** | `wikimedia.org/api/rest_v1/metrics/pageviews/per-article/.../user/Hypnosis/daily/...` | **[V]** HTTP 200 | Daily view counts for any article, any language wiki | Daily (T+1, sometimes T+2) | Daily granularity only; monthly endpoint 404s **[R]** |
| **Mastodon trends** | `mastodon.social/api/v1/trends/tags` | **[V]** HTTP 200 | Each tag carries a **built-in 7-day daily history** `[{day, accounts, uses}]` — free velocity time series | Hourly | Mastodon is not our audience, but it is a clean, free, *self-reported burst-detector* source |
| **Google News RSS** | `news.google.com/rss/search?q=...&qft=+qdr:d` | **[V]** recency windows change result-set size | News-attention velocity on niche terms | Hourly | 100-item cap; no volume |
| **HN Algolia** | `hn.algolia.com/api/v1/search_by_date?query=...` | **[V]** HTTP 200 | Newest-first mentions; free, no key | Hourly | Low niche relevance (tech-heavy) |
| **Europe PMC / PubMed / Crossref / arXiv** | `ebi.ac.uk/europepmc/webservices/rest/search`; `eutils.ncbi.nlm.nih.gov` | **[V]** HTTP 200 | Research-emergence + **evidence grading** for the §11 safety requirement | Daily | PubMed 3 req/s (10 with free NCBI key) |
| **iTunes/Apple Podcasts search** | `itunes.apple.com/search?term=...&media=podcast` | **[V]** HTTP 200 | New podcast episodes/feeds in a niche | Daily | No view metrics |
| **YouTube Data API v3** | Official | **[D]** | `search.list` (order=date) → fresh videos; count **distinct channels**; `commentThreads.list` → audience questions | Hourly | 10,000 units/day + **100 `search.list`/day** (separate bucket since Jun 2026) **[D]** |

## B.2 Tier 2 — Official APIs, real and usable, but gated (long lead time → apply now)

| Source | What it unlocks | Gate | Effort |
|---|---|---|---|
| **Instagram Graph API — Hashtag Search** | `/{ig-hashtag-id}/top_media` + `/recent_media` for public media; re-querying a known tag is free within the 7-day window | Meta **App Review** + `instagram_basic` + **Instagram Public Content Access** + Business/Creator account + Business Verification | Weeks–months. **Allowed-usage wording is brand/campaign-scoped** — a generic aggregator may not pass review **[R]** |
| **Threads API — `keyword_search`** | Search **public Threads posts** by keyword/tag, with `since`/`until` windows and `search_type=TOP\|RECENT` | App Review for `threads_keyword_search` | 2,200 queries/24h/user **[R]**. Best free official public-trend API of 2026 |
| **Pinterest Trends API** | `/v5/trends/keywords/{region}/top/growing` — an explicit **early-trend ranking** with `pct_growth_wow`, weekly normalised time series | Manual **Standard access review** (screen-recorded OAuth demo required); Trial tier exists | **Best niche fit of any source**: wellness/lifestyle vertical, pre-purchase intent, and the region buckets include **SE+DK+FI+NO** and (likely) ES **[R]** |
| **TikTok Research API** | Public account/content query | Academic & non-profit only; **not open to a commercial product** | Do not plan around it |
| **Meta Content Library API** | Facebook/Instagram public content | Qualified academic/non-profit institutions only, in a clean room | Barred to commercial users **[R]** |

## B.3 Tier 3 — Available but fragile. Use as enrichment, never as backbone

| Source | Reality |
|---|---|
| **TikTok Creative Center (UI)** | Free, login-optional, human-browsable, **not automatable** without a WAF-defeating proxy. Apify's actor changelog shows TikTok removed the songs and creators feeds in Jun 2026 **[R]** — so **do not build on sound-level or creator-level TikTok trends** |
| **`davidteather/TikTok-Api` 7.3.3** | Alive but in **maintenance mode**; needs your own `msToken` + Playwright + likely a residential proxy. **User-level endpoints are broken** by the `X-Gnarly` signature change (Jul 2026), unfixed **[R]**. Reverse-engineering that signature is exactly the access-control circumvention the brief forbids — exclude it |
| **`instaloader` 4.15.4** | Genuinely maintained (patched 12 Oct 2026) but it is a **logged-in** scraper, hashtags require login, IG is throwing `feedback_required` checkpoints and 429s, and commercial use is ToS-prohibited **[R]**. Your account becomes the liability |
| **Reddit** | **Dying on a fixed schedule.** RSS ends 13 Nov 2026; new public API access requests close **31 Oct 2026**; public API access ends Mar 2027 **[R]**. Independently confirmed: `reddit.com/r/hypnosis/new.json` → **403**, `.rss` → **429** from this datacenter IP **[V]**. `Arctic Shift` free archive works **[V]** but lags 4–6 weeks and will break **[R]** |
| **X / Twitter** | Effectively no free path — `nitter` was **archived 9 Oct 2026** after an X Corp C&D **[R]**; paid API is ~$42k/mo **[R]** |
| **Pinterest Trends website** | Behind Arkose Labs bot protection; `/api/*` paths all 404 **[R]** |
| **Apify** | $5/mo prepaid credit, no card, permanent **[R]**. `data_xplorer/tiktok-trends` ≈ $0.50/1k results — the only repeatable *structured* TikTok trend source, but its own README admits TikTok doesn't serve a full hashtag feed to non-browser clients |

## B.4 What is realistically NOT collectable

- TikTok trending **sounds** and **creators** (removed) — do not design around them
- TikTok **video-level engagement** at any free price, sustainably, without a paid residential proxy
- Instagram **new hashtag discovery** via official API (impossible), or **comment content** (not exposed by Graph API)
- **Anyone's** TikTok/IG data at sub-hourly cadence, for free, legally
- Reddit after 13 Nov 2026 without a Devvit app
- **Absolute search volume** anywhere except Google Ads Keyword Planner (needs an ad account + card; also sensitive-keyword filters may block "hypnosis"/"therapy")

---

# C. EXISTING SOLUTIONS — do not rebuild these

## C.1 Reuse directly

| Project | Verdict |
|---|---|
| **`flack0x/trendspyg`** — MIT, 58★, actively maintained **[V]** | **The single best component.** Already implements: browser-free Google Trends RSS collection (125 countries), `watch_google_trends_rss` streaming `new`/`volume_up`/`dropped` events, a **local SQLite history archive** with first-seen + rank-over-time, a pytrends-compatible `TrendReq`, and a documented rate-limit story (~8–10 browser sessions per 15 min triggers a 35+ min Google 429 — so **use RSS for scheduled work, treat Explore as manual enrichment only**). This alone replaces ~400 lines of my recommended architecture |
| **`mvanhorn/last30days-skill`** — MIT **[R]** | The best **discovery-mode** engine: a 3-stage cost ladder (nomination sweep → LLM judgment with a `worthiness` score → deep research only for survivors). Its "velocity-ranked topics with momentum labels" output is close to what the brief asks for. MIT licence makes it commercially reusable |
| **`MaartenGr/BERTopic`** — MIT **[R]** | Correct tool for new-topic detection: `model.partial_fit(doc)` is true **online/incremental** topic modelling — a new cluster id *is* a newly-emerging topic, no refit required. `.topics_over_time()` gives topic-level velocity |
| **`sansan0/TrendRadar`** — **GPL-3.0**, 63.1k★, 260 commits, v6.11.0 (13 Oct 2026) **[V]** | The **architecture reference**: cron → 11 platforms → SQLite/R2 → timeline + rank + 🆕-newness detection → LiteLLM analysis → `index.html` → 9 push channels → MCP server. **Do not link it (GPL-3.0 copyleft).** It is also Chinese-platform-scoped with no TikTok/IG/Reddit/Finnish sources, and it depends on a third-party hot-list API |
| **`HalcyonVector/GitHub-Trending-Intelligence-`** — MIT **[R]** | Best **modern stack reference** (FastAPI + Celery + Postgres + Redis + Next.js + Ollama, 0–100 momentum score blending velocity with a recency bonus, "hype vs substance" flag) — but GitHub-domain only |
| **`barretlee/agent-pulse`** — MIT **[R]** | Good pattern for *evidence-linked judgments*: traceable Events, explicit next-signal / counter-signal / invalidation conditions |
| **`theagenttimes/agent-news`** — MIT-0 **[R]** | Good pattern for **confidence labels + signed provenance** (CONFIRMED / REPORTED / ESTIMATED) — directly serves the brief's "distinguish verified observations from AI interpretation" requirement |

## C.2 Do NOT use

| Project | Why |
|---|---|
| `GeneralMills/pytrends` | **Archived** Apr 2025; `trending_searches()` and `top_charts()` now 404 **[R]** |
| `zedeus/nitter` | **Archived 9 Oct 2026** after X Corp C&D; all instances dead **[R]** |
| `xdevplatform/Gnip-Trend-Detection` | Archived 2017 — read the *paper*, not the code **[R]** |
| `imsyy/DailyHotApi` | MIT and clean, but **no TikTok/IG/Reddit/Google-Trends**; 54 of 58 routes are Chinese platforms. Wrong market, wrong languages **[R]** |
| `soxoj/TrendRadar` | 404 — moved to `sansan0/TrendRadar` |
| `DIYgod/RSSHub` | 700+ routes, but AGPL-3.0 and heavy dependencies **[R]** |

---

# D. DETECTION METHODOLOGY

## D.1 The principle

> **A trend is a change in the rate of change of a concept's visibility — not its volume.**

The single strongest empirical finding in the literature is that **burst acceleration** outranks raw volume as a predictive feature. A 2026 multi-source study (9.2 M posts, 1,800 labelled emerging topics, 14 months) reports **mean detection lead time of 36.4 hours ahead of native platform trending lists, F1 = 0.91**, with the top three features being *burst acceleration → cross-platform co-occurrence → influencer-adjusted reach* **[R]**.

## D.2 The five signals, and why each should work

| # | Signal | Source | Why it detects *early* | What it cannot do |
|---|---|---|---|---|
| **S1** | **Burst onset / change-point on a concept's own series** | Wikipedia pageviews, Mastodon tag `uses`, YouTube creator-count, News RSS volume | Kleinberg's HMM burst model identifies **the exact single message on which the state transition occurred** — the onset *is* the first observation, which is what makes it a first-mover detector **[R]**. Burst detection is defined relative to an *expected intensity*, so a baseline is mandatory, never an absolute threshold | Requires an existing series. Cold-start topics have no baseline |
| **S2** | **Query lengthening in autocomplete** | Google/YouTube suggest endpoints | A suggestion that only appears when you append a second word ("hypnosis **for sleep**", "hypnosis **for anxiety**") is *specific intent that content hasn't caught up with yet*. Weights in the YouTube variant give a relative popularity bucket to diff over time **[V]** | No country targeting (`gl` inert) **[V]**. Language only |
| **S3** | **Distinct-creator count growth** | YouTube Data API `search.list` (order=date) | Directly implements the brief's "more independent creators discussing the same subject". This is a *supply-side* signal that precedes *demand-side* virality | Needs a seed keyword. 100 `search.list`/day cap **[D]** |
| **S4** | **Trend onset timestamp + `% increase`** | Google Trends Trending Now batchexecute | `start_ts` gives the **minute the spike began** and `pct_increase` gives magnitude — both fields exist in the RSS feed but only `start_ts`/volume are exposed there **[V]** | General-interest list; wellness terms rarely surface. 48 h lag on some fields **[D]** |
| **S5** | **Cross-surface co-occurrence** | Wikipedia + Google Trends + YouTube + News + Pinterest + Mastodon | Corleto et al. (ASE 2013): **~72 % of matching trends appear first on social, then on Google**; a Twitter trend causes a similar Google trend ~43 % of the time **[R]**. Multi-source fusion buys ~36 h of lead **[R]** | Cross-confirmation **raises confidence**, it does not create lead time. Do not conflate the two |

## D.3 The scoring function (defensible, observable, no invented thresholds)

```
momentum_score = 100 × normalise(
      w1 · Δlog(mentions_24h)              # velocity (slope)
    + w2 · Δ²log(mentions_24h)             # acceleration (the signal that matters most)
    + w3 · burst_onset_score               # Kleinberg change-point, 0–1
    + w4 · distinct_creator_growth         # normalised across a rolling 7d median
    + w5 · cross_surface_corroboration     # distinct surfaces seen in 24h, log-scaled
    + w6 · relevance_score                 # embedding cosine to your category centroid
) × season_adj × novelty_penalty
```

Four properties make this defensible rather than arbitrary:

1. **Every term is a measured quantity with a stored timestamp.** Nothing is inferred from a score.
2. **Acceleration dominates velocity.** Acceleration is what distinguishes "gaining" from "already popular".
3. **`season_adj` is mandatory.** Mental-health Google Trends have a documented **52-week seasonal component, peaking in winter** (OCD ±45 %, schizophrenia ±43 %) **[R]**. Without this, every January produces a false "emerging trend" wave. This is the single most common failure mode of naive trend dashboards.
4. **`novelty_penalty` suppresses recycled topics.** A term whose baseline is already high is capped — we want things that *aren't* popular yet.

## D.4 Validation design (this is the part the brief is right to insist on)

**Baseline to beat:** Google Trends' own Trending Now list, Pinterest "growing" list, TikTok Creative Center's trending hashtags (checked manually), and a manual Instagram/Google scan.

**The validation harness (all free):**

1. **Run the collector for 8–12 weeks** and archive every observation with timestamps.
2. **Ground truth** = the moment a concept crosses into the baseline surfaces (appears on Trending Now; becomes a Pinterest "growing" pick; crosses a YouTube creator-count threshold; gets a Wikipedia article).
3. **Metric** = *lead time* = ground-truth timestamp − our detection timestamp. Report the distribution (median, p25, p75), not a single number.
4. **Negative control** = a **permutation test** à la Kleinberg: shuffle the corpus preserving arrival times but breaking content-time correspondence. If the shuffled corpus still produces "trends," the signal is an artefact **[R]**. This is the strongest available proof of non-spuriousness.
5. **False-positive rate** = fraction of flagged concepts that never reach the baseline within 30 days.
6. **Seasonality control** = re-run the detector with a synthetic January-shifted baseline and confirm it does *not* fire.
7. **Comparative test** = for 20 flagged topics, manually check TikTok Creative Center + Instagram + Google Trends weekly and record when *a human* would have noticed. Compare that against our detection timestamp. **If our lead time over manual checking is not materially positive, the system's complexity is not justified** — exactly the test the brief demands.

**Hard constraint I will not violate: the AI never produces the confidence number.** Confidence comes from the *number and independence of corroborating surfaces* and from the *statistical properties of the series* (z-score of the acceleration against the concept's own baseline). The LLM only does things a statistician cannot: summarise, cluster, classify intent, and write the "why this matters" — always with a citation to the observation IDs that justify it.

---

# E. ARCHITECTURE

```
                    ┌──────────────────────────────────────────┐
                    │  GITHUB ACTIONS (public repo)            │
                    │  cron: "17 * * * *"  (hourly, off-hour)   │
                    │  ubuntu-latest — 4 CPU / 16 GB           │
                    │                                           │
                    │  1. Collect  → Google Trends RSS+batch,   │
                    │               Suggest, Wikipedia, YouTube│
                    │               API, News RSS, Mastodon,    │
                    │               EuropePMC, Pinterest        │
                    │  2. Normalise → one `observation` schema  │
                    │  3. Store     → D1  (+ SQLite mirror)     │
                    │  4. Detect    → first-seen, velocity,      │
                    │               acceleration, burst onset,  │
                    │               cross-surface co-occurrence │
                    │  5. Cluster   → multilingual embeddings + │
                    │               BERTopic partial_fit        │
                    │  6. Explain   → LLM: summary, intent,     │
                    │               evidence tier, content      │
                    │               angles — with citation IDs  │
                    │  7. Publish   → static JSON + HTML        │
                    └───────────────┬──────────────────────────┘
                                    │ (D1 REST API)
                    ┌───────────────▼──────────────────────────┐
                    │  CLOUDFLARE WORKER  →  read API for the  │
                    │  dashboard (100k req/day free)           │
                    │  CLOUDFLARE D1     →  structured history │
                    │  CLOUDFLARE R2     →  raw payloads       │
                    └───────────────┬──────────────────────────┘
                                    │ client-side fetch (cached)
                    ┌───────────────▼──────────────────────────┐
                    │  NETLIFY  —  static dashboard shell      │
                    │  ONE deploy. No scheduled redeploys.     │
                    │  Cost = bandwidth only.                  │
                    └──────────────────────────────────────────┘
```

**Components, in plain terms:**

1. **Collector** — one Python program, one scheduled job, one output schema.
2. **Normalised observation schema** — the single most important design decision. Every source becomes rows of `(ts, source, geo, lang, surface, concept_key, metric, value, url, raw_ref)`. One schema means one velocity algorithm, one dashboard, one audit trail.
3. **Detector** — pure functions over the observation table. No ML in the hot path. Deterministic, replayable, and debuggable.
4. **Clusterer** — multilingual embeddings + BERTopic `partial_fit`. Run offline, not on every tick. **Use `multilingual-e5-base` (768-d, 100+ langs, MIT) or `paraphrase-multilingual-MiniLM-L12-v2` (384-d, Apache-2.0) — NOT `all-MiniLM-L6-v2`, which is English-only and will silently fail on Finnish** **[R]**.
5. **Explainer** — free LLM (Groq free tier: 1,000 req/day; Gemini free tier; or local Ollama `qwen3.5:4b` via llama.cpp, 201 languages, ~4 GB disk **[R]**). Output is always a JSON object with a `evidence_ids` array.
6. **Publisher** — a static JSON + a static HTML page. No SPA, no React runtime, no API key in the browser.

**Why not Netlify Functions for the collector?** Netlify scheduled functions have a hard **30-second** execution limit and **1024 MB** memory on Free **[V, Netlify docs]**; background functions (15 min) exist on credit-based Free but not on legacy Free **[R]**. Chromium does not fit a Netlify function bundle **[R]**. Netlify Functions are the wrong tool for a collector; they are fine for a trivial read API.

**Why GitHub Actions and not Cloudflare Workers for the collector?** Workers Free charges **10 ms CPU per cron trigger** **[V, Cloudflare docs]**, and network wait doesn't count — so a fetch-and-store worker fits, but *parsing* a 188 KB JSON payload and running embeddings will not. Cloudflare **Durable Objects** (30 s CPU/request) or Workers AI (10,000 neurons/day free) can carry the LLM step.

---

# F. INFRASTRUCTURE — the free-tier reality, verified

## F.1 The Netlify correction (matters a lot for you)

Netlify moved to a **credit-based model on 4 September 2025**. Accounts created before that date are on Legacy plans with completely different limits **[V, Netlify docs]**. Check which you are on: Netlify → Usage & billing → Billing details → Plan. **Switching is irreversible.**

| Meter | Credit-based Free (300 cr/mo, hard limit) | Legacy Free |
|---|---|---|
| Compute | **10 credits / GB-hour** → 30,000 function-minutes @ 1 GB | 125k invocations/site/mo |
| Bandwidth | **20 credits / GB** → **15 GB** | 100 GB |
| Requests | **2 credits / 10k** → **1.5 M** | — |
| **Production deploy** | **15 credits each → only 20/month** | — |
| AI inference | **180 credits per $1** → **$1.67/month of model spend** | — |

Function limits (both plans, non-configurable) **[V, Netlify docs]**: memory 1024 MB, synchronous **60 s**, **scheduled 30 s**, background 15 min.

**The trap:** a dashboard that redeploys hourly costs 15 × 720 = **10,800 credits/month** against a 300-credit budget. Your site would be **paused mid-month** ("Site not available"). Netlify's credit model has a **hard limit and no auto-recharge** on Free **[V]**.

**Therefore: deploy to Netlify once. Never redeploy on a schedule.** The dashboard shell fetches live JSON from a Cloudflare Worker at runtime.

## F.2 Component-by-component recommendation

| Component | Choice | Why | Free limit |
|---|---|---|---|
| **Dashboard hosting** | **Netlify** (your account) | You asked for it; static hosting is exactly right | 15 GB bandwidth, 1.5 M requests, 20 deploys/mo — one deploy is plenty |
| **Collector runtime** | **GitHub Actions, public repo, `ubuntu-latest`** | Standard runners are **free and unmetered in public repos** (the 2,000 min/mo figure is the *private* repo quota) **[D]**. 4 CPU / 16 GB / 14 GB SSD — the only free tier that can run Chromium and a 1 GB embedding model | Unlimited minutes |
| **Scheduler** | GH Actions `schedule`, cron `17 * * * *` | Minimum interval 5 min; **avoid the top of the hour** (documented congestion — jobs can be dropped under load) **[D]**. Use `17 *` to dodge it | — |
| **Primary store** | **Cloudflare D1** | 5 M rows read/day, 100 k rows written/day, 500 MB/DB, 7-day Time Travel, **no inactivity pause** | Ample: ~30 obs/cycle × 24 × 90 ≈ 65 k rows/quarter |
| **Raw payloads** | **Cloudflare R2** | 10 GB, free egress | Ample |
| **Read API** | **Cloudflare Worker** | 100 k req/day, **10 ms CPU** — enough to serve JSON, not to compute | Ample |
| **Backup / local mirror** | **SQLite in the repo** (or a release artifact) | You keep an owned, portable, queryable history — no vendor lock-in, and it survives any provider shutdown | ~130–260 MB/yr at hourly RSS cadence **[V via trendspyg]** |
| **LLM** | **Groq free tier** (primary) → **Gemini free tier** (fallback) → **local Ollama `qwen3.5:4b`** (offline) | Groq: `gpt-oss-120b`/`20b`, 30 RPM, 1,000 RPD, 200 K TPD, plus built-in browser search for fact-checking **[R]**. Gemini free tier is free-of-charge for Flash models but **Google-Search grounding is NOT on the free tier** **[R]** | A 100-item/day digest at 3 calls/item = 300 calls/day — fits Groq comfortably |
| **Search API (geo-targeted)** | **Brave Search API** | **$5/1,000 requests with $5 in free credits every month** (recurring, no card) **[V]**; `country=` and `search_lang=` params give you the **geo targeting that raw Google Suggest does not have** (`gl` is inert on `suggestqueries` **[V]**) — this is how you get real Finland and Spain targeting | ~1,000 requests/month |

## F.3 Rejected alternatives, with reasons

| Option | Why not |
|---|---|
| **Vercel Hobby** | Cron is **daily only** (sub-daily `schedule` fails at deploy); functions capped at 300 s; **"non-commercial personal use only"** **[D]** — disqualifying for a business tool |
| **Streamlit Community Cloud** | Sleeps after 12 h idle, wakes only on a visitor click; **no cron**; filesystem not durable across redeploys **[R]**. Fine as a read-only dashboard, wrong as a collector |
| **Supabase Free** | **Pauses after 7 days of inactivity** and `pg_cron` stops with it; backups not downloadable on Free **[R]**. Also a legal/ethical problem for storing wellness/therapy-adjacent conversation data in a shared Postgres without a DPA — D1 avoids that entirely |
| **Fly.io / Railway** | Trial credits only; no genuine free tier **[R]** |
| **Render Free** | Spins down after 15 min, ephemeral disk, no background workers **[R]** |
| **Oracle Cloud Always Free** | Real VM, but idle reclamation kills a low-duty scraper, and A1 was halved to 2 OCPU / 12 GB **[R]** |
| **PythonAnywhere Free** | Outbound internet restricted to an allowlist; 100 CPU-seconds/day **[R]** — unusable |
| **Netlify Functions as collector** | 30 s scheduled limit, 1 GB RAM, no Chromium **[V]** |
| **Cloudflare Workers as collector** | 10 ms CPU per cron **[V]** |

---

# G. RISKS

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| **R1** | **TikTok/IG data never becomes legally accessible** | **Very high** | **High** — the brief's core data plane | Design the system so TikTok/IG are *enrichment*, not dependencies. Use Creative Center manually as the validation baseline. Apply for Instagram Public Content Access + Threads keyword_search now (long lead) |
| **R2** | **Reddit disappears** | **Certain** — RSS ends 13 Nov 2026; public API ends Mar 2027 **[R]** | Medium | Do not build a Reddit-dependent component. If you want it, apply for Devvit **before 31 Oct 2026** (10 days) |
| **R3** | **Google's undocumented endpoints change or rate-limit** | High | High | Archive everything you fetch so you can always replay. Never poll the Chrome/Explore path on a schedule — it triggers a 35+ min hard block **[R]**. Use the RSS path |
| **R4** | **Seasonal false positives** (every January looks like a trend) | **High** if unhandled | High | Mandatory 52-week seasonal baseline **[R]**. Ship the January control test in the validation harness |
| **R5** | **Cold-start has no baseline** — a brand-new concept has no series to compute acceleration against | Certain | Medium | Use cross-surface *co-occurrence* and *first-seen-across-surfaces* as the cold-start detector. Show "new concept" separately from "accelerating concept" — they are different claims with different confidence |
| **R6** | **Netlify credit exhaustion → site pauses mid-month** | Medium | High | One deploy. Runtime data fetch. Never redeploy on a schedule. Monitor credits |
| **R7** | **GH Actions scheduler drops jobs / 60-day auto-disable on inactive public repos** | Medium | Medium | Off-hour cron; idempotency keys + `concurrency` group; a second trigger (Cloudflare Cron → `repository_dispatch`) that also keeps the repo "active" **[D]** |
| **R8** | **False positives / a wrong call damaging a client's trust** | Medium | **High** (wellness context) | Confidence derived from statistics, never from the LLM. Every claim carries evidence IDs. Never present a probabilistic assessment as a prediction |
| **R9** | **Wellness-specific harm** — content recommendations implying unsupported therapeutic claims to a vulnerable audience | Medium | **High** | Make **evidence tier** a first-class field (established therapy / emerging research / spiritual or cultural framing / unsupported claim), sourced from Europe PMC + PubMed + Cochrane, with a citation. Add a hard blocklist on medical claims. This is a product requirement, not a nice-to-have |
| **R10** | **Model/embedding choice silently breaks Finnish or Spanish** | Medium | Medium | Use multilingual models only. `all-MiniLM-L6-v2` is English-only **[R]** |
| **R11** | **Instagram App Review rejects a generic trend aggregator** | Medium-High | Medium | Frame the app around *your own* content strategy and a specific brand/campaign, which is what the feature's allowed-usage wording actually describes **[R]**. Or skip it — the system works without it |
| **R12** | **Privacy/GDPR exposure from storing audience questions and wellness discussions** | Medium | Medium-High | Store aggregate counts and topic labels, not raw identifiable comment text. Prefer on-device or non-EU storage (GitHub Actions is US/EU runners; D1 is global). Get a DPIA before storing raw Reddit/YouTube comments |

---

# H. IMPLEMENTATION ROADMAP

**Phase 0 — Validation harness (weeks 1–3). No dashboard, no AI.**
- Stand up the repo + one GH Actions cron + SQLite archive + D1
- Collect **only**: Google Trends RSS (FI/ES/US/GB/DE), Google Trends batchexecute Trending Now, Google + YouTube autocomplete (en/fi/es), Wikipedia pageviews for a 200-term seed list, Mastodon tag trends, Google News RSS
- Compute only: first-seen, 24 h/7 d deltas, rank change, burst onset
- **Deliverable:** a plain CSV + a single static HTML page. No LLM, no clustering, no Netlify dashboard yet
- **Gate:** ≥ 8 weeks of data. Then run the permutation test and the lead-time backtest. **If lead time vs. manual baseline is not materially positive, stop here and rethink.** This is the gate the brief asks for and it is cheap

**Phase 1 — Methodological core (weeks 4–6).**
- Add YouTube Data API (`search.list` order=date → distinct-creator count; `commentThreads.list` → audience questions)
- Add Pinterest Trends (apply for Standard access in week 1; use Trial meanwhile)
- Implement the full scoring function, seasonal baseline, novelty penalty
- Add evidence-tier classification (Europe PMC + PubMed) — the §11 safety requirement
- **Deliverable:** a ranked, evidence-linked report. Still no pretty dashboard

**Phase 2 — Dashboard + AI (weeks 7–10).**
- Multilingual embeddings + BERTopic `partial_fit` for new-topic detection
- LLM: summary, audience intent, content angles, "why it matters" — all with `evidence_ids`
- Cloudflare Worker read API + D1
- **Netlify:** static dashboard shell, one deploy
- **Deliverable:** the dashboard in the brief, minus the sections that have no data behind them

**Phase 3 — Official APIs (parallel, weeks 3–20).**
- Meta App Review: Threads `threads_keyword_search` + Instagram Public Content Access
- Fill the TikTok gap with Apify ($5/mo free credit) at a **daily** cadence only, treated as best-effort enrichment, with an explicit "source health" flag when it fails

**Phase 4 — Continuous validation (ongoing).**
- Weekly lead-time report, false-positive rate, permutation test, seasonal control
- Publish the methodology alongside the dashboard — transparency is the product's credibility

---

# I. ALTERNATIVES — and why they lose

| Alternative | Assessment |
|---|---|
| **Build everything from scratch** | Rejected. trendspyg alone gives you RSS collection + SQLite history + change events. BERTopic gives you online topic detection. Writing these is 3–6 weeks of work with no competitive advantage |
| **Fork TrendRadar** | Rejected: **GPL-3.0** forces copyleft on a commercial product; Chinese-platform sources; depends on a third-party hot-list API; no TikTok/IG/Finnish |
| **Adopt `last30days-skill` wholesale** | Closest to the brief's *discovery* half, MIT-licensed, and it has a genuine velocity-ranked output. **But** it is topic-driven (you name the topic) rather than a continuous unattended multi-geo monitor, and it leans on Reddit/X/TikTok via paid keys. **Recommended: mine its discovery protocol and reuse `trendspyg` for collection — don't adopt the whole skill** |
| **Use Apify / a paid actor for everything** | Rejected as the backbone (vendor risk + credit-limited), **accepted** for the TikTok slice (daily, best-effort) |
| **Run a local LLM on a Mac Mini / always-on machine** | Tempting (unlimited, private, free) but it is not *infrastructure* — it is a hobby that dies when the laptop sleeps. The brief asks for "largely autonomous." Use it as a fallback, not the backbone |
| **Just check TikTok Creative Center + Google Trends manually** | This is the **baseline to beat**, and it is genuinely good for *mainstream* topics. It is **structurally late** for niche wellness terms: ~72 % of matching trends appear first on social **[R]**, and Google Trends' own trending list is general-interest. A manual human will not notice "somatic discharging" until it is a hashtag |
| **Buy a commercial social listening tool** | $100–500/mo (Brandwatch, Mention, Talkwalker). No free tier, and the brief explicitly wants free. Revisit only if the free system proves the signal is real but coverage is insufficient |

---

# J. FINAL RECOMMENDATION

## 1. Overall feasibility score

| Scope | Score |
|---|---|
| **The brief as written** (TikTok + Instagram automated, free, early detection, predictive dashboard) | **6 / 10** |
| **The same goal with a legally and operationally defensible data plane** (search-intent + emerging-concept + adjacent-social, free, evidence-linked) | **8 / 10** |

The 6 is not about difficulty. It is about **two platform APIs that do not exist for commercial use**. The 8 is because everything else in the brief is achievable at zero marginal cost.

## 2. The strongest available strategy

> **Detect emerging *concepts* through search intent, emerging *practices* through independent-creator growth, and emerging *questions* through autocomplete — then rank them by acceleration against a seasonal baseline, and require cross-surface corroboration before labelling anything a trend. Use TikTok Creative Center manually as the baseline you must beat, not as a feed you must parse.**

Concretely, five keyless or officially-sanctioned surfaces, one scheduled job, one SQLite/D1 store, one static Netlify dashboard, a free LLM for explanation only, and a validation harness that publishes its own lead times.

## 3. The biggest obstacle

**The absence of a legal, free, stable API for TikTok and Instagram trend data.**

Everything else is engineering. This is a business-model and platform-governance constraint. It cannot be engineered around within the brief's rules (no bypassing access controls, no commercial scraping). The only legitimate paths are:
- **Meta**: App Review for Instagram Public Content Access + Threads `threads_keyword_search` (weeks–months; may reject a generic aggregator)
- **TikTok**: the Research API (academic/nonprofit only — not available to you), a licensed commercial arrangement, or **manual use of Creative Center**
- **Pinterest**: Standard-access review for the Trends API — *the most likely near-term win*, and the best niche fit

The project succeeds by **not depending on those answers**.

## 4. The smallest credible implementation

```
One public GitHub repo
  .github/workflows/collect.yml      # cron "17 * * * *"
  collector/                        # ~600 lines, Python
    sources.py    # 5 keyless endpoints
    normalise.py  # -> observation schema
    detect.py     # first-seen, velocity, acceleration, burst onset, co-occurrence
  data/observations.sqlite           # committed; full history, owned
  out/dashboard.html                # static, no build step
```
Five endpoints (Trends RSS, Trends batchexecute, autocomplete ×2 languages, Wikipedia pageviews, Mastodon/News RSS), one schema, one detector, one HTML file, ~600 lines, **$0/month**, runs hourly, and produces a plain ranked table of concepts with their acceleration, first-seen date, source links, and seasonal baseline.

**That is enough to prove or disprove the entire thesis.** If it cannot, no amount of dashboard will save it.

## 5. What to build first (in this exact order)

1. **The repo, the cron, and the SQLite schema.** Nothing else matters until there is a timestamped observation table.
2. **A 200-term seed list** from your §2 categories — as a versioned YAML file. This is your first real asset; it is also what you can hand to an LLM as relevance context.
3. **The detector** (first-seen, velocity, acceleration, seasonal baseline). No embeddings, no LLM. Statistics only.
4. **The validation harness** — permutation test + lead-time backtest + January control. Ship it *before* the dashboard.
5. **A plain HTML ranked table.** Ugly. Honest.
6. *Then* embeddings, *then* the LLM, *then* the dashboard you actually want.

**Start the long-lead applications in parallel, on day one:** Pinterest Trends Standard access, Meta App Review (Threads first — easiest approval, then Instagram), and Reddit Devvit (before **31 Oct 2026** if you want Reddit at all).

## 6. What to deliberately avoid building

- **A scraper for TikTok or Instagram.** Highest maintenance, highest legal risk, lowest reliability. This is where the brief's own warning ("do not confuse a working scraper with a sustainable data pipeline") bites hardest.
- **A reverse-engineered signature client** (`X-Gnarly`/`X-Bogus`) — access-control circumvention, explicitly forbidden, and TikTokApi is already broken by it.
- **A CAPTCHA-solving service or residential proxy used to defeat a WAF.** This converts a technical problem into a legal one for a business that touches therapy and hypnosis — where the reputational downside is asymmetric and severe.
- **Anything that treats an LLM confidence score as evidence.** The LLM explains; it does not measure.
- **A prediction surface.** "Before it goes viral" must ship as *"strongest current candidates, with the evidence and its limits shown."* You cannot validate predictions until you have months of history, and the first honest answer to "how accurate is this?" will be "we don't know yet" — which is fine, as long as you say it.
- **A multi-platform dashboard with empty sections.** Build only the sections you can fill with real, timestamped, linkable observations. A dashboard with 6 working sections beats one with 12 speculative ones.
- **A custom vector database, a message queue, Kubernetes, or a React SPA.** D1 + SQLite + a static HTML file covers this project's actual scale for years.
- **Storing raw audience comments.** Store counts and topic labels. Raw wellness/therapy discussion text is sensitive data with real GDPR exposure and little analytical benefit.

## 7. Final recommendation

# **GO — but GO on the narrowed thesis, not the brief as written.**

**GO** on a **Phase 0 + Phase 1** validation system: 5–8 keyless sources, one scheduled job, one SQLite store, a statistics-only detector, and a published lead-time backtest. Budget: roughly **two weeks** of focused work and **$0**. Risk: near-zero, because nothing is irreversible and no infrastructure is committed.

**CONDITIONAL GO** on Phase 2 (dashboard + AI) — **only if** Phase 0's backtest shows lead time over the manual baseline that justifies the complexity, and the false-positive rate is survivable for a wellness context.

**NO-GO** on: automated TikTok/Instagram scraping, residential-proxy WAF evasion, any predictive/"guaranteed viral" claim surface, and any expansion beyond ~10 sources before the validation harness has produced 8 weeks of honest numbers.

**Explicitly reconsider the whole project if**, after 8–12 weeks, the median lead time over manual checking is under ~24 hours, or the false-positive rate exceeds ~50%. At that point you have built a nicely-scheduled list of popular topics — which is exactly what the brief said you do *not* want.

---

## Appendix — Key URLs

**Sources (primary documentation)**
- Google Trends API alpha (application-gated, ~48 h data lag): https://developers.google.com/search/apis/trends
- Google Trends RSS: `https://trends.google.com/trending/rss?geo={FI,ES,US}`
- Google Trending Now internal endpoint: `POST https://trends.google.com/_/TrendsUi/data/batchexecute?rpcids=i0OFE`
- Google/YouTube autocomplete: `https://suggestqueries.google.com/complete/search?client=firefox&hl={lang}`
- Wikipedia pageviews: https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{wiki}/{access}/user/{title}/daily/{start}/{end}
- Mastodon trends: https://mastodon.social/api/v1/trends/tags
- Google News RSS: `https://news.google.com/rss/search?q={q}&qft=+qdr:d`
- YouTube Data API quota: https://developers.google.com/youtube/v3/getting-started
- Reddit API closure announcement: https://www.reddit.com/r/redditdev/comments/1wubcvf/moving_data_api_apps_to_the_developer_platform/
- Threads keyword_search: https://developers.facebook.com/docs/threads/keyword-search
- Instagram hashtag search: https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-facebook-login/hashtag-search
- Pinterest Trends API: https://developers.pinterest.com/docs/analytics-and-reports/trends/
- TikTok Research API: https://developers.tiktok.com/products/research-api/
- TikTok ToS: https://www.tiktok.com/legal/page/global/terms-of-service/en
- Meta scraping terms: https://www.facebook.com/apps/site_scraping_tos_terms.php
- Brave Search API pricing: https://brave.com/search/api/
- Netlify credit-based plans: https://docs.netlify.com/manage/accounts-and-billing/billing/billing-for-credit-based-plans/credit-based-pricing-plans/
- Netlify function limits: https://docs.netlify.com/build/functions/configuration/
- Cloudflare Workers limits: https://developers.cloudflare.com/workers/platform/limits/
- GitHub Actions billing (public repos unlimited): https://docs.github.com/en/billing/concepts/product-billing/github-actions
- GitHub Actions schedule semantics: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule

**Reusable code**
- https://github.com/flack0x/trendspyg — MIT, Google Trends collection + SQLite archive + change events
- https://github.com/mvanhorn/last30days-skill — MIT, discovery protocol
- https://github.com/MaartenGr/BERTopic — MIT, online topic detection
- https://github.com/sansan0/TrendRadar — GPL-3.0, architecture reference only
- https://github.com/HalcyonVector/GitHub-Trending-Intelligence- — MIT, modern stack reference
- https://github.com/barretlee/agent-pulse — MIT, evidence-linked judgment pattern
- https://github.com/ArthurHeitmann/arctic_shift — free Reddit archive (lagging, at risk)

**Methodology literature**
- Kleinberg, *Bursty and Hierarchical Structure in Streams* (KDD 2002): https://www.cs.cornell.edu/home/kleinberg/bhs.pdf
- Rizoiu et al., *A Tutorial on Hawkes Processes for Events in Social Media*: https://arxiv.org/pdf/1708.06401
- Corleto et al., *How Twitter Trending Topics Help Predict Google Hot Queries* (ASE 2013): https://www.dsi.unive.it/~orlando/PUB/ASE-2013.pdf
- Parikh & Sundaresan, *Scalable and near real-time burst detection from eCommerce queries* (KDD 2008): https://doi.org/10.1145/1401890.1402006
- Kong et al., *On the Real-time Prediction Problems of Bursting Hashtags in Twitter*: https://arxiv.org/html/1401.2018
- Mental-health search seasonality (52-week cycle): https://pmc.ncbi.nlm.nih.gov/articles/PMC6505370/

---

## Appendix — What I could NOT independently verify

| Claim | Status |
|---|---|
| Instagram hashtag search limit: 30 unique hashtags / rolling 7 days, per Business/Creator account | **[R]** — cited from Meta's developer documentation by research; the endpoint itself I confirmed returns `(#100) Param user_id is not a valid Instagram User ID` without a token **[V]**. **Verify against the live doc before relying on it.** |
| Threads `keyword_search` limit: 2,200 queries / 24 h per user | **[R]** — same treatment |
| Instagram Public Content Access allowed-usage wording being brand/campaign-scoped (i.e. a generic aggregator may fail review) | **[R]** — **highest-risk unverified assumption in this report.** Worth reading the Meta feature reference yourself before designing around it |
| Reddit closure dates (31 Oct 2026 / 13 Nov 2026 / Mar 2027) | **[R]** — from Reddit's own r/redditdev announcement + TechCrunch. I independently confirmed the *current* state: `.json` → 403, `.rss` → 429 from a datacenter IP **[V]** |
| Apify free plan = $5/mo prepaid credit, no card | **[R]** — read from Apify's pricing page by research |
| Groq free tier (30 RPM, 1,000 RPD, 200 K TPD; Llama models removed from free tier) | **[R]** — read from Groq's docs by research |
| Gemini free-tier model list and rate limits | **[R]** — read from Google's pricing docs by research |
| `nitter` archived 9 Oct 2026 after X Corp C&D | **[R]** — GitHub API was rate-limited when I tried to re-verify |
| Pinterest Trends region buckets include SE+DK+FI+NO and ES | **[R]** — **verify the exact region list before planning Finland coverage around Pinterest.** My Finland strategy also stands on Wikipedia (fi.wikipedia.org) and Trends `geo=FI`, both independently verified working |
| TikTok Creative Center internal API gating behaviour across IP types | **[V]** from this datacenter IP only. Behaviour from a residential IP is unverified |
| Google's "Trend Explorer" CSV/Explore path behaviour | **[R]** — I did **not** test it, because `trendspyg` documents it as rate-limit-sensitive and my RSS-path finding is sufficient. Deliberately untested, not untestable |
| Whether TikTok Creative Center covers Finland among its 27 countries | **Not verified.** Likely **no** (not a target market). Spain likely yes. **This is a real coverage gap for Finland that must be stated plainly in any Finnish-language product claim** |
| `newsnow` API (TrendRadar's upstream hot-list source) | **Could not verify** — Cloudflare challenge from this network |
| RapidAPI aggregate free quotas, ScaleSERP / ZenRows current free tiers | **[R]/[U]** — pricing pages are JS-rendered and timed out. Not load-bearing for any recommendation here |
