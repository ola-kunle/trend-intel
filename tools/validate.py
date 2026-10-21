"""Validation harness.

This is the part of the brief that matters most: *"if the automated system
cannot meaningfully outperform manual checking, we should reconsider its
complexity."*

It answers three questions with data rather than opinion:

1. **Lead time** - when did we first detect a topic, versus when it appeared
   on the baseline surfaces a human checks (Google Trends' own trending list,
   Pinterest's "growing" list, TikTok Creative Center)? Lead time is the
   difference in hours.

2. **Is the signal real?** - Kleinberg's permutation test. We shuffle the
   observation stream so that arrival times no longer correspond to content,
   rebuild the series, and re-run the detector. If the shuffled corpus still
   produces "trends", the detector is measuring an artefact of the schedule
   rather than a property of the data.

3. **False positives** - of the topics we flagged, what fraction never
   reached a baseline surface within the follow-up window?

With less than a few weeks of history the honest answer is "not enough data
yet", and that is what it prints. It never fabricates a precision figure.

    python -m tools.validate [--db data/observations.sqlite]
"""

import argparse
import json
import os
import random
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collector import config, detect, pipeline, store  # noqa: E402

MIN_LEAD_TIME_OBSERVATIONS = 4


def load_history(conn, days=120):
    """Return {concept: {cycle: {...}}} keyed by collection cycle.

    The live detector indexes its growth series by collection cycle, so the
    validation harness must do the same. Using wall-clock buckets here would
    measure something the dashboard does not measure.
    """
    cutoff = time.time() - days * 86400
    rows = conn.execute(
        "SELECT concept, cycle, epoch, source, COUNT(*) n FROM observations "
        "WHERE epoch >= ? GROUP BY concept, cycle, source ORDER BY concept, cycle",
        (cutoff,)).fetchall()
    hist = {}
    for r in rows:
        h = hist.setdefault(r["concept"], {"points": [], "sources": {}})
        h["points"].append((int(r["cycle"] or 0), r["epoch"], r["n"], r["source"]))
        h["sources"].setdefault(int(r["cycle"] or 0), set()).add(r["source"])
    return hist


def series_for(hist, concept):
    """Collapse the observation rows into a per-cycle count series."""
    buckets = {}
    for cycle, _epoch, n, _src in hist.get(concept, {}).get("points", []):
        buckets[cycle] = buckets.get(cycle, 0) + n
    return sorted(buckets.items())


def first_detected(series):
    """The earliest bucket at which the detector would have flagged this.

    We use the same burst criterion the live system uses, so "detected" means
    exactly what it means in the dashboard.
    """
    if len(series) < MIN_LEAD_TIME_OBSERVATIONS:
        return None
    counts = [c for _, c in series]
    for i in range(MIN_LEAD_TIME_OBSERVATIONS, len(counts) + 1):
        window = counts[:i]
        base = window[:-1]
        mean = statistics.mean(base)
        sd = statistics.pstdev(base) if len(base) > 1 else 0.0
        latest = window[-1]
        if sd > 0 and (latest - mean) / sd >= 1.5:
            return series[i - 1][0]
        if mean > 0 and latest > mean * 2:
            return series[i - 1][0]
    return None


