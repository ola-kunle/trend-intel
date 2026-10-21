"""Concept resolution: surface text -> canonical concept key.

The resolver is intentionally conservative. It prefers an exact or
phrase-level match against the curated ontology and only falls back to fuzzy
token overlap above a threshold. Anything it cannot place becomes a *new,
auto-discovered concept* rather than being force-fitted into a seed.

That distinction matters: a concept we curated has a known category and a
known evidence tier. An auto-discovered concept has a category we have to infer
and a tier of "adjacent" until a human says otherwise. The dashboard shows
that difference.
"""

import re

from . import ontology

_TOKEN_RE = re.compile(r"[a-z0-9']+")

# Very common words that carry no topical signal but inflate token overlap.
_STOP = {
    "a", "an", "and", "the", "of", "for", "to", "in", "on", "with", "your",
    "my", "me", "i", "is", "are", "be", "do", "does", "how", "what", "why",
    "can", "will", "it", "at", "or", "you", "we", "they", "he", "she", "not",
    "best", "top", "free", "new", "guide", "tips", "help", "more", "than",
    "vs", "near", "me", "work", "works", "working", "get", "make", "use",
    "using", "does", "from", "about", "into", "out", "off", "own", "same",
}

# Token -> concept map, built once from the ontology. Longer phrases win.
_PHRASE_INDEX = {}
for _seed in ontology.ALL_SEEDS:
    _PHRASE_INDEX.setdefault(_seed, _seed)
for _alias, _target in ontology.ALIASES.items():
    _PHRASE_INDEX.setdefault(_alias, _target)

# Sorted longest-first so "nervous system regulation" beats "nervous system".
_PHRASES_BY_LENGTH = sorted(_PHRASE_INDEX.items(), key=lambda kv: -len(kv[0]))

# A single compiled alternation is far faster than 300 separate regex passes
# per observation, which matters at a few thousand observations per cycle.
_PHRASE_RE = None
if _PHRASES_BY_LENGTH:
    alt = "|".join(re.escape(p) for p, _ in _PHRASES_BY_LENGTH if len(p) >= 4)
    if alt:
        _PHRASE_RE = re.compile(r"(?<![a-z0-9])(?:" + alt + r")(?![a-z0-9])")

_DISCOVERY_RE = None
_dterms = [t for t in ontology.DISCOVERY_LEXICON if len(t) >= 4]
if _dterms:
    _DISCOVERY_RE = re.compile(
        r"(?<![a-z0-9])(?:" + "|".join(re.escape(t) for t in _dterms) + r")(?![a-z0-9])")

_TOKEN_INDEX = {}
for _phrase, _target in _PHRASE_INDEX.items():
    _toks = [t for t in _TOKEN_RE.findall(_phrase) if t not in _STOP]
    if not _toks:
        continue
    _TOKEN_INDEX.setdefault(_toks[0], set()).add((tuple(_toks), _target))


def slug(text):
    t = ontology.normalise(text)
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:80] or "unknown"


def tokens(text):
    return [t for t in _TOKEN_RE.findall(ontology.normalise(text)) if t not in _STOP]


def resolve(text, *, min_overlap=0.75):
    """Return (concept_key, how) or (None, None).

    ``how`` is one of: exact, alias, phrase, token, new.
    """
    if not text:
        return None, None
    norm = ontology.normalise(text)
    if not norm:
        return None, None

    # 1. Exact canonical match.
    if norm in ontology.SEED_SET:
        return norm, "exact"

    # 2. Exact alias match.
    if norm in ontology.ALIASES:
        return ontology.ALIASES[norm], "alias"

    # 3. Whole-phrase containment, longest phrase first.
    if _PHRASE_RE:
        m = _PHRASE_RE.search(norm)
        if m:
            return _PHRASE_INDEX[m.group(0)], "phrase"

    # 4. Token overlap against any known phrase.
    toks = set(tokens(norm))
    if toks:
        best, best_score = None, 0.0
        for cand_toks, target in {t for s in _TOKEN_INDEX.values() for t in s}:
            ctoks = set(cand_toks)
            if not ctoks:
                continue
            inter = toks & ctoks
            if not inter:
                continue
            score = len(inter) / len(ctoks)
            if score > best_score:
                best, best_score = target, score
        if best and best_score >= min_overlap:
            return best, "token"

    return None, None


