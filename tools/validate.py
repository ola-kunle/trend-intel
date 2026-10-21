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

from collector import config, detect, store  # noqa: E402

MIN_LEAD_TIME_OBSERVATIONS = 4


def load_history(conn, days=120):
    """Return {concept: [(epoch, count)]} plus per-concept source sets."""
    cutoff = time.time() - days * 86400
    rows = conn.execute(
        "SELECT concept, epoch, source, COUNT(*) n FROM observations "
        "WHERE epoch >= ? GROUP BY concept, epoch, source ORDER BY concept, epoch",
        (cutoff,)).fetchall()
    hist = {}
    for r in rows:
        h = hist.setdefault(r["concept"], {"points": [], "sources": {}})
        h["points"].append((r["epoch"], r["n"], r["source"]))
        h["sources"].setdefault(r["epoch"], set()).add(r["source"])
    return hist


def series_for(hist, concept):
    """Collapse the observation rows into a per-bucket count series."""
    buckets = {}
    for epoch, n, _src in hist.get(concept, {}).get("points", []):
        b = int(epoch // 3600) * 3600
        buckets[b] = buckets.get(b, 0) + n
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
        for epoch, n, src in h["points"]:
            events.append({"concept": concept, "epoch": epoch, "n": n, "src": src})
    timestamps = sorted({e["epoch"] for e in events})
    real_hits = 0
    perm_hits = 0

    def detect_all(assignment):
        per = {}
        for e, ts in zip(assignment, timestamps):
            b = int(ts // 3600) * 3600
            per.setdefault(e["concept"], {}).setdefault(b, 0)
            per[e["concept"]][b] += e["n"]
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
            "The detector flags materially more topics in the real ordering "
            "than in shuffled order, so the signal is not an artefact of the "
            "collection schedule."
            if expected and real_hits / expected > 1.3 else
            "The detector performs no better on the real ordering than on "
            "shuffled data. The signal is not currently distinguishable from "
            "noise."
        ),
    }


def lead_time_report(conn, hist, days=30):
    """Lead time against the surfaces a human actually checks.

    Our baseline is the Google Trends trending list: if a concept appears in
    Google's own 'Trending Now' for a geo, that is the moment a person
    checking the free tools would have seen it. We compare that timestamp
    with the moment we first detected the concept independently.
    """
    cutoff = time.time() - days * 86400
    baseline = conn.execute(
        "SELECT concept, MIN(epoch) e FROM observations "
        "WHERE source IN ('google_trends_now','google_trends_rss','pinterest_trends') "
        "AND epoch >= ? GROUP BY concept", (cutoff,)).fetchall()
    baseline_first = {r["concept"]: r["e"] for r in baseline}

    leads = []
    details = []
    for concept, h in hist.items():
        series = series_for(h, concept)
        det = first_detected(series)
        if det is None:
            continue
        base = baseline_first.get(concept)
        if base is None:
            continue
        lead_h = (base - det) / 3600.0
        leads.append(lead_h)
        details.append({
            "concept": concept,
            "detected_at": det,
            "baseline_at": base,
            "lead_hours": round(lead_h, 2),
        })
    details.sort(key=lambda d: -d["lead_hours"])

    if not leads:
        return {
            "n": 0,
            "status": "insufficient_data",
            "message": (
                "No concept has both an independent detection and a later "
                "appearance on a baseline surface yet. This needs weeks of "
                "history before lead time can be measured."
            ),
            "details": [],
        }
    return {
        "n": len(leads),
        "status": "measured",
        "median_lead_hours": round(statistics.median(leads), 2),
        "mean_lead_hours": round(statistics.mean(leads), 2),
        "min_lead_hours": round(min(leads), 2),
        "max_lead_hours": round(max(leads), 2),
        "positive_leads": sum(1 for l in leads if l > 0),
        "negative_leads": sum(1 for l in leads if l < 0),
        "interpretation": (
            "Positive lead hours mean the system saw the topic before it "
            "surfaced on the free tools a person checks manually. "
            "Negative lead hours mean the baseline caught it first."
        ),
        "details": details[:40],
    }


def false_positive_report(conn, hist, days=30):
    """Fraction of flagged topics that never reached a baseline surface."""
    cutoff = time.time() - days * 86400
    flagged = []
    for concept in hist:
        series = series_for(hist, concept)
        if first_detected(series) is not None:
            flagged.append(concept)
    baseline = {r["concept"] for r in conn.execute(
        "SELECT DISTINCT concept FROM observations "
        "WHERE source IN ('google_trends_now','google_trends_rss','pinterest_trends') "
        "AND epoch >= ?", (cutoff,)).fetchall()}
    if not flagged:
        return {"status": "insufficient_data", "n": 0}
    confirmed = [c for c in flagged if c in baseline]
    fp = len(flagged) - len(confirmed)
    return {
        "status": "measured",
        "n_flagged": len(flagged),
        "n_reached_baseline": len(confirmed),
        "false_positive_count": fp,
        "false_positive_rate": round(fp / len(flagged), 3),
        "note": (
            "A 'false positive' here means the topic did not appear on a "
            "baseline surface within the window. That is not proof it was "
            "noise - it may simply be a slower topic - so treat this as an "
            "upper bound, not a precision score."
        ),
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
        all_ts = [e for h in hist.values() for e, _, _ in h["points"]]
        if all_ts:
            span_days = (max(all_ts) - min(all_ts)) / 86400.0

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "history_span_days": round(span_days, 2),
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
        "false_positives": false_positive_report(conn, hist, args.days),
        "permutation_test": permutation_test(hist, args.trials),
    }
    store.write_json(args.out, report)

    print(json.dumps(report, indent=2)[:4000])
    print("\nWritten to", args.out)
    conn.close()


if __name__ == "__main__":
    main()