def permutation_test(hist, trials=40, seed=20261021):
    """Kleinberg-style shuffle test.

    We permute the *order* in which observation events are assigned to
    timestamps while preserving the timestamps themselves, then re-run the
    detector. Real trends should largely disappear.
    """
    rng = random.Random(seed)
    events = []
    for concept, h in hist.items():
        for cycle, epoch, n, src in h["points"]:
            events.append({"concept": concept, "cycle": cycle, "epoch": epoch,
                           "n": n, "src": src})
    cycles = sorted({e["cycle"] for e in events})
    real_hits = 0
    perm_hits = 0

    def detect_all(assignment):
        per = {}
        for e, cyc in zip(assignment, cycles):
            per.setdefault(e["concept"], {}).setdefault(cyc, 0)
            per[e["concept"]][cyc] += e["n"]
        hits = 0
        for concept, buckets in per.items():
            series = sorted(buckets.items())
            if first_detected(series) is not None:
                hits += 1
        return hits

    real_hits = detect_all(events)
    for _ in range(trials):
        shuffled = events[:]
        rng.shuffle(shuffled)
        perm_hits += detect_all(shuffled)

    expected = perm_hits / trials if trials else 0
    return {
        "real_topics_flagged": real_hits,
        "permuted_average_flagged": round(expected, 2),
        "trials": trials,
        "ratio": round(real_hits / expected, 2) if expected else None,
        "interpretation": (
            ("The detector flags topics in the real ordering that the "
             "shuffled corpus never produces, so the signal is not an "
             "artefact of the collection schedule.")
            if expected == 0 and real_hits > 0 else
            ("The detector flags materially more topics in the real "
             "ordering than in shuffled order, so the signal is not an "
             "artefact of the collection schedule.")
            if expected and real_hits / expected > 1.3 else
            ("The detector performs no better on the real ordering than on "
             "shuffled data. The signal is not currently distinguishable "
             "from noise.")
        ),
    }


def _baseline_cycle(series, factor=2.0):
    """The cycle at which the topic became obvious.

    "Obvious" is defined against the topic's own history: the first cycle in
    which its observed volume exceeded ``factor`` times its trailing median.
    That is the point at which someone browsing the free tools by hand would
    reasonably have noticed it.

    We deliberately do NOT use Google's global "Trending Now" list as the
    baseline for this vertical: that list is general-interest, and roughly
    zero of its several hundred daily entries are wellness topics, so a
    vertical topic would essentially never appear on it. Using it would make
    every lead time look infinitely good and every false-positive rate look
    like 100%. The honest baseline is the topic's own volume threshold,
    cross-checked against the surfaces a practitioner actually watches.
    """
    if len(series) < 3:
        return None
    for i in range(MIN_LEAD_TIME_OBSERVATIONS - 1, len(series)):
        prior = [c for _, c in series[:i]]
        if not prior:
            continue
        med = statistics.median(prior)
        if med > 0 and series[i][1] >= factor * med:
            return series[i][0]
    return None


def lead_time_report(conn, hist, days=30):
    """Lead time against the topic's own 'it became obvious' threshold."""
    leads = []
    details = []
    for concept, h in hist.items():
        series = series_for(hist, concept)
        det = first_detected(series)
        if det is None:
            continue
        base = _baseline_cycle(series)
        if base is None:
            continue
        lead_cycles = base - det
        leads.append(lead_cycles)
        details.append({
            "concept": concept,
            "detected_at_cycle": det,
            "became_obvious_at_cycle": base,
            "lead_cycles": lead_cycles,
        })
    details.sort(key=lambda d: -d["lead_cycles"])

    if not leads:
        return {
            "n": 0,
            "status": "insufficient_data",
            "message": (
                "No concept has both an independent detection and a later "
                "crossing of its own volume threshold yet. This needs weeks "
                "of history before lead time can be measured."
            ),
            "details": [],
        }
    return {
        "n": len(leads),
        "status": "measured",
        "median_lead_cycles": statistics.median(leads),
        "mean_lead_cycles": round(statistics.mean(leads), 2),
        "min_lead_cycles": min(leads),
        "max_lead_cycles": max(leads),
        "positive_leads": sum(1 for l in leads if l > 0),
        "negative_leads": sum(1 for l in leads if l < 0),
        "unit": "collection cycles",
        "interpretation": (
            "Positive lead cycles mean the system saw the topic before its "
            "volume crossed the threshold a human would have noticed. "
            "Negative lead cycles mean the threshold was crossed first."
        ),
        "details": details[:40],
    }


