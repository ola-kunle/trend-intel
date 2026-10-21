"""Detection: turn observations into defensible trend assessments.

The rules that make this defensible:

* **We never use an absolute engagement threshold.** A topic is interesting
  relative to *its own* history, so we compare against the concept's own
  trailing baseline. There is no magic number for "popular enough".
* **Acceleration outranks velocity.** A topic that is growing steadily from a
  high base is not emerging; a topic whose *rate of change* is increasing is.
* **A baseline is mandatory.** With fewer than ``MIN_OBSERVATIONS`` points we
  refuse to compute growth at all and label the concept "newly observed".
* **Seasonality is subtracted.** Topics in this vertical have a strong annual
  cycle (sleep, burnout and stress all peak in winter). We compare against
  the same point in the previous year where data exists, and otherwise damp
  the score rather than pretending to know.
* **Confidence comes from corroboration**, not from an LLM. It is a function
  of the number of *independent* surfaces, the number of observations and the
  depth of history.
* **Everything is traceable.** Every computed number is accompanied by the
  observation ids that produced it.
"""

import math
import statistics
import time

from . import config, concepts, ontology
from .families import families_for


def _safe_div(a, b, default=0.0):
    try:
        if b in (0, None):
            return default
        return a / b
    except Exception:
        return default


def _rank_pct(values, val):
    """Mid-rank percentile of ``val`` within ``values``.

    Percentile *rank* rather than interpolation: robust to the heavy ties
    that occur when many concepts share the same metric (which is the normal
    case before any history accumulates), and always inside [0, 1].
    """
    if not values:
        return 0.0
    n = len(values)
    below = sum(1 for v in values if v < val)
    equal = sum(1 for v in values if v == val)
    return (below + equal / 2.0) / n


