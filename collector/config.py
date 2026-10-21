"""Runtime configuration.

Every knob that affects what gets collected lives here so that a run is
reproducible and so the dashboard can report exactly what was configured.
"""

import os

# --- Identity --------------------------------------------------------------

VERSION = "1.0.0"
PROJECT = "trend-intel"

# --- Paths -----------------------------------------------------------------

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
SNAPSHOT_DIR = os.path.join(DATA_DIR, "snapshots")
WEB_DIR = os.path.join(ROOT, "web")
DB_PATH = os.environ.get("TREND_DB", os.path.join(DATA_DIR, "observations.sqlite"))
LATEST_JSON = os.path.join(DATA_DIR, "latest.json")

# --- Geographies & languages ------------------------------------------------
#
# geo codes are Google Trends "geo" values; lang is the hl parameter for
# autocomplete and the locale used for search surfaces.

GEOS = [
    # code, trends_geo, language tag, human label
    ("GLOBAL", "US", "en", "Global English"),
    ("FI", "FI", "fi", "Finland"),
    ("ES", "ES", "es", "Spain"),
    ("GB", "GB", "en", "United Kingdom"),
    ("DE", "DE", "de", "Germany"),
    ("SE", "SE", "sv", "Sweden"),
]
GEO_KEYS = [g[0] for g in GEOS]
GEO_TRENDS = {g[0]: g[1] for g in GEOS}
GEO_LANG = {g[0]: g[2] for g in GEOS}
GEO_LABEL = {g[0]: g[3] for g in GEOS}

# Primary geo drives which geo the headline dashboard view uses.
PRIMARY_GEO = os.environ.get("TREND_PRIMARY_GEO", "GLOBAL")

# --- Reddit ----------------------------------------------------------------
#
# Reddit's public RSS endpoints are being retired (announced: RSS ends
# 13 Nov 2026). They are IP-rate-limited aggressively, so we fetch a small
# number per cycle, round-robin, with a long cooldown. Failures are expected
# and are reported as source health, not as fatal errors.

REDDIT_SUBREDDITS = [
    "hypnosis",
    "Hypnotherapy",
    "mentalhealth",
    "wellness",
    "selfimprovement",
    "Meditation",
    "SomaticExperiencing",
    "CBT",
    "attachmenttheory",
]

REDDIT_MIN_INTERVAL_SECONDS = 8.0
REDDIT_PER_CYCLE = 2

# Which Reddit listing to read. `rising` is Reddit's own algorithmic
# "this is taking off" ranking and `top` for the week is what a person
# browsing manually would see. Both are the manual baseline, captured
# continuously rather than by hand.
REDDIT_SORTS = ["rising", "top", "new"]

# --- YouTube ---------------------------------------------------------------

# yt-dlp search queries. Kept modest: each search is a real network round trip.
YOUTUBE_QUERIES = [
    "hypnosis therapy",
    "quantum hypnosis",
    "nervous system regulation",
    "somatic healing",
    "subconscious reprogramming",
    "self hypnosis for anxiety",
    "inner child healing",
    "burnout recovery",
    "manifestation",
    "nervous system reset",
]
YOUTUBE_RESULTS_PER_QUERY = 12

# --- Search-suggestion expansion ------------------------------------------
#
# Autocomplete gives us long-tail demand. We expand each seed with a small
# set of intent modifiers to reach the "how do I..." layer.

# Autocomplete is the highest-value niche signal we have, so we rotate
# through every seed across cycles rather than covering all of them at once.
# Each cycle probes a slice of the seed list with a small set of intent
# modifiers; the full list is covered every few cycles.
SUGGEST_MODIFIERS = ["", "for", "how to"]
SUGGEST_SEEDS_PER_CYCLE = 30
SUGGEST_LANG_CYCLE = ["en", "fi", "es", "en", "fi", "es"]

# Language -> the geography it represents for the regional view. English is
# deliberately left as GLOBAL because the English-language audience is
# global; the localised languages map onto their own country.
LANG_GEO = {"fi": "FI", "es": "ES", "de": "DE", "sv": "SE"}

SUGGEST_MAX_PER_SEED = 8

# Sources whose text is a *topic* rather than a *headline*. Only these may
# mint a new concept. A news headline like "Wellness Expo in Sharonville" is
# an event, not an emerging topic, and minting it would fill the store with
# fragments.
MINT_ALLOWED_SOURCES = {
    # Only surfaces whose text is a short, topic-shaped phrase may mint a
    # new concept. A paper title ("Sleep I am positive affirmations") or a
    # news headline is a sentence about a topic, not a topic, and minting
    # those fills the store with fragments. Search phrasings and Wikipedia
    # article titles are the right shape.
    "wikipedia_views",     # article titles are canonical
    "wikipedia_categories", # and so are category members
}

SOURCES = {
    # --- free, keyless, no registration required -------------------------
    "google_trends_rss": True,
    "google_trends_now": True,
    "google_suggest": True,
    "youtube_suggest": True,
    "youtube_search": True,
    "youtube_channels": True,
    "wikipedia_views": True,
    "wikipedia_categories": True,
    "mastodon_trends": True,
    "mastodon_search": True,
    "lemmy_search": True,
    "reddit_rss": True,
    "news_rss": True,
    "europepmc": True,
    "pubmed_counts": True,
    "arxiv": True,
    "itunes_podcasts": True,
    "hn_algolia": True,
    "tiktok_creative": True,

    # --- require an account, an app review or a key ----------------------
    # Disabled by default. The code is kept and works; it simply stays
    # dormant until a credential is supplied, so the system never depends on
    # something it cannot legally or practically reach.
    "brave_search": False,
    "youtube_data_api": False,
    "instagram_hashtag": False,
    "threads_search": False,
    "pinterest_trends": False,
}

