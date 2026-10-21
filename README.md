# Trend Intelligence

**Early-warning trend discovery for wellness, hypnosis, therapy, spirituality and personal development.**

A publicly accessible dashboard that surfaces topics people are *beginning* to become
interested in, shows the evidence behind every claim, and tells you exactly which parts
are measured, which are estimated and which are simply not yet knowable.

Live dashboard: **https://trend-intel.netlify.app**

---

## What this is, and what it deliberately is not

| It is | It is not |
|---|---|
| A statistical early-warning system over observed public data | A dashboard of yesterday's viral videos |
| Evidence-linked — every trend shows its original sources | A list of AI-generated guesses |
| Explicit about when it has enough history to make a claim | A predictor claiming to know what goes viral |
| Built on free, keyless, legally accessible sources | A scraper evading platform protections |
| Honest about which platforms it cannot reach | A pretence of TikTok and Instagram coverage |

**The central rule:** a topic without a baseline is reported as *newly observed*, and no
early-detection claim is made for it. No confidence value on this site is produced by a
language model.

---

## The honest constraint

TikTok and Instagram expose **no public trend API**:

- TikTok's Creative Center internal endpoint returns `{"code":40101,"msg":"no permission"}`
  and its trending-*sounds* feed was removed outright (HTTP 404). TikTok's only official
  trend-shaped APIs are the Research API (academic/nonprofit only) and Business API
  (your own account only).
- Instagram's Graph API hashtag search is App-Review-gated, capped at **30 unique hashtags
  per rolling 7 days**, and can only re-query tags you already know. There is no
  trending-hashtag endpoint and no hashtag time series.

So this system detects early interest through **search intent, emerging-concept surfaces
and adjacent social surfaces**, and uses TikTok Creative Center **manually as the baseline
it must beat** rather than as a feed it must parse. That is where the earliest signal
actually lives, and it is legally clean.

The **Source Health** panel on the dashboard states the position of every source in plain
language, including exactly why a platform is unreachable.

---

## Architecture

```
GitHub Actions (public repo, every 2h)      Cloudflare-free, zero compute cost
  ├─ collect   Google Trends (RSS + Trending Now RPC), Google/YouTube
  │            autocomplete, YouTube search (yt-dlp), Wikipedia pageviews,
  │            Mastodon, Reddit RSS, Google News RSS, Europe PMC,
  │            iTunes Podcasts, Hacker News, TikTok Creative Center (best effort)
  ├─ detect    acceleration-weighted momentum, Kleinberg burst onset,
  │            seasonal damp, evidence-derived confidence
  ├─ validate  lead time vs manual baseline, permutation test, false-positive rate
  └─ publish   data branch (raw file host)  →  dashboard fetches at runtime
                                                        │
                                          Netlify (static, one deploy) ◄────┘
```

**Why Netlify hosts only static files.** Netlify's credit model charges 15 credits per
production deploy and 10 credits per GB-hour of function compute. A dashboard that
redeploys hourly would burn 10,800 credits against a 300-credit monthly budget and pause
the site mid-month. So the site is deployed once and reads live data at runtime from the
raw file host — the Netlify cost is bandwidth only.

**How the observation store persists.** The store exists in two places: the
repository (a durable weekly checkpoint) and the CI cache (a fast per-run
restore). The cache restore is written to a side path and the two copies are
reconciled by collection-cycle count, so a stale cache can never silently roll
the history backwards. The cache is evicted after 7 days of inactivity and is
not a backup; the weekly commit is.

**Why the growth series is indexed by collection cycle, not wall-clock hour.** A cycle is
the natural unit of time for a scheduled collector, and indexing by cycle keeps the
series comparable whether the collector ran twice a day or was restarted mid-window.
Wall-clock timestamps are still recorded on every observation, and used for lead-time
validation.

**Why confidence is derived from evidence.** It is a function of the number of *independent*
corroborating surfaces, observation depth, and whether a baseline exists. A language model
is never asked for a number.