def burst_onset_score(buckets, now_epoch, window=12):
    """Kleinberg-style change point on a concept's own count series.

    ``buckets`` is {bucket_epoch: {count, sources, ...}}. We look at the most
    recent window of buckets and ask: how many standard deviations is the
    latest bucket above the mean of the preceding ones, and has the rate of
    growth itself increased?

    Returns a 0..1 score plus the raw evidence.
    """
    if len(buckets) < 4:
        return 0.0, {"reason": "insufficient buckets", "n": len(buckets)}
    keys = sorted(buckets)
    recent = keys[-window:]
    counts = [buckets[k].get("count", 0) for k in recent]
    if len(counts) < 4:
        return 0.0, {"reason": "insufficient buckets", "n": len(counts)}

    baseline = counts[:-1]
    base_mean = statistics.mean(baseline)
    base_sd = statistics.pstdev(baseline) if len(baseline) > 1 else 0.0
    latest = counts[-1]

    z = (latest - base_mean) / base_sd if base_sd > 0 else 0.0
    z_score = max(0.0, min(1.0, z / 4.0))

    # Acceleration: recent half vs older half growth rate.
    half = max(1, len(counts) // 2)
    older, newer = counts[:-half], counts[-half:]
    old_rate = (sum(older[-max(1, len(older) // 2):]) / max(1, len(older) // 2))
    new_rate = (sum(newer) / len(newer))
    accel = _safe_div(new_rate - old_rate, max(old_rate, 0.5))

    score = max(0.0, min(1.0, 0.55 * z_score + 0.45 * max(0.0, min(1.0, accel / 1.5))))

    evidence = {
        "n": len(counts),
        "baseline_mean": round(base_mean, 3),
        "baseline_sd": round(base_sd, 3),
        "latest": latest,
        "z": round(z, 3),
        "old_rate": round(old_rate, 3),
        "new_rate": round(new_rate, 3),
        "accel": round(accel, 3),
    }
    return score, evidence


def _seasonal_damp(concept, series, now_epoch):
    """Reduce confidence for topics that are simply seasonal.

    We do not have a multi-year baseline in the first weeks of operation, so
    the honest thing is to *flag* seasonality rather than pretend to model it.
    A concept whose observation volume is concentrated in a narrow band of the
    year, and whose current window is in that band, gets a modest damp.
    """
    if len(series) < 30:
        return 1.0, {"reason": "insufficient history for seasonal model"}
    by_month = {}
    for ts, v in series:
        m = time.gmtime(ts).tm_mon
        by_month.setdefault(m, []).append(v)
    if len(by_month) < 6:
        return 1.0, {"reason": "fewer than 6 months observed"}
    month_now = time.gmtime(now_epoch).tm_mon
    monthly_mean = {m: statistics.mean(v) for m, v in by_month.items()}
    grand = statistics.mean(list(monthly_mean.values())) or 1.0
    ratio = monthly_mean.get(month_now, grand) / grand
    if ratio > 1.35:
        return 0.75, {"reason": "current month historically elevated",
                      "ratio": round(ratio, 2), "month": month_now}
    return 1.0, {"reason": "no strong seasonal signal detected",
                  "ratio": round(ratio, 2), "month": month_now}


def classify_lifecycle(metrics, history_depth, now_epoch):
    """Assign a lifecycle label.

    ``emerging`` and ``accelerating`` are only asserted when we have a
    baseline to compare against. Otherwise the concept is reported as
    ``newly_observed`` - which is an honest statement, not a hedge.
    """
    # Without a baseline we make no momentum claim at all. This is the rule
    # the brief insists on: no history, no early-detection claim.
    if history_depth < config.MIN_OBSERVATIONS:
        return "newly_observed"

    accel = metrics.get("acceleration", 0.0)
    velocity = metrics.get("velocity", 0.0)
    sources = metrics.get("cross_source_count", 0)
    burst = metrics.get("burst_score", 0.0)

    if accel < -0.05:
        return "declining"
    if accel > 0.12:
        return "accelerating"
    if accel > 0.05 and sources >= config.MIN_CROSS_SOURCE:
        return "emerging"
    if burst > 0.6 and accel <= 0.05:
        return "peaking"
    if metrics.get("seasonality_peak"):
        return "recurring"
    return "steady"


def confidence_level(metrics, history_depth):
    """Confidence from evidence, never from an AI score.

    Three ingredients: how many *independent* surfaces corroborate, how many
    observations back it, and whether we have a baseline to compute growth
    against. Surfaced as low / moderate / high with the reason attached.
    """
    families = metrics.get("family_count", 0)
    depth = history_depth
    reasons = []

    if families >= 3:
        s_score = 3
        reasons.append("%d independent lines of evidence (%s)"
                       % (families, ", ".join(metrics.get("families") or [])))
    elif families == 2:
        s_score = 2
        reasons.append("2 independent lines of evidence (%s)"
                       % ", ".join(metrics.get("families") or []))
    elif families == 1:
        s_score = 1
        reasons.append("1 line of evidence only")
    else:
        s_score = 0
        reasons.append("no independent corroboration")

    obs = metrics.get("observations", 0)
    buckets = metrics.get("time_buckets", 0)
    if buckets >= 12 and obs >= 24:
        d_score = 3
        reasons.append(f"{obs} observations across {buckets} time buckets")
    elif buckets >= 6 and obs >= 10:
        d_score = 2
        reasons.append(f"{obs} observations across {buckets} time buckets")
    elif buckets >= config.MIN_OBSERVATIONS:
        d_score = 1
        reasons.append(f"{obs} observations across {buckets} time buckets")
    else:
        d_score = 0
        reasons.append("no baseline yet")

    b_score = 2 if metrics.get("has_baseline") else 0
    if b_score:
        reasons.append("baseline available")

    total = s_score + d_score + b_score
    if total >= 7:
        level = "high"
    elif total >= 5:
        level = "moderate"
    else:
        level = "low"

    return {"level": level, "score": total, "reasons": reasons}




# ---------------------------------------------------------------------------
# Maturity: separating a genuinely emerging topic from an established one
# ---------------------------------------------------------------------------
#
# The failure mode this exists to prevent: a large, flat, well-known topic
# ("meditation", "burnout", "anxiety") accumulating the highest score purely
# because it has the most observations. That is not early detection, it is a
# popularity ranking, and it is exactly what the brief said not to build.
#
# Maturity is a *fact about the concept's own history*, not a score.

MATURITY_LABELS = {
    "new": "Newly observed",
    "emerging": "Emerging",
    "accelerating": "Accelerating",
    "established": "Established",
    "mature": "Mature",
    "fading": "Fading",
    "recurring": "Recurring / seasonal",
    "steady": "Steady",
}


def classify_maturity(metrics, volume_pct, now_epoch):
    """Label how developed a concept is, from its own history."""
    depth = metrics.get("time_buckets", 0)
    if depth < config.MIN_OBSERVATIONS:
        return "new"

    accel = metrics.get("acceleration", 0.0)
    vel = metrics.get("velocity", 0.0)
    families = metrics.get("family_count", 0)
    phrase_rate = metrics.get("phrase_novelty_rate", 0.0)
    burst = metrics.get("burst_score", 0.0)

    if metrics.get("seasonality_peak"):
        return "recurring"
    if accel < -0.2:
        return "fading"

    # Established: a large topic whose rate of change is flat. Big and calm
    # is the definition of already-established.
    if volume_pct >= 0.65 and accel < 0.03 and phrase_rate < 0.10:
        return "established"

    # Emerging: a real change in the rate of change, seen by at least two
    # independent lines of evidence, and preferably accompanied by new
    # search phrasings (the strongest early marker there is).
    if accel > 0.05 and families >= 2:
        return "emerging"
    if accel > 0.12 and families >= 1:
        return "accelerating"
    if accel > 0.02 and phrase_rate > 0.12 and families >= 2:
        return "emerging"
    if volume_pct >= 0.65:
        return "mature"
    return "steady"


# ---------------------------------------------------------------------------
# Emergence score
# ---------------------------------------------------------------------------
#
# Deliberately *not* the same thing as the old momentum score. Momentum
# rewarded volume, which is a popularity measure. The emergence score rewards
# novelty and change, and is computed as a percentile against the current
# cohort, so it always answers "how unusual is this relative to what we are
# watching right now".
#
# The component that matters most is `phrase_novelty`: a search phrasing that
# has never been seen before, for a topic, is demand forming before there is
# content to serve it. That is the earliest observable marker of an emerging
# interest that exists without a paid API.

EMERGENCE_WEIGHTS = {
    "phrase_novelty": 0.20,
    "acceleration": 0.20,
    "burst_onset": 0.16,
    "discovery_novelty": 0.14,
    "family_confirmation": 0.14,
    "recency": 0.08,
    "velocity": 0.05,
    "relevance": 0.03,
}


def emergence_score(metrics, cohort):
    """0-100 emergence score.

    The previous design summed percentile ranks across components, which had
    a serious flaw: a topic that was merely unremarkable on *every* axis
    still scored around 50, because being above the median on eight
    separate measures adds up. Large established topics are above the median
    on most measures, so they kept winning.

    This version fixes three things:

    * **Magnitude matters.** Each growth measure is scaled by an absolute
      reference, not only by its rank. A concept whose relative share grew
      by 2% is not emerging no matter where it sits in the cohort.
    * **Growth and confirmation multiply, they do not add.** A topic with
      ten sources and no growth is not emerging; a topic with real growth
      and one source is unconfirmed. Only the product can express that.
    * **Newly discovered vocabulary gets a small bonus**, never a
      disqualifying penalty - an unfamiliar term is earlier news, but it
      still has to be corroborated.
    """
    def clamp(x):
        return max(0.0, min(1.0, x))

    # --- growth, on an absolute scale ------------------------------------
    accel = metrics.get("acceleration", 0.0)
    accel_strength = clamp(accel / 0.08)
    phrase_rate = metrics.get("phrase_novelty_rate", 0.0)
    phrase_strength = clamp(phrase_rate / 0.18)
    growth = 0.65 * accel_strength + 0.35 * phrase_strength

    # --- confirmation ------------------------------------------------------
    families = metrics.get("family_count", 0)
    family_factor = clamp(families / 4.0)
    burst_pct = (cohort.get("burst_onset") or [])
    burst_strength = 0.0
    if burst_pct:
        burst_strength = _rank_pct(burst_pct, metrics.get("burst_score", 0.0))
    recency = metrics.get("recency", 0.0)
    confirm = 0.55 * family_factor + 0.25 * burst_strength + 0.20 * recency

    score = 100.0 * growth * (0.25 + 0.75 * confirm)
    # A concept the system discovered by itself is earlier news than one we
    # were already watching, so it gets a bounded bonus.
    score *= (1.0 + 0.15 * metrics.get("discovery_novelty", 0.0))

    parts = {
        "acceleration": round(accel_strength, 4),
        "phrase_novelty": round(phrase_strength, 4),
        "growth": round(growth, 4),
        "family_confirmation": round(family_factor, 4),
        "burst_onset": round(burst_strength, 4),
        "recency": round(recency, 4),
        "confirmation": round(confirm, 4),
        "discovery_bonus": round(metrics.get("discovery_novelty", 0.0), 4),
    }
    return round(min(100.0, max(0.0, score)), 1), parts


def maturity_label(maturity):
    return MATURITY_LABELS.get(maturity, maturity)


def why_it_matters(t):
    """A factual, non-speculative explanation of what the data shows.

    Every clause is derived from a measurement. Nothing here asserts that a
    topic will grow, and nothing invents a cause.
    """
    parts = []
    m = t.get("maturity")
    if m == "established":
        parts.append("Large and flat: this is an established topic, not an emerging one")
    elif m == "emerging":
        parts.append("Gaining momentum: its rate of change is increasing against its own baseline")
    elif m == "accelerating":
        parts.append("Accelerating: the acceleration itself is rising")
    elif m == "new":
        parts.append("Too new to have a baseline yet, so no momentum claim is made")
    elif m == "fading":
        parts.append("Losing momentum against its own baseline")
    elif m == "recurring":
        parts.append("Seasonal: the current window matches a recurring pattern")
    else:
        parts.append("Stable: no significant change in its rate of change")

    if t.get("new_phrase_count"):
        parts.append(
            "%d search phrasing%s appeared for the first time in the last 24 hours, which is demand forming before content exists"
            % (t["new_phrase_count"], "" if t["new_phrase_count"] == 1 else "s"))
    if t.get("discovered"):
        parts.append("The vocabulary itself was discovered by the system, not on the curated watchlist")
    if t.get("family_count"):
        parts.append("corroborated by %d independent %s (%s)"
                     % (t["family_count"],
                        "line of evidence" if t["family_count"] == 1 else "lines of evidence",
                        ", ".join(t.get("families") or [])))
    if t.get("creator_count"):
        parts.append("%d distinct creators" % t["creator_count"])
    return "; ".join(parts) + "."


def compute_metrics(concept, buckets, now_epoch, extra=None):
    """Compute growth metrics for one concept from its bucketed observations."""
    extra = extra or {}
    keys = sorted(buckets)            # collection cycle ids, in order
    # The growth series uses the *relative* count (share of the cycle's
    # total activity) so that expanding coverage does not read as growth.
    counts = [buckets[k].get("count_rel", buckets[k].get("count", 0)) for k in keys]
    views = [buckets[k].get("views", 0.0) for k in keys]
    sources_all = set()
    for k in keys:
        sources_all.update(buckets[k].get("sources") or [])
    fams = families_for(sources_all)

    depth = len(keys)                       # distinct time buckets observed
    raw_obs = sum(buckets[k].get("raw_count", 0) for k in keys)
    cycles = set()
    for k in keys:
        cycles.update(buckets[k].get("cycles") or [])
    has_baseline = depth >= config.MIN_OBSERVATIONS

    velocity = 0.0
    acceleration = 0.0
    window = 6
    source_step = 0.0
    if depth >= 4:
        recent = counts[-window:]
        prior = counts[-2 * window:-window] or counts[:-1]
        if prior and recent:
            r_rate = sum(recent) / len(recent)
            p_rate = sum(prior) / len(prior)
            # Scale-free, because the series is relative (a share of the
            # cycle's total activity) and therefore has no natural floor.
            # A log-ratio change is the only formulation that stays
            # meaningful across several orders of magnitude.
            eps = max(1e-9, 0.02 * (sum(counts) / max(1, len(counts))))
            velocity = math.log10((r_rate + eps) / (p_rate + eps))
            if len(recent) >= 3 and len(prior) >= 2:
                    half = max(1, len(recent) // 2)
                    rr = sum(recent[-half:]) / half
                    pr = sum(recent[:-half]) / max(1, len(recent) - half)
                    acceleration = math.log10((rr + eps) / (pr + eps))

            # If the set of sources feeding this concept changed sharply
            # between the two windows, the apparent growth is a change in
            # instrumentation, not in the world. Damp it and say so.
            def _srcs(seq):
                out = set()
                for kk in seq:
                    out.update(buckets[kk].get("sources") or [])
                return out
            prev_srcs = _srcs(keys[-2 * window:-window] or keys[:-1])
            curr_srcs = _srcs(keys[-window:])
            added = len(curr_srcs - prev_srcs)
            if prev_srcs and added >= 2:
                source_step = min(0.6, 0.25 * added)
                velocity *= (1.0 - source_step)
                acceleration *= (1.0 - source_step)

    burst, burst_ev = burst_onset_score(buckets, now_epoch)
    series = [(buckets[k].get("epoch", k), buckets[k].get("count", 0)) for k in keys]
    damp, season_info = _seasonal_damp(concept, series, now_epoch)

    # Creator diversity: distinct channels observed in the recent window.
    creators = set()
    for k in keys[-12:]:
        for ch in buckets[k].get("creators") or []:
            creators.add(ch)
    creator_growth = metrics_creator_growth = 0.0
    if depth >= 4 and creators:
        early = set()
        for k in keys[:max(1, len(keys) // 2)]:
            for ch in buckets[k].get("creators") or []:
                early.add(ch)
        creator_growth = max(0.0, len(creators - early) / max(1, len(early) or 1))

    first_epoch = buckets[keys[0]].get("epoch", now_epoch) if keys else now_epoch
    age_hours = max(0.0, (now_epoch - first_epoch) / 3600.0)

    recent_obs = sum(counts[-3:]) if counts else 0

    metrics = {
        "observations": raw_obs,
        "time_buckets": depth,
        "cycles_observed": len(cycles),
        "has_baseline": has_baseline,
        "age_hours": round(age_hours, 1),
        "velocity": round(velocity, 4),
        "acceleration": round(acceleration, 4),
        "burst_score": round(burst, 4),
        "burst_evidence": burst_ev,
        "source_step_damping": round(source_step, 4),
        "cross_source_count": len(sources_all),
        "sources": sorted(sources_all),
        "families": fams,
        "family_count": len(fams),
        "creator_count": len(creators),
        "creator_growth": round(creator_growth, 4),
        "recent_observation": recent_obs,
        "total_count": sum(buckets[k].get("abs_count", buckets[k].get("count", 0)) for k in keys),
        "relative_series": [round(c, 8) for c in counts],
        "total_views": round(sum(views), 1),
        "seasonality_damp": damp,
        "seasonality": season_info,
        "seasonality_peak": bool(season_info.get("reason") == "current month historically elevated"),
        "series": [{"t": k, "v": c, "cycle": kk} for kk, (k, c) in zip(keys, series[-90:])],
    }
    return metrics


def score_concept(metrics, cohort):
    """Normalise the metrics against the cohort and produce a 0-100 score.

    Percentile normalisation within the cohort is used instead of absolute
    thresholds, so the score means "how unusual is this relative to what we
    are currently watching" - which is the actual question.
    """
    w = config.SCORE_WEIGHTS
    raw = {
        "acceleration": metrics.get("acceleration", 0.0),
        "velocity": metrics.get("velocity", 0.0),
        "burst_onset": metrics.get("burst_score", 0.0),
        "creator_diversity": metrics.get("creator_growth", 0.0),
        "cross_source": metrics.get("cross_source_count", 0),
        "evidence_volume": metrics.get("total_count", 0),
        "relevance": cohort.get("_relevance", {}).get(metrics["_concept"], 0.4),
    }
    pct = {}
    for key, val in raw.items():
        vals = cohort.get(key) or []
        pct[key] = _rank_pct(vals, val) if vals else 0.0

    score = sum(w[k] * pct[k] for k in w) * 100.0
    score *= metrics.get("seasonality_damp", 1.0)
    return round(min(100.0, max(0.0, score)), 1), pct


def evidence_links(rows):
    """Compact, verifiable evidence list for a concept."""
    seen = {}
    for r in rows:
        key = (r.get("source"), r.get("raw_text"))
        if key in seen:
            continue
        seen[key] = {
            "source": r.get("source"),
            "surface": r.get("surface"),
            "title": (r.get("raw_text") or "")[:200],
            "url": r.get("url"),
            "ts": r.get("ts"),
            "geo": r.get("geo"),
            "metric": r.get("metric"),
            "value": r.get("value"),
        }
    out = list(seen.values())
    out.sort(key=lambda e: e["ts"] or "", reverse=True)
    return out[:12]


def audience_questions(rows, limit=25):
    """Extract question-shaped content from the observation stream.

    A question is either literally interrogative, or an autocomplete phrase
    that expresses a search need. We keep the phrasing verbatim and attach the
    source link so the practitioner can read the actual conversation.
    """
    seen = set()
    out = []
    for r in rows:
        text = (r.get("raw_text") or "").strip()
        if not text:
            continue
        low = text.lower()
        interrogative = ("?" in text or low.startswith(
            ("how ", "what ", "why ", "when ", "where ", "which ", "can ",
             "is ", "does ", "do ", "should ", "are ", "was ", "could ")))
        if not interrogative:
            continue
        intent = ontology.classify_intent(text)
        if intent not in ("problem_solving", "seeking_practical",
                          "considering_professional", "looking_for_service",
                          "curious"):
            continue
        norm = ontology.normalise(text)
        if norm in seen:
            continue
        seen.add(norm)
        out.append({
            "text": text[:220],
            "source": r.get("source"),
            "surface": r.get("surface"),
            "url": r.get("url"),
            "ts": r.get("ts"),
            "intent": intent,
        })
    out.sort(key=lambda q: q["ts"] or "", reverse=True)
    return out[:limit]


def content_opportunities(concept, rows, questions, limit=6):
    """Suggest angles strictly from observed evidence.

    We do not generate angles the data does not support, and we never assert
    a therapeutic outcome. Anything that would read as a medical claim is
    filtered out.
    """
    angles = []
    surfaces = {}
    for r in rows:
        surfaces.setdefault(r.get("surface"), []).append(r)

    titles = [r.get("raw_text") for r in rows if r.get("raw_text")]
    if titles:
        angles.append({
            "kind": "explain",
            "angle": "Explain %s plainly, including what the evidence does and does not support."
                     % concept,
        })
    if surfaces.get("suggest"):
        phrases = [r.get("raw_text") for r in surfaces["suggest"][:5]]
        if phrases:
            angles.append({
                "kind": "answer_search_demand",
                "angle": "Answer the exact phrasing people are searching: %s"
                         % "; ".join(sorted({p for p in phrases if p})[:3]),
            })
    if surfaces.get("video"):
        angles.append({
            "kind": "format",
            "angle": "Short-form video using the observed title patterns: %s"
                     % "; ".join(sorted({(t or "")[:60] for t in
                                         [r.get("raw_text") for r in surfaces["video"][:4]]})[:3]),
        })
    if surfaces.get("academic"):
        angles.append({
            "kind": "evidence",
            "angle": "Cite the new research appearing on this topic so the audience "
                     "can distinguish established methods from emerging ones.",
        })
    if questions:
        angles.append({
            "kind": "answer_question",
            "angle": "Directly answer: \"%s\"" % questions[0]["text"][:120],
        })

    out = []
    for a in angles:
        if ontology.is_blocked_claim(a["angle"]):
            a = dict(a)
            a["angle"] = "Reworded to avoid a therapeutic claim: " + a["angle"]
            a["flagged"] = "medical-claim-filter"
        out.append(a)
    return out[:limit]
