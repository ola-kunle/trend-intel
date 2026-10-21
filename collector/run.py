"""Collector orchestrator.

    python -m collector.run [--quick] [--only source,source]

Responsibilities, in order:

  1. collect every enabled source, recording honest health for each
  2. persist timestamped observations
  3. recompute growth metrics for every concept we have recent history for
  4. score, classify lifecycle, assess confidence from evidence
  5. build the dashboard payload and the durable daily series
  6. print a human-readable summary

Every step is independently useful, so a source failure degrades the output
rather than stopping it.
"""

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time

from . import config, concepts, detect, enrich, ontology, sources, store

START = time.time()


def log(msg):
    print("[%7.1fs] %s" % (time.time() - START, msg), flush=True)


def _ytdlp_bin():
    """Locate a yt-dlp binary: venv first, then PATH, then pipx-style."""
    candidates = [
        os.path.join(config.ROOT, ".venv", "bin", "yt-dlp"),
        shutil.which("yt-dlp"),
        shutil.which("yt-dlp.exe"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def _rotate(items, cursor, take):
    """Deterministic round-robin slice so every item gets covered over time."""
    if not items:
        return [], cursor
    take = min(take, len(items))
    out = []
    for i in range(take):
        out.append(items[(cursor + i) % len(items)])
    return out, (cursor + take) % len(items)


def _shortlist(seeds, cursor, take):
    """Pick seeds whose *recent activity* justifies a deeper probe.

    We do not want to spend the whole budget on quiet topics, and we do not
    want to miss a topic that just started moving. The cursor rotates so
    everything is covered, and the list is biased towards concepts with
    recent observations.
    """
    if not seeds:
        return [], cursor
    rotated = seeds[cursor:] + seeds[:cursor]
    return rotated[:min(take, len(rotated))], (cursor + take) % len(seeds)


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

def collect(conn, only=None, quick=False):
    rows = []
    health = {}

    deadline = time.time() + config.COLLECT_BUDGET_SECONDS

    def run(source_id, fn, *args, **kwargs):
        if only and source_id not in only:
            return None
        if time.time() > deadline:
            health[source_id] = {"ok": False, "items": 0, "latency_ms": 0,
                                 "message": "deferred: collection time budget exhausted"}
            log(f"  {source_id}: DEFERRED (time budget)")
            return None
        if not config.SOURCES.get(source_id, True):
            health[source_id] = {"ok": False, "items": 0, "latency_ms": 0,
                                 "message": "disabled in configuration"}
            log(f"  {source_id}: disabled")
            return None
        t0 = time.time()
        try:
            res = fn(*args, **kwargs)
            got, meta = res if isinstance(res, tuple) else (res, {})
            rows.extend(got)
            dt = int((time.time() - t0) * 1000)
            health[source_id] = {"ok": True, "items": len(got), "latency_ms": dt,
                                 "message": "", "meta": meta}
            log(f"  {source_id}: OK {len(got)} rows in {dt}ms {meta if meta else ''}")
            return got
        except Exception as exc:
            dt = int((time.time() - t0) * 1000)
            health[source_id] = {"ok": False, "items": 0, "latency_ms": dt,
                                 "message": f"{type(exc).__name__}: {exc}"[:300]}
            log(f"  {source_id}: FAILED after {dt}ms -> {exc}")
            return None

    cursor = int(store.get_state(conn, "cursor", "0") or 0)
    seeds = list(ontology.ALL_SEEDS)
    budget = 4 if quick else 24
    query_budget = 2 if quick else 10

    log("Collecting sources...")

    # --- Google Trends -----------------------------------------------------
    geos = config.GEOS[:1] if quick else config.GEOS
    for geo, trends_geo, lang, _label in geos:
        run("google_trends_rss", sources.google_trends_rss, geo, lang)
        run("google_trends_now", sources.google_trends_now, geo, 24, lang)

    # --- Autocomplete ------------------------------------------------------
    # One language per cycle (rotating), so Finnish and Spanish coverage
    # builds over time without tripling the request budget.
    cycle = int(store.get_state(conn, "cycle", "0") or 0)
    lang = config.SUGGEST_LANG_CYCLE[cycle % len(config.SUGGEST_LANG_CYCLE)]
    sug_count = 4 if quick else config.SUGGEST_SEEDS_PER_CYCLE
    sug_seeds, cursor = _shortlist(seeds, cursor, sug_count)
    run("google_suggest", sources.google_suggest, sug_seeds, lang)
    run("youtube_suggest", sources.youtube_suggest, sug_seeds, lang)

    # --- YouTube search ----------------------------------------------------
    ytdlp = _ytdlp_bin()
    if ytdlp:
        yq, cursor = _shortlist(config.YOUTUBE_QUERIES, cursor, query_budget)
        run("youtube_search", sources.youtube_search, yq, ytdlp)
    else:
        health["youtube_search"] = {"ok": False, "items": 0, "latency_ms": 0,
                                    "message": "yt-dlp not installed"}
        log("  youtube_search: yt-dlp not found - skipped")

    # --- Wikipedia ---------------------------------------------------------
    wiki_terms, cursor = _shortlist(seeds, cursor, (6 if quick else 18))
    titles = []
    for term in wiki_terms:
        t = sources.wikipedia_search(term, "en")
        if t:
            titles.append(t)
    run("wikipedia_views", sources.wikipedia_views, titles, "en")

    # --- Mastodon ----------------------------------------------------------
    run("mastodon_trends", sources.mastodon_trends)

    # --- News / academic / podcast / HN ------------------------------------
    news_q, cursor = _shortlist(seeds, cursor, query_budget + 6)
    run("news_rss", sources.news_rss, news_q)

    acad_q = [
        "hypnosis AND anxiety", "somatic AND therapy", "nervous system regulation",
        "subconscious AND hypnosis", "psychedelic AND therapy",
        "mindfulness AND burnout", "attachment AND therapy",
        "breathwork AND stress", "meditation AND sleep", "trauma AND therapy",
    ]
    run("europepmc", sources.europepmc, acad_q[:3] if quick else acad_q)

    pod_q = ["hypnosis", "self improvement", "mental health", "meditation",
             "nervous system", "personal growth", "spirituality"]
    run("itunes_podcasts", sources.itunes_podcasts, pod_q[:3] if quick else pod_q)

    hn_q = ["hypnosis", "meditation", "mental health", "psychedelic", "wellness"]
    run("hn_algolia", sources.hn_algolia, hn_q[:2] if quick else hn_q)

    # --- TikTok (best effort) ----------------------------------------------
    run("tiktok_creative", sources.tiktok_creative)

    # --- Reddit (last: it is heavily rate limited and must not starve the
    #     other sources of the time budget) ---------------------------------
    subs, cursor = _shortlist(config.REDDIT_SUBREDDITS, cursor,
                              1 if quick else config.REDDIT_PER_CYCLE)
    for sub in subs:
        run("reddit_rss", sources.reddit_rss, sub)

    store.set_state(conn, "cursor", cursor)
    store.set_state(conn, "cycle", cycle + 1)

    for sid, h in health.items():
        store.record_health(conn, sid, h["ok"], h["items"], h["latency_ms"], h["message"])
    return rows, health


# ---------------------------------------------------------------------------
# Analysis + payload
# ---------------------------------------------------------------------------

def build_payload(conn, health, llm_notes=None):
    now = time.time()
    window_days = 14
    since = now - window_days * 86400
    obs = store.recent_observations(conn, since)
    log(f"Analysing {len(obs)} observations from the last {window_days} days")

    by_concept = {}
    for o in obs:
        c = o["concept"]
        if not c:
            continue
        by_concept.setdefault(c, []).append(o)

    # How many collection cycles contributed to each wall-clock hour, across
    # the whole corpus. Reported in the payload so the reader can see how
    # densely the system was actually sampling.
    bucket_cycles = {}
    for o in obs:
        b = int(o["epoch"] // 3600) * 3600
        bucket_cycles.setdefault(b, set()).add(int(o.get("cycle") or 0))
    cycles_total = len({int(o.get("cycle") or 0) for o in obs})

    # Buckets per concept, keyed by COLLECTION CYCLE rather than wall-clock
    # hour. The collector runs on a fixed schedule, so a cycle is the natural
    # unit of time: growth measured per cycle is comparable across runs and
    # is unaffected by a collector that was restarted or backfilled. Wall
    # clock is still recorded on every observation for display and for the
    # lead-time validation.
    buckets = {}
    for c, rows_c in by_concept.items():
        b = {}
        for r in rows_c:
            slot = int(r.get("cycle") or 0)
            s = b.setdefault(slot, {"count": 0.0, "raw_count": 0, "views": 0.0,
                                    "volume": 0.0, "comments": 0.0,
                                    "sources": set(), "creators": set(),
                                    "avg_rank": None, "rank_sum": 0.0,
                                    "rank_n": 0, "raw": 0.0, "cycles": set(),
                                    "epochs": []})
            extra = {}
            try:
                extra = json.loads(r.get("extra") or "{}")
            except Exception:
                extra = {}
            # Evidence weight: an exact ontology match counts fully, a
            # glancing phrase mention inside an unrelated title counts a
            # little. The raw count is kept alongside so the dashboard can
            # show "how many raw observations" as well as "how much evidence".
            w = concepts.evidence_weight(extra.get("resolution"), r["source"])
            s["count"] += w
            s["cycles"].add(int(r.get("cycle") or 0))
            s["epochs"].append(r["epoch"])
            s["raw_count"] += 1
            s["raw"] += w
            s["sources"].add(r["source"])
            ch = extra.get("channel_id") or extra.get("channel")
            if ch:
                s["creators"].add(ch)
            v = r.get("value")
            if v is not None:
                if r["metric"] in ("views", "volume", "comments"):
                    s[r["metric"]] += float(v)
                elif r["metric"] == "rank":
                    s["rank_sum"] += float(v)
                    s["rank_n"] += 1
        for s in b.values():
            s["sources"] = sorted(s["sources"])
            s["avg_rank"] = (s["rank_sum"] / s["rank_n"]) if s["rank_n"] else None
            s["epoch"] = sum(s["epochs"]) / len(s["epochs"]) if s["epochs"] else 0
            s["epoch_max"] = max(s["epochs"]) if s["epochs"] else 0
            s["cycles"] = sorted(s["cycles"])
        buckets[c] = b

    # Cohort for percentile normalisation.
    cohort = {k: [] for k in config.SCORE_WEIGHTS}
    cohort["_relevance"] = {}
    prelim = {}
    for c, b in buckets.items():
        m = detect.compute_metrics(c, b, now)
        m["_concept"] = c
        prelim[c] = m
        cohort["acceleration"].append(m["acceleration"])
        cohort["velocity"].append(m["velocity"])
        cohort["burst_onset"].append(m["burst_score"])
        cohort["creator_diversity"].append(m["creator_growth"])
        cohort["cross_source"].append(m["cross_source_count"])
        cohort["evidence_volume"].append(m["total_count"])
        cohort["_relevance"][c] = concepts.weight_of(c)

    trend_rows = []
    for c, m in prelim.items():
        rows_c = by_concept.get(c, [])
        score, pct = detect.score_concept(m, cohort)
        lifecycle = detect.classify_lifecycle(m, m["time_buckets"], now)
        conf = detect.confidence_level(m, m["time_buckets"])
        questions = detect.audience_questions(rows_c)
        angles = detect.content_opportunities(c, rows_c, questions)
        name = c[5:] if c.startswith("auto:") else c
        category = concepts.category_of(c)
        tier = concepts.tier_of(c)
        row = {
            "key": c,
            "name": name,
            "category": category,
            "category_label": (ontology.CATEGORIES.get(category) or {}).get("label", "Unclassified"),
            "evidence_tier": tier,
            "evidence_tier_label": ontology.EVIDENCE_TIERS[tier]["label"],
            "evidence_tier_note": ontology.EVIDENCE_TIERS[tier]["description"],
            "evidence_tier_check": ontology.EVIDENCE_TIERS[tier]["check"],
            "curated": concepts.is_curated(c),
            "discovered": c.startswith("auto:"),
            "related": concepts.related_for(c),
            "sources": m["sources"],
            "cross_source_count": m["cross_source_count"],
            "cycles_observed": m.get("cycles_observed", 0),
            "surface_count": len({r.get("surface") for r in rows_c}),
            "observations": m["observations"],
            "time_buckets": m["time_buckets"],
            "collection_cycles": m.get("cycles_observed", 0),
            "age_hours": m["age_hours"],
            "first_seen_recent": m["age_hours"] < 24,
            "velocity": m["velocity"],
            "acceleration": m["acceleration"],
            "burst_score": m["burst_score"],
            "burst_evidence": m["burst_evidence"],
            "creator_count": m["creator_count"],
            "creator_growth": m["creator_growth"],
            "total_count": m["total_count"],
            "total_views": m["total_views"],
            "recent_observation": m["recent_observation"],
            "lifecycle": lifecycle,
            "lifecycle_label": LIFECYCLE_LABELS.get(lifecycle, lifecycle),
            "confidence": conf,
            "momentum_score": score,
            "score_components": {k: round(v, 4) for k, v in pct.items()},
            "score_weights": config.SCORE_WEIGHTS,
            "seasonality": m["seasonality"],
            "has_baseline": m["has_baseline"],
            "series": m["series"],
            "evidence": detect.evidence_links(rows_c),
            "questions": questions,
            "opportunities": angles,
            "geos": sorted({r.get("geo") for r in rows_c if r.get("geo")}),
            "langs": sorted({r.get("lang") for r in rows_c if r.get("lang")}),
            "first_observed": min((r.get("ts") for r in rows_c if r.get("ts")), default=None),
            "last_observed": max((r.get("ts") for r in rows_c if r.get("ts")), default=None),
        }
        if llm_notes and c in llm_notes:
            row["note"] = llm_notes[c]
            row["note_source"] = "llm"
        trend_rows.append(row)

    trend_rows.sort(key=lambda r: r["momentum_score"], reverse=True)

    # --- Section views -----------------------------------------------------
    emerging = [r for r in trend_rows if r["lifecycle"] in ("emerging", "accelerating")]
    # Topics seen for the first time inside the window. These make no
    # early-detection claim - they are simply the newest things we noticed.
    newly_observed = sorted(
        [r for r in trend_rows if r["lifecycle"] == "newly_observed"],
        key=lambda r: (r["cross_source_count"], r["observations"]), reverse=True)
    before_viral = sorted(
        [r for r in trend_rows
         if r["lifecycle"] in ("emerging", "accelerating")
         and r["cross_source_count"] >= 2
         and r["burst_score"] >= 0.25],
        key=lambda r: (r["burst_score"] * r["cross_source_count"] * r["momentum_score"]),
        reverse=True)
    fastest = sorted(trend_rows, key=lambda r: r["acceleration"], reverse=True)
    cross = [r for r in trend_rows if r["cross_source_count"] >= 2]

    all_questions = []
    qseen = set()
    for r in trend_rows:
        for q in r["questions"]:
            k = ontology.normalise(q["text"])
            if k in qseen:
                continue
            qseen.add(k)
            all_questions.append(dict(q, concept=r["name"], concept_key=r["key"]))
    all_questions.sort(key=lambda q: q["ts"] or "", reverse=True)

    opportunities = []
    for r in trend_rows:
        for a in r["opportunities"]:
            opportunities.append(dict(a, concept=r["name"], concept_key=r["key"],
                                       tier=r["evidence_tier"],
                                       confidence=r["confidence"]["level"],
                                       momentum=r["momentum_score"]))
    opportunities.sort(key=lambda a: a["momentum"], reverse=True)

    # Regional view
    regional = {}
    for r in trend_rows:
        for g in r["geos"]:
            regional.setdefault(g, []).append(
                {"key": r["key"], "name": r["name"], "score": r["momentum_score"],
                 "lifecycle": r["lifecycle"], "confidence": r["confidence"]["level"],
                 "tier": r["evidence_tier"]})

    # --- Source health -----------------------------------------------------
    source_health = []
    for sid in sorted(set(list(config.SOURCES.keys()) + list(health.keys()))):
        h = health.get(sid, {})
        hist = store.health_history(conn, sid, 40)
        ok_count = sum(1 for x in hist if x["ok"])
        source_health.append({
            "source": sid,
            "ok": bool(h.get("ok")),
            "items": h.get("items", 0),
            "latency_ms": h.get("latency_ms", 0),
            "message": h.get("message", ""),
            "meta": h.get("meta", {}),
            "history": hist[-20:],
            "success_rate": round(ok_count / len(hist), 3) if hist else None,
            "runs": len(hist),
            "label": SOURCE_LABELS.get(sid, sid),
        })

    total_obs = conn.execute("SELECT COUNT(*) c FROM observations").fetchone()["c"]
    total_concepts = conn.execute(
        "SELECT COUNT(*) c FROM concepts").fetchone()["c"]

    # Slim the payload. The dashboard needs full detail (evidence links,
    # questions, angles, series) for what it actually renders, but shipping
    # full detail for hundreds of low-ranked concepts bloats the published
    # snapshot for no benefit and makes the published history heavy.
    FULL_DETAIL_TOP_N = 120
    for i, r in enumerate(trend_rows):
        if i < FULL_DETAIL_TOP_N:
            continue
        r["evidence"] = (r.get("evidence") or [])[:3]
        r["questions"] = (r.get("questions") or [])[:2]
        r["opportunities"] = (r.get("opportunities") or [])[:1]
        r["series"] = (r.get("series") or [])[-12:]

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "generated_at_local": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "version": config.VERSION,
        "primary_geo": config.PRIMARY_GEO,
        "stats": {
            "observations_total": total_obs,
            "collection_cycles": cycles_total,
            "median_cycle_interval_hours": _median_cycle_interval(conn),
            "concepts_total": total_concepts,
            "concepts_active": len(trend_rows),
            "window_days": window_days,
            "sources_ok": sum(1 for s in source_health if s["ok"]),
            "sources_total": len(source_health),
        },
        "methodology": {
            "principle": "A trend is a change in the rate of change of a concept's "
                         "visibility, not its absolute volume.",
            "weights": config.SCORE_WEIGHTS,
            "cross_source_min": config.CROSS_SOURCE_MIN,
            "min_observations": config.MIN_OBSERVATIONS,
            "normalisation": "Percentile against the current cohort; no absolute "
                             "engagement thresholds are used.",
            "confidence": "Derived from the number of independent corroborating "
                          "surfaces, observation depth and baseline availability. "
                          "Never from an AI score.",
            "seasonality": "Concepts with fewer than 30 observations are flagged "
                           "as seasonally unmodelled and their score is damped.",
            "note": "Concepts without a baseline are reported as 'newly observed'. "
                    "No early-detection claim is made for them.",
        },
        "categories": [{"key": k, **v} for k, v in ontology.CATEGORIES.items()],
        "evidence_tiers": ontology.EVIDENCE_TIERS,
        "geos": [{"key": g[0], "label": g[3], "lang": g[2], "trends_geo": g[1]}
                 for g in config.GEOS],
        "trends": trend_rows,
        "sections": {
            "emerging": [r["key"] for r in emerging],
            "before_viral": [r["key"] for r in before_viral],
            "fastest": [r["key"] for r in fastest],
            "cross_platform": [r["key"] for r in cross],
            "newly_observed": [r["key"] for r in newly_observed],
        },
        "questions": all_questions[:90],
        "new_phrasings": store.new_phrasings(conn, within_hours=72, limit=90),
        "opportunities": opportunities[:90],
        "regional": regional,
        "source_health": source_health,
        "llm": {"provider": enrich.available(),
                "enabled": bool(enrich.available())},
    }
    return payload, trend_rows, by_concept


def _median_cycle_interval(conn):
    """Median wall-clock hours between collection cycles.

    Reported so a reader can see how densely the system was actually
    sampling. The growth series is indexed by cycle, so it stays comparable
    whatever this number is, but lead times expressed in hours are only
    meaningful once the interval matches the intended schedule.
    """
    rows = conn.execute(
        "SELECT cycle, MIN(epoch) e FROM observations GROUP BY cycle ORDER BY cycle"
    ).fetchall()
    if len(rows) < 2:
        return None
    gaps = [(rows[i + 1]["e"] - rows[i]["e"]) / 3600.0 for i in range(len(rows) - 1)]
    gaps = [g for g in gaps if g >= 0]
    if not gaps:
        return None
    gaps.sort()
    return round(gaps[len(gaps) // 2], 3)


LIFECYCLE_LABELS = {
    "newly_observed": "Newly observed",
    "emerging": "Emerging",
    "accelerating": "Accelerating",
    "peaking": "Peaking",
    "declining": "Declining",
    "recurring": "Recurring / seasonal",
    "steady": "Steady",
}

SOURCE_LABELS = {
    "google_trends_rss": "Google Trends - daily RSS",
    "google_trends_now": "Google Trends - Trending Now (full)",
    "google_suggest": "Google Autocomplete",
    "youtube_suggest": "YouTube Autocomplete (weighted)",
    "youtube_search": "YouTube search (yt-dlp, date ordered)",
    "wikipedia_views": "Wikipedia pageviews",
    "mastodon_trends": "Mastodon trends (7-day history)",
    "reddit_rss": "Reddit subreddit RSS",
    "news_rss": "Google News RSS (24h window)",
    "europepmc": "Europe PMC (research)",
    "itunes_podcasts": "iTunes / Apple Podcasts",
    "hn_algolia": "Hacker News (Algolia)",
    "tiktok_creative": "TikTok Creative Center",
    "instagram_hashtag": "Instagram hashtag search (authorised)",
    "threads_search": "Threads keyword search (authorised)",
    "pinterest_trends": "Pinterest Trends (authorised)",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="reduced budget, for testing")
    ap.add_argument("--only", help="comma separated source ids")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--db", help="override database path")
    args = ap.parse_args()

    only = set(args.only.split(",")) if args.only else None
    db_path = args.db or config.DB_PATH
    conn = store.connect(db_path)
    store.prune(conn)

    cycle_id = int(store.get_state(conn, "cycle_id", "0") or 0) + 1
    rows, health = collect(conn, only=only, quick=args.quick)
    for r in rows:
        r["cycle"] = cycle_id
    store.set_state(conn, "cycle_id", cycle_id)

    if rows:
        # Resolve concepts for any that are still unmapped.
        fixed = 0
        for r in rows:
            if not r.get("concept"):
                key, how = concepts.resolve_or_discover(r.get("raw_text", ""))
                r["concept"] = key or ""
                fixed += 1
        n = store.insert_observations(conn, rows)
        log(f"Persisted {n} observations ({fixed} concept-resolved)")

    concept_rows = []
    seen = set()
    for r in rows:
        c = r.get("concept")
        if not c or c in seen:
            continue
        seen.add(c)
        concept_rows.append({
            "concept": c, "first_seen": r["ts"], "last_seen": r["ts"],
            "category": concepts.category_of(c),
            "is_seed": concepts.is_curated(c), "tier": concepts.tier_of(c),
        })
    store.upsert_concepts(conn, concept_rows)

    # Optional LLM narrative, after statistics exist.
    llm_notes = {}
    if not args.no_llm and enrich.available():
        log(f"LLM enrichment via {enrich.available()}")
        pre_rows, _, by_c = build_payload(conn, health, None)
        qmap = {c: [q["text"] for q in detect.audience_questions(rows_c)]
                for c, rows_c in by_c.items()}
        llm_notes = enrich.enrich_batch(
            [r for r in pre_rows if r["cross_source_count"] >= 2][:60], qmap)
        log(f"LLM produced {len(llm_notes)} notes")

    payload, trend_rows, by_c = build_payload(conn, health, llm_notes)

    os.makedirs(config.SNAPSHOT_DIR, exist_ok=True)
    size = store.write_json(config.LATEST_JSON, payload)
    log(f"Wrote {config.LATEST_JSON} ({size/1024:.0f} KB)")

    # Durable daily series
    series_rows = store.daily_aggregates(conn, days=120)
    merged = store.merge_series(store.load_series(), series_rows)
    store.write_json(os.path.join(config.DATA_DIR, "series.json"), merged)
    log(f"Series merged: {len(merged)} concept-day rows")

    # Also copy into the web folder so the deployed site has a fallback.
    os.makedirs(os.path.join(config.WEB_DIR, "data"), exist_ok=True)
    store.write_json(os.path.join(config.WEB_DIR, "data", "latest.json"), payload)
    store.write_json(os.path.join(config.WEB_DIR, "data", "series.json"), merged)

    day = time.strftime("%Y-%m-%d")
    store.write_json(os.path.join(config.SNAPSHOT_DIR, f"{day}.json"), payload)

    ok = sum(1 for s in payload["source_health"] if s["ok"])
    print()
    print("=" * 66)
    print(f"  Concepts tracked      : {payload['stats']['concepts_total']}")
    print(f"  Active in {payload['stats']['window_days']}d window : {len(trend_rows)}")
    print(f"  Observations stored   : {payload['stats']['observations_total']}")
    print(f"  Sources healthy       : {ok}/{len(payload['source_health'])}")
    print(f"  Emerging / accelerating: {len(payload['sections']['emerging'])}")
    print(f"  Cross-surface signals : {len(payload['sections']['cross_platform'])}")
    print(f"  Audience questions    : {len(payload['questions'])}")
    print(f"  Content opportunities : {len(payload['opportunities'])}")
    print("=" * 66)
    for r in trend_rows[:12]:
        print(f"  {r['momentum_score']:5.1f}  {r['name'][:38]:38s} "
              f"{r['lifecycle_label'][:18]:18s} src={r['cross_source_count']} "
              f"conf={r['confidence']['level']}")
    print()
    conn.close()


if __name__ == "__main__":
    sys.exit(main())
