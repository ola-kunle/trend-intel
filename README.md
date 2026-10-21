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

**Why the growth series is indexed by collection cycle, not wall-clock hour.** A cycle is
the natural unit of time for a scheduled collector, and indexing by cycle keeps the
series comparable whether the collector ran twice a day or was restarted mid-window.
Wall-clock timestamps are still recorded on every observation, and used for lead-time
validation.

**Why confidence is derived from evidence.** It is a function of the number of *independent*
corroborating surfaces, observation depth, and whether a baseline exists. A language model
is never asked for a number.

---

## Scoring

```
momentum_score = 100 × Σ wᵢ · percentileᵢ(concept, cohort) × seasonal_damp
```

| Component | Weight | What it measures |
|---|---|---|
| `acceleration` | 26% | change in the growth rate — what separates "gaining" from "already popular" |
| `velocity` | 16% | change in volume against the concept's own prior rate |
| `burst_onset` | 16% | Kleinberg-style change point on the concept's series |
| `cross_source` | 14% | number of independent surfaces carrying the topic |
| `creator_diversity` | 12% | growth in the number of *distinct* creators touching the topic |
| `relevance` | 10% | distance from the vertical's concept ontology |
| `evidence_volume` | 6% | total corroborated evidence |

Four properties make this defensible rather than arbitrary:

1. **No absolute engagement threshold.** Every comparison is against the concept's own
   trailing baseline.
2. **A baseline is mandatory.** Below four collection cycles, no growth statistic is
   computed at all.
3. **Seasonality is subtracted.** Topics in this vertical have a strong annual cycle
   (sleep, burnout and stress all peak in winter). Without this, every January would
   produce a false "emerging trend" wave.
4. **Percentile normalisation, not thresholds.** A score means "how unusual is this
   relative to what we are currently watching", which is the question that is actually
   being asked.

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
| iTunes / Apple Podcasts | live | public iTunes API | every cycle |
| Hacker News (Algolia) | live | public API | every cycle |
| Mastodon trends | live | public API | every cycle |
| Reddit subreddit RSS | live, **degrading** | public RSS; **ends 13 Nov 2026** | rotating, heavily rate limited |
| TikTok Creative Center | **blocked** | no public API | attempted, reported honestly |
| Instagram hashtag search | **awaiting authorisation** | App Review + Public Content Access | inert until a token exists |
| Threads keyword search | **awaiting authorisation** | App Review for `threads_keyword_search` | inert until a token exists |
| Pinterest Trends | **awaiting authorisation** | Standard access review | inert until a token exists |

The last three adapters are **implemented and wired**, not aspirational. Supply a token
and they start contributing on the next cycle:

```bash
export INSTAGRAM_ACCESS_TOKEN=...   # + IG_USER_ID
export THREADS_ACCESS_TOKEN=...
export PINTEREST_ACCESS_TOKEN=...
```

**What this system will not do:** defeat a CAPTCHA, forge a request signature, solve a
challenge, or use a residential proxy to defeat a WAF. Those are access-control
circumvention, and they convert a technical problem into a legal one for a business that
sits next to therapy and hypnosis.

---

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