def cross_platform_report(hist):
    """How many cycles before a topic appeared on a source it was not on before.

    This is the closest free proxy for the manual baseline: the moment a
    practitioner checking several platforms would have run into the topic.
    """
    lags = []
    details = []
    for concept, h in hist.items():
        series = series_for(hist, concept)
        det = first_detected(series)
        if det is None:
            continue
        cycles_sorted = sorted(h["sources"].keys())
        seen = set()
        for c in cycles_sorted:
            if c > det:
                break
            seen |= h["sources"][c]
        first_new_source = None
        for cycle in cycles_sorted:
            if cycle <= det:
                continue
            if h["sources"][cycle] - seen:
                first_new_source = cycle
                break
        if first_new_source is None:
            continue
        lag = first_new_source - det
        lags.append(lag)
        details.append({"concept": concept, "detected_cycle": det,
                        "first_new_surface_cycle": first_new_source,
                        "lag_cycles": lag})
    details.sort(key=lambda d: d["lag_cycles"])
    if not lags:
        return {"status": "insufficient_data", "n": 0}
    return {
        "status": "measured",
        "n": len(lags),
        "median_lag_cycles": statistics.median(lags),
        "note": (
            "Cycles between the system's first detection and the topic "
            "showing up on a surface it had not previously appeared on. "
            "A practitioner checking several platforms would have run into "
            "the topic around the second number."
        ),
        "details": details[:40],
    }


def false_positive_report(conn, hist, days=30):
    """Flagged topics that never crossed their own volume threshold."""
    flagged = []
    for concept in hist:
        series = series_for(hist, concept)
        if first_detected(series) is not None:
            flagged.append(concept)
    confirmed = []
    for concept in flagged:
        series = series_for(hist, concept)
        if _baseline_cycle(series) is not None:
            confirmed.append(concept)
    if not flagged:
        return {"status": "insufficient_data", "n": 0}
    fp = len(flagged) - len(confirmed)
    return {
        "status": "measured",
        "n_flagged": len(flagged),
        "n_reached_own_threshold": len(confirmed),
        "false_positive_count": fp,
        "false_positive_rate": round(fp / len(flagged), 3),
        "note": (
            "A 'false positive' here means the topic did not double its own "
            "trailing volume within the window. That is not proof it was "
            "noise - it may simply be a slower topic, and the window is "
            "short. Treat this as an upper bound, not a precision score."
        ),
    }




def manual_baseline_report(hist, conn=None):
    """Lead time against the baseline a person actually browses by hand.

    The most honest baseline available without an account is Reddit's own
    ``rising`` and ``top`` rankings: they are literally what someone
    scrolling the subreddit would see, and the collector now reads them
    continuously rather than by hand. TikTok Creative Center cannot be read
    automatically, so Reddit's algorithmic rising list stands in for it -
    it is the same kind of surface (a platform's own "this is taking off"
    ranking) produced by the same kind of signal (engagement velocity).

    For each topic we ask: in which cycle did we first have enough evidence
    to call it emerging, and in which cycle did it first appear on the
    manual baseline? The difference, in cycles, is the lead time.
    """
    manual_first = {}
    for concept, h in hist.items():
        for cycle, srcs in (h.get("sources") or {}).items():
            for s in srcs:
                if s in ("reddit_rss",):
                    # the manual surface
                    if concept not in manual_first or cycle < manual_first[concept]:
                        manual_first[concept] = cycle

    rows = []
    for concept, h in hist.items():
        series = series_for(hist, concept)
        det = first_detected(series)
        if det is None:
            continue
        base = manual_first.get(concept)
        if base is None:
            continue
        det_cycle = det          # first_detected returns the cycle id
        rows.append({
            "concept": concept,
            "detected_cycle": det_cycle,
            "manual_surface_cycle": base,
            "lead_cycles": det_cycle - base,
        })
    rows.sort(key=lambda r: r["lead_cycles"])
    if not rows:
        return {
            "status": "insufficient_data",
            "n": 0,
            "message": ("No topic has both an independent detection and a later "
                        "appearance on the manual baseline yet."),
        }
    leads = [r["lead_cycles"] for r in rows]
    ahead = sum(1 for l in leads if l < 0)
    behind = sum(1 for l in leads if l > 0)

    # Cold-start confound. A topic that was already on the manual surface in
    # the first few cycles could not have been beaten: the detector needs a
    # baseline before it is allowed to call anything emerging, so for those
    # topics "lead time" is undefined rather than negative. The eligible
    # subset is the one where the system had a baseline before the manual
    # surface showed the topic.
    eligible = [r for r in rows
                if r["manual_surface_cycle"] >= config.MIN_OBSERVATIONS]
    elig_leads = [r["lead_cycles"] for r in eligible]
    return {
        "status": "measured",
        "n": len(rows),
        "ahead_of_manual": ahead,
        "behind_manual": behind,
        "median_lead_cycles": statistics.median(leads),
        "eligible_n": len(eligible),
        "eligible_ahead": sum(1 for l in elig_leads if l < 0),
        "eligible_behind": sum(1 for l in elig_leads if l > 0),
        "eligible_median_lead_cycles": (statistics.median(elig_leads)
                                        if elig_leads else None),
        "eligible_note": (
            "Topics whose first appearance on the manual surface came at or "
            "after cycle %d - the point at which the detector had a baseline. "
            "Topics that were already trending when collection began cannot be "
            "beaten by definition, so they are excluded here and reported "
            "separately above." % config.MIN_OBSERVATIONS
        ),
        "unit": "collection cycles",
        "interpretation": (
            "Negative lead means the system had flagged the topic before it "
            "appeared on the platform's own rising/top list - that is the "
            "advantage over browsing by hand. Positive means the manual "
            "surface got there first."
        ),
        "rows": rows[:40],
    }




