"""Source families.

Cross-platform confirmation is only meaningful if the confirming sources are
genuinely independent. Two search surfaces that both reflect the same Google
index are not two confirmations; a Reddit thread and a YouTube upload are.

Grouping sources into families lets the detector count *independent* lines of
evidence rather than the raw number of feeds, which is otherwise dominated by
whichever surface happens to be chatty.
"""

SOURCE_FAMILIES = {
    # demand expressed as a search or a suggestion
    "google_suggest": "search_intent",
    "youtube_suggest": "search_intent",
    "google_trends_now": "search_intent",
    "google_trends_rss": "search_intent",
    "brave_search": "search_intent",

    # conversation
    "reddit_rss": "social",
    "mastodon_search": "social",
    "mastodon_trends": "social",
    "lemmy_search": "social",
    "hn_algolia": "social",
    "tiktok_manual": "social",
    "instagram_manual": "social",

    # published video
    "youtube_search": "video",
    "youtube_channels": "video",
    "youtube_data_api": "video",

    # the research literature
    "europepmc": "research",
    "pubmed_counts": "research",
    "arxiv": "research",

    # public reference works
    "wikipedia_views": "reference",
    "wikipedia_categories": "reference",

    # editorial coverage
    "news_rss": "editorial",

    # spoken-word
    "itunes_podcasts": "podcast",

    # a trend list read off a platform by a human
    "tiktok_creative": "platform_trend",
}

FAMILY_LABELS = {
    "search_intent": "search demand",
    "social": "conversation",
    "video": "published video",
    "research": "research",
    "reference": "reference works",
    "editorial": "editorial",
    "podcast": "podcast",
    "platform_trend": "platform trend list",
}


def family_of(source):
    return SOURCE_FAMILIES.get(source, "other")


def families_for(sources):
    """Distinct families, excluding the catch-all bucket."""
    out = set()
    for s in sources or []:
        f = family_of(s)
        if f != "other":
            out.add(f)
    return sorted(out)