---

## The emergence model

> A trend is a change in the rate of change of a concept's visibility — not its
> volume. Popularity and emergence are different questions, and this system
> answers them separately.

The first version of the scorer summed percentile ranks across seven components.
That was wrong, and the data showed it: **meditation, burnout, anxiety and
mindfulness topped the "emerging" list**, because a large topic is above the median
on almost every measure and the sum of eight medians is not a signal. It was a
popularity ranking wearing an early-detection label.

The current model fixes it in four ways.

### 1. The series is a *share*, not a count

The collector's coverage grows over time — more channels, more categories, more
seeds — so every concept's raw count drifts upward together. A raw count therefore
measures the collector, not the topic.

Each concept's volume is divided by the number of distinct sources that fed it
(so switching a new source on is not mistaken for growth), and then by the cycle's
total activity (so expanding coverage cancels out). What remains is a **share of
what the system observed**.

Acceleration is then a **log-ratio change**, the only formulation that stays
meaningful across the five orders of magnitude the share spans. A topic whose
share grew 2 % per cycle is not emerging, no matter where it sits in the cohort.

### 2. Growth and confirmation multiply, they do not add

A topic with ten sources and no growth is not emerging. A topic with real growth
and one source is unconfirmed. Only a product expresses that:

```
emergence = 100 x growth x (0.25 + 0.75 x confirmation) x (1 + 0.15 x discovery_bonus)
```

`growth` blends absolute acceleration with **new search phrasings** — a phrasing
that has never been seen before is demand forming before there is content to serve
it, and it is the earliest marker available without a paid API. `confirmation`
counts **independent families** (search demand, conversation, published video,
research, reference works, editorial, podcast), not raw source count: two surfaces
that both reflect the same index are not two confirmations.

### 3. Maturity is a separate classification, not a score

Every topic gets one of: `new`, `emerging`, `accelerating`, `established`,
`mature`, `fading`, `recurring`, `steady`.

**Established** means large *and* flat — big and calm is the definition of
already-established. Those topics appear in their own dashboard section, clearly
separated, precisely so you can see that they were *excluded* from the emerging
list. A large topic can be popular and still be flat; conflating the two is the
failure mode this project exists to avoid.

### 4. "Emerging" requires corroboration

The gate requires either two independent families **or** a burst of new search
phrasings alongside a second family. A topic moving on one surface is not
corroborated, and calling it emerging inflates the count with single-surface
noise. This is also precisely the part a manual check cannot do, because a person
scrolling one platform has only one surface in view.

### Five properties that make it defensible

1. **No absolute engagement threshold.** Every comparison is against the concept's
   own trailing baseline.
2. **A baseline is mandatory.** Below six collection cycles, no growth statistic is
   computed at all.
3. **Seasonality is subtracted.** Topics in this vertical have a strong annual
   cycle (sleep, burnout and stress all peak in winter). Without this, every
   January would produce a false "emerging trend" wave.
4. **Source changes are damped.** If the set of sources feeding a concept changed
   sharply between windows, the apparent growth is a change in instrumentation,
   not in the world; the score is damped and the fact is recorded.
5. **The validator replays the production detector.** `tools/validate.py` imports
   the same `detect` module and the same `pipeline.build_buckets` that run in
   production, and replays them cycle by cycle over the archived history. A
   harness that measured a different detector would be measuring nothing.

---

## Evidence tiers

Every topic carries a curated tier so a practitioner can tell a clinically supported
method from a spiritual framing from an unsupported claim:

| Tier | Meaning |
|---|---|
| **Established** | Clinically supported method with a meaningful evidence base |
| **Emerging research** | Promising but limited or preliminary evidence |
| **Adjacent / lifestyle** | Plausible wellness practice, not a clinical treatment |
| **Spiritual / interpretive** | Meaning-making or energetic framing, not a medical intervention |
| **Unsubstantiated claim** | Claims that exceed what the evidence supports |