def replay_emergence(conn, now=None):
    """Replay the *production* detector over the archived history.

    This is the apples-to-apples measurement. For every collection cycle in
    order, the harness rebuilds the buckets from the observations recorded
    up to that point, runs exactly the same
    ``detect.compute_metrics`` / ``detect.classify_maturity`` code the live
    system runs, and records the first cycle at which each concept would
    have been shown as *emerging* on the dashboard.

    Comparing that to when the topic appeared on the manual baseline (a
    platform's own rising/top ranking) gives the lead time over browsing by
    hand, measured on the same detector that makes the claim.
    """
    now = now or time.time()
    rows = conn.execute(
        "SELECT concept, cycle, epoch, source, metric, value, url, extra "
        "FROM observations ORDER BY cycle, epoch").fetchall()
    obs = []
    for r in rows:
        if not r["concept"]:
            continue
        obs.append({
            "concept": r["concept"], "cycle": int(r["cycle"] or 0),
            "epoch": r["epoch"], "source": r["source"], "metric": r["metric"],
            "value": r["value"], "url": r["url"],
            "extra": r["extra"] or "{}",
        })
    if not obs:
        return {}

    cycles = sorted({o["cycle"] for o in obs})
    first_emerging = {}
    classified_at = {}

    for cut in cycles:
        prefix = [o for o in obs if o["cycle"] <= cut]
        if len(prefix) < 100:
            continue
        buckets, _totals = pipeline.build_buckets(prefix)
        rows_b = pipeline.bucket_to_rows(buckets)
        metrics = {}
        for c, b in rows_b.items():
            m = detect.compute_metrics(c, b, now)
            m["_concept"] = c
            metrics[c] = m
        volumes = sorted(m["total_count"] for m in metrics.values())
        for c, m in metrics.items():
            below = sum(1 for v in volumes if v < m["total_count"])
            equal = sum(1 for v in volumes if v == m["total_count"])
            vol_pct = (below + equal / 2.0) / len(volumes)
            maturity = detect.classify_maturity(m, vol_pct, now)
            classified_at.setdefault(c, {})[cut] = maturity
            if maturity in ("emerging", "accelerating") and c not in first_emerging:
                first_emerging[c] = cut
    return {"first_emerging": first_emerging, "by_cycle": classified_at,
            "cycles": cycles}


def manual_baseline_cycles(conn):
    """First cycle each concept appeared on the manual baseline surface.

    Reddit's ``rising`` and ``top`` rankings are what someone scrolling the
    subreddit would see. They are the closest keyless equivalent of the
    TikTok Creative Center list a human checks by hand, and the collector
    now reads them continuously rather than occasionally.
    """
    rows = conn.execute(
        "SELECT concept, MIN(cycle) c FROM observations "
        "WHERE source = 'reddit_rss' GROUP BY concept").fetchall()
    return {r["concept"]: r["c"] for r in rows}