# Platform hashtags are space-stripped by definition: TikTok's
# "#nervoussystemregulation" is the phrase "nervous system regulation". The
# ontology is written in spaced form, so a second index maps the stripped
# form back to the concept.
_STRIPPED_INDEX = {}
for _seed in ontology.ALL_SEEDS:
    _STRIPPED_INDEX.setdefault(_seed.replace(" ", ""), _seed)
for _alias, _target in ontology.ALIASES.items():
    _STRIPPED_INDEX.setdefault(_alias.replace(" ", ""), _target)


def resolve_tag(tag):
    """Resolve a platform hashtag to a concept.

    Handles the space-stripped form natively, and falls back to a prefix
    match so that "#burnoutrecovery" still lands on "burnout recovery"
    rather than being discarded.
    """
    if not tag:
        return None, None
    key, how = resolve(tag)
    if key:
        return key, how
    stripped = tag.replace(" ", "").replace("-", "").replace("_", "")
    if stripped in _STRIPPED_INDEX:
        return _STRIPPED_INDEX[stripped], "stripped"
    # longest stripped seed that the tag starts with
    best = None
    for sform, target in _STRIPPED_INDEX.items():
        if len(sform) >= 4 and stripped.startswith(sform):
            if best is None or len(sform) > len(best[0]):
                best = (sform, target)
    if best:
        return best[1], "prefix"
    return None, None


def resolve_or_discover(text, *, min_overlap=0.75, allow_mint=True):
    """Resolve, or mint a stable key for an unseen concept.

    Auto-discovery is gated on the vertical lexicon: a phrase only becomes a
    new concept if it carries an unmistakable wellness signal. Without that
    gate, a global trending feed would mint concepts for every news item and
    the store would fill with noise.
    """
    key, how = resolve(text, min_overlap=min_overlap)
    if key:
        return key, how
    if not allow_mint:
        return None, None
    norm = ontology.normalise(text)
    if not norm or not ontology.discoverable(norm):
        return None, None
    # A discovered concept needs a stable identity across cycles. Slug +
    # normalisation is deterministic, so the same phrase always maps to the
    # same key.
    label = ontology.mint_concept_label(norm) or norm
    key = "auto:" + slug(label)
    return key, "mint"


def category_of(concept):
    if concept in ontology.CATEGORY_OF:
        return ontology.CATEGORY_OF[concept]
    if concept.startswith("auto:"):
        label = concept[5:].replace("-", " ")
        term = ontology.lexicon_match(label)
        if term:
            cat = ontology.category_for_lexicon(term)
            if cat:
                return cat
    # Auto-discovered concepts inherit a category from the closest seed by
    # token overlap, but only when the overlap is strong. Otherwise the
    # category is unknown and the dashboard says so.
    best, best_score = None, 0.0
    ctoks = set(tokens(concept.replace("auto:", "")))
    if not ctoks:
        return None
    for seed in ontology.ALL_SEEDS:
        stoks = set(tokens(seed))
        if not stoks:
            continue
        score = len(ctoks & stoks) / len(stoks)
        if score > best_score:
            best, best_score = seed, score
    if best and best_score >= 0.6:
        return ontology.CATEGORY_OF[best]
    return None


def weight_of(concept):
    if concept in ontology.WEIGHT_OF:
        return ontology.WEIGHT_OF[concept]
    cat = category_of(concept)
    if cat and cat in ontology.CATEGORIES:
        return 0.45
    return 0.35


def evidence_weight(method, source=None):
    """How strongly one observation supports the concept it was matched to.

    An exact ontology match is strong evidence. A phrase match inside a long
    title is weaker: "hypnosis pokemon" mentions the concept without being
    about it. Autocomplete suggestions are systematically noisier than search
    results, so their phrase matches are discounted further.
    """
    base = {"exact": 1.0, "alias": 0.9, "phrase": 0.45, "token": 0.30,
            "mint": 0.70}.get(method, 0.5)
    if source in ("google_suggest", "youtube_suggest") and method in ("phrase", "token"):
        base *= 0.6
    return base


def tier_of(concept):
    if concept in ontology.EVIDENCE_MAP:
        return ontology.EVIDENCE_MAP[concept]
    return "adjacent"


def related_for(concept):
    return [{"concept": c, "relation": r} for c, r in ontology.related(concept)]


def is_curated(concept):
    return concept in ontology.SEED_SET


def is_vertical(text):
    """Cheap pre-filter used by collectors to avoid storing irrelevant rows."""
    key, _ = resolve(text)
    return key is not None
