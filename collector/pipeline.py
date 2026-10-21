"""Shared bucketing.

The live collector and the validation harness must build observation buckets
*identically*, otherwise the harness measures a different detector from the
one that runs in production and the lead-time comparison is meaningless.

This module is the single implementation. Both call ``build_buckets``.
"""

import json
import time

from .concepts import evidence_weight


def build_buckets(observations):
    """Return {concept: {cycle: bucket}} plus per-cycle totals.

    A bucket holds the evidence for one concept in one collection cycle:
    weighted volume, the sources that contributed, the creators involved, and
    the raw view counts.

    Two normalisations are applied, and both matter:

    * **Per source** - the weighted volume is divided by the number of
      distinct sources that contributed. Otherwise switching a new source on
      looks exactly like a topic growing.
    * **Per cycle total** - the result is then divided by the cycle's total
      activity, giving each concept a *share* of what the system observed.
      The collector's coverage grows over time, so every concept's raw count
      drifts upward together; a share cancels that out.
    """
    cycle_totals = {}
    for o in observations:
        c = o.get("concept")
        if not c:
            continue
        cyc = int(o.get("cycle") or 0)
        cycle_totals[cyc] = cycle_totals.get(cyc, 0.0) + 1.0

    buckets = {}
    for o in observations:
        c = o.get("concept")
        if not c:
            continue
        cyc = int(o.get("cycle") or 0)
        slot = buckets.setdefault(c, {}).setdefault(cyc, {
            "count": 0.0, "raw_count": 0, "views": 0.0, "volume": 0.0,
            "comments": 0.0, "sources": set(), "creators": set(),
            "avg_rank": None, "rank_sum": 0.0, "rank_n": 0,
            "raw": 0.0, "cycles": set(), "epochs": [],
        })
        extra = {}
        try:
            extra = json.loads(o.get("extra") or "{}")
        except Exception:
            extra = {}
        # An exact ontology match is strong evidence; a glancing phrase
        # mention inside an unrelated title is weak. The weight carries that
        # difference into every downstream statistic.
        w = evidence_weight(extra.get("resolution"), o.get("source"))
        slot["count"] += w
        slot["raw"] += w
        slot["raw_count"] += 1
        slot["sources"].add(o.get("source"))
        slot["epochs"].append(o.get("epoch") or 0.0)
        ch = extra.get("channel_id") or extra.get("channel")
        if ch:
            slot["creators"].add(ch)
        v = o.get("value")
        if v is None:
            continue
        if o.get("metric") in ("views", "volume", "comments"):
            slot[o["metric"]] += float(v)
        elif o.get("metric") == "rank":
            slot["rank_sum"] += float(v)
            slot["rank_n"] += 1

    for concept, cycles in buckets.items():
        for cyc, slot in cycles.items():
            slot["sources"] = sorted(slot["sources"])
            slot["avg_rank"] = (slot["rank_sum"] / slot["rank_n"]) if slot["rank_n"] else None
            slot["epoch"] = (sum(slot["epochs"]) / len(slot["epochs"])) if slot["epochs"] else 0.0
            slot["cycles"] = sorted(slot["cycles"])
            n_src = max(1, len(slot["sources"]))
            slot["count"] = slot["count"] / n_src
            slot["raw"] = slot["raw"] / n_src
            slot["source_count"] = n_src
            total = max(1.0, cycle_totals.get(cyc, 1.0))
            slot["count_rel"] = slot["count"] / total
            slot["abs_count"] = slot["count"]
    return buckets, cycle_totals


def bucket_to_rows(buckets):
    """Flatten the bucket structure into the row shape the detector expects."""
    out = {}
    for concept, cycles in buckets.items():
        out[concept] = {}
        for cyc, slot in cycles.items():
            out[concept][cyc] = {
                "count": slot["count"],
                "count_rel": slot["count_rel"],
                "abs_count": slot["abs_count"],
                "raw_count": slot["raw_count"],
                "views": slot["views"],
                "volume": slot["volume"],
                "comments": slot["comments"],
                "sources": slot["sources"],
                "creators": slot["creators"],
                "cycles": slot["cycles"],
                "epoch": slot["epoch"],
            }
    return out