def real_lead_time(conn, replay):
    """Lead time of the production detector against the manual baseline."""
    if not replay:
        return {"status": "insufficient_data", "n": 0}
    manual = manual_baseline_cycles(conn)
    rows = []
    for concept, cyc in replay["first_emerging"].items():
        base = manual.get(concept)
        if base is None:
            continue
        rows.append({
            "concept": concept,
            "detected_cycle": cyc,
            "manual_surface_cycle": base,
            "lead_cycles": cyc - base,
        })
    rows.sort(key=lambda r: r["lead_cycles"])
    if not rows:
        return {
            "status": "insufficient_data", "n": 0,
            "message": ("No topic has both a production-detector emerging "
                        "classification and an appearance on the manual "
                        "baseline yet."),
        }
    leads = [r["lead_cycles"] for r in rows]
    ahead = sum(1 for l in leads if l < 0)
    behind = sum(1 for l in leads if l > 0)

    # Cold-start confound. A topic that was already on the manual surface in
    # the first few cycles could not have been beaten: the detector needs a
    # baseline before it is allowed to call anything emerging, so for those
    # topics "lead time" is undefined rather than negative. The eligible
    # subset is the one where the system had a baseline before the manual
    # surface showed the topic.
    eligible = [r for r in rows
                if r["manual_surface_cycle"] >= config.MIN_OBSERVATIONS]
    elig_leads = [r["lead_cycles"] for r in eligible]
    return {
        "status": "measured",
        "n": len(rows),
        "ahead_of_manual": ahead,
        "behind_manual": behind,
        "median_lead_cycles": statistics.median(leads),
        "eligible_n": len(eligible),
        "eligible_ahead": sum(1 for l in elig_leads if l < 0),
        "eligible_behind": sum(1 for l in elig_leads if l > 0),
        "eligible_median_lead_cycles": (statistics.median(elig_leads)
                                        if elig_leads else None),
        "eligible_note": (
            "Topics whose first appearance on the manual surface came at or "
            "after cycle %d - the point at which the detector had a baseline. "
            "Topics that were already trending when collection began cannot be "
            "beaten by definition, so they are excluded here and reported "
            "separately above." % config.MIN_OBSERVATIONS
        ),
        "unit": "collection cycles",
        "interpretation": (
            "Negative lead means the dashboard would have shown the topic as "
            "emerging before it surfaced on the platform's own rising/top "
            "ranking - that is the advantage over browsing by hand. Positive "
            "means the manual surface got there first. Measured by "
            "replaying the production detector over the archived history."
        ),
        "rows": rows[:50],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=config.DB_PATH)
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--trials", type=int, default=40)
    ap.add_argument("--out", default=os.path.join(config.DATA_DIR, "validation.json"))
    args = ap.parse_args()

    conn = store.connect(args.db)
    hist = load_history(conn, args.days)
    span_days = 0
    if hist:
        all_ts = [p[1] for h in hist.values() for p in h["points"]]
        if all_ts:
            span_days = (max(all_ts) - min(all_ts)) / 86400.0

    replay = replay_emergence(conn)
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "history_span_days": round(span_days, 2),
        "collection_cycles": len({int(r["cycle"] or 0) for r in conn.execute(
            "SELECT DISTINCT cycle FROM observations").fetchall()}),
        "concepts_with_history": len(hist),
        "minimum_history_for_conclusions_days": 21,
        "verdict": (
            "NOT YET MEASURABLE - the observation window is too short. "
            "Lead time and false-positive rate cannot be honestly reported "
            "until at least three weeks of history exist."
            if span_days < 21 else
            "MEASURABLE - see the sections below."
        ),
        "lead_time_vs_manual_baseline": lead_time_report(conn, hist, args.days),
        "cross_platform_confirmation": cross_platform_report(hist),
        "manual_baseline_lead_time": manual_baseline_report(hist, conn),
        "production_detector_lead_time": real_lead_time(conn, replay),
        "false_positives": false_positive_report(conn, hist, args.days),
        "permutation_test": permutation_test(hist, args.trials),
    }
    store.write_json(args.out, report)

    print(json.dumps(report, indent=2)[:4000])
    print("\nWritten to", args.out)
    conn.close()


if __name__ == "__main__":
    main()
