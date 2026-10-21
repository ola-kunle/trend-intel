"""Turning an observed trend into content a practitioner can actually make.

The brief asked for the platform to show "how it could translate into
relevant TikTok, Instagram, or website content". This module does that, with
three rules that keep it honest:

1. **Every angle is derived from something observed.** The title of the
   short-form video comes from the phrasing people are actually searching
   for, not from a copywriting template. If nobody has searched for
   anything about a topic, the module says so instead of inventing a plan.

2. **The evidence tier governs what may be claimed.** A topic tiered
   *established* can be presented as a supported method. A topic tiered
   *unsubstantiated* (quantum hypnosis, QHHT) gets an explicitly
   explanatory and non-clinical treatment, because the risk of a
   misleading claim in this vertical is not a hypothetical.

3. **No therapeutic promise.** Every angle is screened against the
   medical-claim filter before it is returned.
"""

from . import ontology

# The observed shape of a short-form video, used to describe a format the
# audience is already responding to, without inventing one.
FORMAT_HINTS = [
    ("step by step", "a how-to walkthrough"),
    ("beginner", "a beginner's starting point"),
    ("in 5 minutes", "a short timed routine"),
    ("at home", "a do-it-at-home version"),
    ("vs ", "a comparison"),
    ("why ", "an explanatory opener"),
    ("what is", "a definition explainer"),
    ("myth", "a myth-busting format"),
    ("routine", "a routine or sequence format"),
    ("morning", "a morning routine format"),
    ("night", "a wind-down format"),
    ("before", "a before/after or trigger format"),
]


def _phrasings(rows, limit=12):
    """Distinct observed phrasings, longest first (longer = more specific)."""
    seen, out = set(), []
    for r in rows:
        if r.get("surface") not in ("suggest", "platform_trend"):
            continue
        t = (r.get("raw_text") or "").strip()
        if not t or t.lower() in seen:
            continue
        seen.add(t.lower())
        out.append(t)
    out.sort(key=lambda s: -len(s))
    return out[:limit]


def _questions(rows, limit=6):
    out = []
    for r in rows:
        t = (r.get("raw_text") or "").strip()
        if "?" in t or t.lower().startswith(("how ", "why ", "what ", "can ", "is ", "does ")):
            if t not in out:
                out.append(t)
    return out[:limit]


def content_translation(concept, rows, questions, tier, category_label):
    """Return per-channel content angles derived from what was observed."""
    phrases = _phrasings(rows)
    qs = _questions(rows)
    t = (tier or "adjacent")

    # --- what can be claimed, derived from the evidence tier --------------
    if t == "established":
        claim = ("present it as a method with research support, and say what "
                 "the evidence does and does not cover")
    elif t == "emerging":
        claim = ("present it as a developing area - describe what the "
                 "research so far shows, and flag it as preliminary")
    elif t == "interpretive":
        claim = ("present it as a meaning-making or spiritual framework, and "
                 "be explicit that it is not a clinical intervention")
    elif t == "unsubstantiated":
        claim = ("explain what the concept is and where the claims come "
                 "from, without endorsing them - and state plainly that the "
                 "evidence base is weak")
    else:
        claim = ("present it as a practical wellness habit, without any "
                 "therapeutic or medical claim")

    angles = []

    # --- short-form video --------------------------------------------------
    if phrases:
        top = phrases[0]
        hook = ("\"%s\" - open with the exact phrase people are searching "
                "for, because that is the question in their head" % top[:90])
        angles.append({
            "channel": "Short-form video (TikTok / Reels)",
            "angle": hook,
            "format": "Answer the search phrase head-on in the first two seconds.",
            "basis": "observed search phrasing",
        })
    if qs:
        angles.append({
            "channel": "Short-form video (TikTok / Reels)",
            "angle": ("Address the question people are literally asking: "
                      "\"%s\" - answer it first, then explain." % qs[0][:110]),
            "format": "Question-led hook, direct answer, then context.",
            "basis": "observed audience question",
        })

    # --- carousel / educational -------------------------------------------
    if len(phrases) > 1:
        angles.append({
            "channel": "Carousel or Instagram educational post",
            "angle": ("Build a %d-part explainer from the distinct ways this "
                      "topic is being asked about: %s."
                      % (min(len(phrases), 5),
                         "; ".join('"%s"' % p[:44] for p in phrases[1:5]))),
            "format": "One idea per slide, each slide a sub-question.",
            "basis": "observed phrasing spread",
        })

    # --- long-form / website ----------------------------------------------
    article = ("A page answering the questions people are actually asking "
               "about %s, with the evidence tier stated up front." % concept)
    if t in ("interpretive", "unsubstantiated"):
        article += (" Include a short section on what is claimed versus what "
                    "is supported, and what to do if someone is in distress.")
    elif t == "established":
        article += (" Include what the research supports, and what is still "
                    "uncertain.")
    else:
        article += (" Include a safety note and a route to professional "
                    "support for anyone struggling.")
    angles.append({
        "channel": "Website / long-form article",
        "angle": article,
        "format": "Answer-first structure, headings taken from the questions.",
        "basis": "observed audience questions + evidence tier",
    })

    # --- what is safe to say ----------------------------------------------
    angles.append({
        "channel": "Framing",
        "angle": claim,
        "format": "Keep the claim inside the evidence tier.",
        "basis": "curated evidence tier",
    })

    # --- what is not yet possible ------------------------------------------
    if not phrases and not qs:
        angles.append({
            "channel": "Not yet actionable",
            "angle": ("No distinct search phrasing or audience question has "
                      "been observed for this topic, so there is no demand "
                      "signal to write against yet. Revisit once one appears."),
            "format": "-",
            "basis": "no observed demand",
        })

    # --- safety screen -----------------------------------------------------
    for a in angles:
        if ontology.is_blocked_claim(a["angle"]):
            a["angle"] = ("Reworded to avoid a therapeutic claim: "
                          + a["angle"])
            a["flagged"] = "medical-claim-filter"
    return angles[:6]


def content_opportunity_note(concept, rows, tier, category_label):
    """A one-line reason this topic is worth the practitioner's attention."""
    phrases = _phrasings(rows, limit=3)
    qs = _questions(rows, limit=2)
    bits = []
    if qs:
        bits.append("people are asking about it directly")
    if phrases:
        bits.append("new ways of phrasing it are appearing")
    if tier == "unsubstantiated":
        bits.append("and it carries claims that need careful handling")
    elif tier == "emerging":
        bits.append("and the research around it is still developing")
    elif tier == "established":
        bits.append("and it can be presented with the evidence attached")
    if not bits:
        return "A topic in %s worth watching." % (category_label or "this vertical")
    return "Worth attention: %s." % ", ".join(bits)