KEYED_SOURCES = {
    "brave_search", "youtube_data_api", "instagram_hashtag",
    "threads_search", "pinterest_trends",
}

# Opt in explicitly, e.g. TREND_ENABLE_KEYED=1 plus the matching credential.
if os.environ.get("TREND_ENABLE_KEYED", "").strip() in ("1", "true", "yes"):
    for _k in KEYED_SOURCES:
        SOURCES[_k] = True

# Wikipedia categories watched for new articles inside the vertical.
WIKIPEDIA_CATEGORIES = [
    "Hypnotherapy", "Hypnosis", "Mental health", "Self-help",
    "Cognitive behavioral therapy", "Meditation", "Mindfulness",
    "Somatic therapy", "Energy healing", "Spirituality", "Neuroplasticity",
    "Attachment theory", "Trauma", "Burnout", "Wellness",
    "Manifestation", "Reiki", "EMDR", "Positive psychology",
]

# --- Instagram hashtag budget ----------------------------------------------
#
# Meta caps Instagram hashtag search at 30 unique hashtags per rolling 7 days
# per Business/Creator account. Re-querying a known tag is free.
IG_UNIQUE_LIMIT = 30
IG_WINDOW_DAYS = 7

# --- New-source rotation budgets ------------------------------------------

# PubMed year-over-year counts are the most expensive new source (one
# request per year per topic), so it runs on a small rotating set.
PUBMED_TOPICS_PER_CYCLE = 8
PUBMED_TOPICS = [
    "hypnosis", "hypnotherapy", "somatic experiencing", "nervous system regulation",
    "subconscious", "mindfulness", "breathwork", "meditation",
    "trauma focused therapy", "emdr", "psychedelic therapy", "ketamine",
    "attachment theory", "self compassion", "burnout", "sleep hygiene",
    "polyvagal", "inner child", "reiki", "manifestation",
    "cbt", "act therapy", "neuroplasticity", "digital mental health",
    "maternal mental health", "adhd adults", "perimenopause", "grief therapy",
]

MASTODON_TOPICS_PER_CYCLE = 10
LEMMY_TOPICS_PER_CYCLE = 6
ARXIV_TOPICS_PER_CYCLE = 6
ARXIV_TOPICS = [
    "self reflection", "digital wellbeing", "affective computing",
    "therapeutic chatbot", "meditation", "neuroscience", "human computer interaction",
    "emotion recognition", "mental health",
]

# --- Optional enrichment ---------------------------------------------------
#
# LLM enrichment is strictly optional. Without a key the system still runs and
# still produces full output; the LLM only adds narrative framing and content
# angles. It never produces a metric, a confidence value, or a source claim.

LLM_PROVIDERS = {
    "groq": {
        "base": "https://api.groq.com/openai/v1/chat/completions",
        "model": "openai/gpt-oss-120b",
        "env": "GROQ_API_KEY",
    },
    "gemini": {
        "base": "https://generativelanguage.googleapis.com/v1beta/models",
        "model": "gemini-3.5-flash-lite",
        "env": "GEMINI_API_KEY",
    },
    "openai_compatible": {
        "base": os.environ.get("TREND_LLM_BASE", ""),
        "model": os.environ.get("TREND_LLM_MODEL", ""),
        "env": "TREND_LLM_API_KEY",
    },
}
LLM_PROVIDER_ORDER = ["groq", "gemini", "openai_compatible"]
LLM_MAX_ITEMS = 60

# --- HTTP ------------------------------------------------------------------

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HTTP_TIMEOUT = 25
HTTP_RETRIES = 2
HTTP_BACKOFF = 2.0

# Wikimedia asks API clients to identify themselves with a descriptive
# User-Agent that includes a contact. Their per-article pageviews endpoint is
# heavy and will 429 anonymous clients that hammer it.
WIKIMEDIA_UA = ("TrendIntelBot/1.0 (open-source wellness trend research; "
                "https://github.com/ola-kunle/trend-intel) Python-urllib")

# Wall-clock budget for the collection phase. Sources that have not run when
# the budget is spent are marked "deferred" rather than silently missing.
COLLECT_BUDGET_SECONDS = 330

# --- Public data host ------------------------------------------------------
#
# The dashboard reads fresh data from the raw file host on the data branch.
# The static copy shipped with the site is the fallback.

PUBLIC_RAW_BASE = os.environ.get(
    "TREND_RAW_BASE",
    "https://raw.githubusercontent.com/ola-kunle/trend-intel/data/data",
)
PUBLIC_REPO = os.environ.get("TREND_REPO", "ola-kunle/trend-intel")
PUBLIC_BRANCH = os.environ.get("TREND_BRANCH", "data")

# --- Scoring ---------------------------------------------------------------

# Weights for the momentum score. Documented in the dashboard so the formula
# is auditable rather than a black box.
SCORE_WEIGHTS = {
    "acceleration": 0.26,
    "velocity": 0.16,
    "burst_onset": 0.16,
    "cross_source": 0.14,
    "creator_diversity": 0.12,
    "relevance": 0.10,
    "evidence_volume": 0.06,
}

# A concept needs this many independent surfaces before we are willing to call
# it a trend rather than an observation.
CROSS_SOURCE_MIN = 2

# Minimum distinct collection cycles before any growth statistic is reported.
# Four was too few: with a four-cycle window the cohort is small, the
# relative-share series is still settling after coverage changes, and the
# resulting classifications are noisy enough to produce false "emerging"
# calls. Six cycles is the point at which the baseline starts to mean
# something.
MIN_OBSERVATIONS = 6

# Minimum distinct sources before "cross-platform signal" is asserted.
MIN_CROSS_SOURCE = 2