Content angles are screened so they cannot imply a cure, a guaranteed outcome or a
replacement for professional care. `quantum hypnosis`, `QHHT` and `quantum healing
hypnosis technique` are tiered *unsubstantiated* and their angles are constrained
accordingly. This is a product requirement, not a nice-to-have: the platform operates
next to therapy and hypnosis, where the reputational downside of a bad claim is
asymmetric.

Related-but-distinct concepts are never collapsed. *Nervous system regulation*,
*somatic healing* and *emotional regulation* overlap without being identical, and the
dashboard shows the relationship rather than merging them.

---

## Sources

| Source | Status | Legal basis | Cadence |
|---|---|---|---|
| Google Trends — Trending Now (full RPC) | live | public web UI | every cycle |
| Google Trends — daily RSS | live | public RSS | every cycle |
| Google Autocomplete | live | keyless public endpoint | rotating seeds |
| YouTube Autocomplete (weighted) | live | keyless public endpoint | rotating seeds |
| YouTube search (yt-dlp, date-ordered) | live | public search surface | rotating queries |
| Wikipedia pageviews | live | Wikimedia API, polite pool | rotating articles |
| Google News RSS (24 h window) | live | public RSS | rotating queries |
| Europe PMC | live | open API | every cycle |
| **PubMed counts (year over year)** | live | NCBI E-utilities, 3 req/s | rotating topics |
| **arXiv preprints** | live | public API | rotating topics |
| **Mastodon hashtag search** | live | public API | rotating topics |
| **Lemmy search** | live | public instance API | rotating topics |
| iTunes / Apple Podcasts | live | public iTunes API | every cycle |
| Hacker News (Algolia) | live | public API | every cycle |
| **Reddit rising / top-week RSS** | live | public RSS | rotating sorts |
| **YouTube channel RSS** (upload velocity) | live | public per-channel feed | every cycle |
| **Wikipedia category watch** (new articles) | live | Wikimedia API, polite pool | rotating categories |
| Mastodon trends | live | public API | every cycle |
| Reddit subreddit RSS | live, **degrading** | public RSS; **ends 13 Nov 2026** | rotating, rate limited |
| TikTok Creative Center | **blocked** | no public API | attempted, reported honestly |
| Instagram hashtag search | **awaiting authorisation** | App Review + Public Content Access | inert until a token exists |
| Threads keyword search | **awaiting authorisation** | App Review for `threads_keyword_search` | inert until a token exists |
| Pinterest Trends | **awaiting authorisation** | Standard access review | inert until a token exists |
| **Brave Search API** | **disabled by default** | needs a key | code kept, dormant |
| **YouTube Data API** | **disabled by default** | needs a key | code kept, dormant |
| **Instagram / Threads / Pinterest** | **disabled by default** | need App Review | code kept, dormant |
| Google Books | **blocked** | shared project quota exhausted without a key | not used |

The five authorisation-gated integrations are **disabled in configuration** rather
than deleted. Their code is complete and tested; set `TREND_ENABLE_KEYED=1` and
supply the matching credential and they start contributing on the next cycle. Until
then they report themselves as "awaiting authorisation" so their absence is visible
rather than silent.

### Why PubMed counts matter

It is the one signal in the system with a baseline the collector does not have
to build. The research literature's own year-over-year movement is an external
measure of whether a topic is genuinely emerging — a topic whose paper count
goes 4 → 19 → 31 across three years is growing research attention whether or
not anyone was watching it. Stored as a growth ratio, so a sustained rise is a
trend in its own right.

### Why Brave is worth a key

Google's own autocomplete endpoint ignores the country parameter — you can
only localise by language. Brave's API takes `country=` directly, which is the
fix for genuine Finland- and Spain-level targeting. Its free tier includes a
recurring monthly credit.

Those adapters are **implemented and wired**, not aspirational. Supply a
credential and they start contributing on the next cycle:

```bash
export INSTAGRAM_ACCESS_TOKEN=...   # + IG_USER_ID
export THREADS_ACCESS_TOKEN=...
export PINTEREST_ACCESS_TOKEN=...
export BRAVE_API_KEY=...            # free monthly credit, country-targeted
export YOUTUBE_API_KEY=...          # free 10,000 units/day
```

Until then they report themselves as "awaiting authorisation" in Source
Health, so their absence is visible rather than silent.

### TikTok and Instagram: what is actually possible

Verified against the live platforms on 21 October 2026, from both a datacentre IP
and a residential one, in a real browser:

| Surface | Result |
|---|---|
| `creative_radar_api/v1/popular_trend/hashtag/list` | `40101 no permission` |
| `cc_portal_api/api/trendsTcc` (what the Creative Center page itself calls) | **HTTP 500** for anonymous clients |
| The three hashtags that visibly render | identical across fresh sessions with zero table rows — shipped inside the frontend bundle, **not live data** |
| `tiktok.com/csi` (Creator Search Insights — rising searches) | **302 → 404**; the surface no longer exists |
| `instagram.com/explore/tags/<tag>/` logged off | **302 → login wall** |
| Instagram's internal `topsearch` endpoints | 404 |

**Instagram is officially possible** and the adapter is built. It needs a Meta app
with `instagram_basic`, the **Instagram Public Content Access** feature, App Review,
a Business/Creator account and Business Verification. Meta's own limit shapes the
design: **30 unique hashtags per rolling 7 days**, and re-querying a tag already
inside that window is free — so the collector tracks the budget locally
(`store.ig_budget_status`) and spends it deliberately.

The tag queue is seeded **discovery-first**: topics the other sources just found,
then corroborated topics, then the curated seed list. That ordering matters,
because Instagram cannot discover trends. The useful question to ask it is *"how
big is the audience for the thing we found elsewhere?"* — which turns a
discovery-only source into a size-confirmation source.

**TikTok has no automated public trend data**, so the system uses a
**human-in-the-loop capture** instead: you look at Creative Center in your own
logged-in session, and the system does the part a human cannot — timestamp the
observation and track the topic's growth over time, with the same baseline and
acceleration treatment as every other source.

```bash
# paste from the browser, or use the Capture tab on the dashboard
python -m collector.capture --clipboard --source tiktok
python -m collector.capture --file trending.txt
```

The dashboard's Capture tab does the same thing without a backend: it copies the
hashtags to your clipboard and offers a JSON file, because Netlify Forms turned
out to be unavailable on this account (verified with a minimal probe form — even
a textbook-correct one was not detected).

**What this system will not do:** defeat a CAPTCHA, forge a request signature, solve a
challenge, or use a residential proxy to defeat a WAF. Those are access-control
circumvention, and they convert a technical problem into a legal one for a business that
sits next to therapy and hypnosis.

---

## Beating manual browsing

The question that matters: **is this actually ahead of someone checking TikTok
Creative Center and Instagram by hand?**

The honest answer, measured by replaying the production detector over the archived
history, is on the dashboard's **Validation** panel and the new **Manual Baseline**
panel, which shows what the manual surfaces are listing *right now* alongside what
the system is calling emerging.

The manual baseline is Reddit's own `rising` and `top` rankings plus Google's
trending list, captured continuously rather than occasionally. Reddit's `rising`
feed is the closest keyless equivalent of the Creative Center list: a platform's own
algorithmic "this is taking off" ranking, driven by engagement velocity.

The structural advantage comes from what the system can see that a person cannot:
a topic's **share** of everything observed, its **rate of change** against its own
baseline, **new search phrasings** appearing before there is content to serve them,
**independent families** agreeing, and **upload velocity** of creators it watches
continuously. A person scrolling one platform has one surface in view and no
history.

**Current measurement, stated plainly:** with 30 collection cycles the comparison
is not yet conclusive. Early in a run's history the cohort is small and the
relative-share series is still settling, which produces unreliable early
classifications; and topics that were already on Reddit's list in the first cycle
could not have been beaten by definition. The harness reports the number either
way and refuses to claim more than the data supports.

## Content translation

Every topic with observed demand gets a per-channel angle derived from what was
actually seen: the short-form video hook is built from the **exact phrasing people
are searching for**, the carousel from the **spread of phrasings**, and the
website article from the **questions being asked**. The framing line is governed
by the curated evidence tier, so `quantum healing hypnosis technique` gets
"explain what the concept is and where the claims come from, without endorsing
them", while an established method gets "present it with the research attached".
Every angle passes through the medical-claim filter, and a topic with no observed
demand is told there is no signal to write against yet.

## Validation

`python -m tools.validate` answers three questions with data rather than opinion:

1. **Lead time** — when did we first detect a topic, versus when it appeared on the
   surfaces a human checks manually? Reported as a distribution, not a single number.
2. **Is the signal real?** — Kleinberg's **permutation test**: shuffle the observation
   stream so arrival times no longer correspond to content, rebuild the series, re-run
   the detector. If the shuffled corpus still produces "trends", the signal is an
   artefact of the collection schedule.
3. **False positives** — what fraction of flagged topics never reached a baseline surface.

With less than three weeks of history the harness prints **"NOT YET MEASURABLE"** rather
than a fabricated precision figure. That is the intended behaviour.

---

## Running it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m collector.run              # full cycle
.venv/bin/python -m collector.run --quick      # reduced budget, for testing
.venv/bin/python -m tools.validate             # run the validation harness
```

### Layout

```
collector/
  ontology.py   curated concepts, aliases, evidence tiers, safety filter
  concepts.py   surface text -> canonical concept, with evidence weighting
  sources.py    one collector per source, honest failures
  detect.py     velocity, acceleration, burst onset, confidence, lifecycle
  store.py      SQLite observation store + durable daily aggregates
  run.py        orchestrator
tools/validate.py   lead time, permutation test, false-positive rate
tools/reconcile.py  picks the more advanced of the cached and stored copies
web/                 the static dashboard (no build step)
```

---

## Operating it

- **Schedule:** GitHub Actions, `23 */2 * * *` — deliberately off the top of the hour,
  because GitHub's scheduler congests on the hour and drops queued jobs.
- **Cost:** $0. Public repositories get unlimited free runner minutes. No card, no
  paid tier, no API keys required for any working source.
- **Data ownership:** every observation is timestamped and stored. The durable history is
  a set of daily aggregates in `data/series.json` — small, diff-friendly, and yours.
- **LLM enrichment is optional.** With a `GROQ_API_KEY`, `GEMINI_API_KEY` or
  `TREND_LLM_API_KEY` set, the system adds a short narrative note per topic. The note is
  labelled as generated prose and never carries a measurement. With no key, everything
  else works identically.

---

## Known limitations

1. **No TikTok or Instagram signal.** By platform policy, not by omission. Where the
   dashboard shows nothing for those, that is the answer.
2. **Google Trends' global trending list is general-interest.** A wellness topic
   appearing on it is a strong breakout signal precisely because it is rare — 570 US
   trends in 24 h typically contain zero or one wellness term. The vertical-specific
   signal comes from autocomplete and the concept surfaces.
3. **Google's own autocomplete cannot be localised by country** — only by language.
   `gl=` is ignored; `hl=` works. Country-level targeting needs a keyed search API.
4. **Reddit is ending.** Public RSS stops on 13 November 2026 and public API access
   closes in March 2027. The source is expected to degrade and is reported as such.
5. **No accuracy claim is possible yet.** Lead time cannot honestly be measured until
   weeks of history exist. The validation harness says so.
6. **Discovery is bounded by the seed list.** New topics are found by matching observed
   text against the vertical ontology and discovery lexicon; a topic using entirely
   novel vocabulary will be missed until someone adds it to the ontology.
