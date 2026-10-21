"""Source collectors.

Each collector returns a list of observation dicts:

    {ts, epoch, source, geo, lang, surface, concept, raw_text,
     metric, value, url, extra}

and raises ``FetchError`` on failure so the orchestrator can record honest
source health.

Design rules
------------
* Prefer endpoints that need no key, no account and no payment method.
* Respect platform restrictions: we read publicly available, logged-off
  surfaces and we never attempt to defeat a CAPTCHA, an access control or a
  request signature.
* Where an official API exists but requires authorisation (Meta, Pinterest),
  the adapter is implemented but stays inert until a token is supplied, and
  reports itself as "awaiting authorisation" rather than silently failing.
* Be polite: pace requests per host, and treat 429 as an expected outcome.
"""

import json
import os
import re
import subprocess
import time
import urllib.parse
import xml.etree.ElementTree as ET

from . import config, concepts, ontology
from .http import FetchError, fetch, fetch_json

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "ht": "https://trends.google.com/trending/rss",
    "content": "http://purl.org/rss/1.0/modules/content/",
}


def _now():
    t = time.time()
    return t, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def parse_batchexecute(body, rpc="i0OFE"):
    """Parse a Google batchexecute response.

    The response is an XSSI-prefixed envelope:
        )]}'\n\n<length>\n[["wrb.fr","<rpc>","<json string>"], ...]
    We extract and decode the inner JSON string for the rpc we asked for.
    """
    if body.startswith(")]}'"):
        body = body.split("\n", 1)[1] if "\n" in body else body[4:]
    # The payload is preceded by a numeric line; find the JSON array.
    start = body.find("[[\"wrb.fr\"")
    if start < 0:
        start = body.find("[")
    if start < 0:
        raise ValueError("no JSON array in batchexecute response")
    # Trim trailing whitespace/newlines.
    chunk = body[start:].strip()
    try:
        envelope = json.loads(chunk)
    except Exception:
        # Trailing junk after the array; trim to the matching bracket.
        depth = 0
        end = None
        for i, ch in enumerate(chunk):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end is None:
            raise
        envelope = json.loads(chunk[:end])
    for item in envelope:
        if isinstance(item, list) and len(item) >= 3 and item[0] == "wrb.fr" and item[1] == rpc:
            return json.loads(item[2])
    raise ValueError("rpc %s not present in batchexecute response" % rpc)


def _mint_allowed(source):
    return source in config.MINT_ALLOWED_SOURCES


def _row(**kw):
    epoch, ts = _now()
    kw.setdefault("epoch", epoch)
    kw.setdefault("ts", ts)
    kw.setdefault("geo", "GLOBAL")
    kw.setdefault("lang", "en")
    kw.setdefault("surface", "search")
    kw.setdefault("metric", "count")
    kw.setdefault("value", 1.0)
    kw.setdefault("extra", {})
    return kw


# ---------------------------------------------------------------------------
# 1. Google Trends - Trending Now (full list via the web UI's own RPC)
# ---------------------------------------------------------------------------

def google_trends_now(geo, hours=24, lang="en"):
    """The richest free early-signal source we have.

    Returns every trending search for a geo, with search volume, percent
    increase and the exact onset timestamp. We keep the rows that touch our
    vertical and count the rest, because "our vertical's share of all search
    attention" is itself a useful signal.
    """
    trends_geo = config.GEO_TRENDS.get(geo, "US")
    hl = {"fi": "fi-FI", "es": "es-ES", "de": "de-DE", "sv": "sv-SE"}.get(lang, "en-US")
    url = ("https://trends.google.com/_/TrendsUi/data/batchexecute"
           "?rpcids=i0OFE&source-path=/trending&hl=%s&rt=c" % hl)
    payload = ('[[["i0OFE","[null,null,\\"%s\\",0,\\"%s\\",%d]",null,"generic"]]]'
               % (trends_geo, hl, hours))
    body = ("f.req=" + urllib.parse.quote(payload)).encode("utf-8")
    raw = fetch(url, headers={"Content-Type": "application/x-www-form-urlencoded"},
                data=body, min_interval=1.5)[1]
    data = parse_batchexecute(raw, "i0OFE")

    rows = data[1] if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list) else []
    out, total, matched = [], 0, 0
    for r in rows:
        if not isinstance(r, list) or not r:
            continue
        total += 1
        title = r[0] or ""
        volume = r[6] if len(r) > 6 else None
        pct = r[8] if len(r) > 8 else None
        start_ts = r[3][0] if len(r) > 3 and r[3] else None
        related = r[9] if len(r) > 9 and isinstance(r[9], list) else []
        cats = r[10] if len(r) > 10 and isinstance(r[10], list) else []
        arts = r[11] if len(r) > 11 and isinstance(r[11], list) else []
        article_url = arts[0][2] if arts and len(arts[0]) > 2 else None

        # The global Trending Now list is mostly news and sport, so it is
        # only allowed to attach to curated concepts - never to mint new ones.
        probe = " ".join([title] + [str(x) for x in related[:12]])
        key, how = concepts.resolve_or_discover(probe, allow_mint=False)
        if not key:
            continue
        matched += 1
        expl = ("https://trends.google.com/trends/explore?date=now%%201-d&q=%s&hl=%s"
                % (urllib.parse.quote(title), hl))
        out.append(_row(
            source="google_trends_now", geo=geo, lang=lang, surface="search",
            concept=key, raw_text=title, metric="volume",
            value=float(volume) if volume else None, url=expl,
            extra={"pct_increase": pct, "start_ts": start_ts, "rank": None,
                   "related": related[:12], "categories": cats,
                   "resolution": how, "article": article_url,
                   "vertical_share": round(matched / total, 4) if total else None,
                   "trend_total": total},
        ))
        # Also record each related query as its own observation: these are the
        # long-tail phrases the trend is made of.
        for rq in related[:8]:
            if not isinstance(rq, str):
                continue
            rk, _ = concepts.resolve_or_discover(rq, allow_mint=False)
            if not rk:
                continue
            out.append(_row(
                source="google_trends_now", geo=geo, lang=lang, surface="search",
                concept=rk, raw_text=rq, metric="volume",
                value=float(volume) if volume else None, url=expl,
                extra={"kind": "related_query", "parent_trend": title},
            ))
    return out, {"total_trends": total, "vertical_matched": matched}


# ---------------------------------------------------------------------------
# 2. Google Trends - daily RSS (poll-safe, no browser)
# ---------------------------------------------------------------------------

def google_trends_rss(geo, lang="en"):
    trends_geo = config.GEO_TRENDS.get(geo, "US")
    url = "https://trends.google.com/trending/rss?geo=%s" % trends_geo
    body = fetch(url, min_interval=1.0)[1]
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise FetchError(url, None, f"RSS parse error: {exc}")

    out = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        traffic = item.findtext("{http://search.yahoo.com/mrss/}approx_traffic") or ""
        m = re.search(r"([\d,]+)\s*\+?", traffic)
        volume = float(m.group(1).replace(",", "")) if m else None
        news_url = None
        nitem = item.find("ht:news_item", NS)
        if nitem is not None:
            news_url = nitem.findtext("ht:news_item_url", None, NS)
        expl = ("https://trends.google.com/trends/explore?date=now%%201-d&q=%s"
                % urllib.parse.quote(title))
        key, how = concepts.resolve_or_discover(title, allow_mint=False)
        if not key:
            continue
        out.append(_row(
            source="google_trends_rss", geo=geo, lang=lang, surface="search",
            concept=key, raw_text=title, metric="volume", value=volume,
            url=news_url or expl,
            extra={"rank": None, "resolution": how, "traffic_text": traffic},
        ))
    return out, {"items": len(out)}


# ---------------------------------------------------------------------------
# 3. Google Autocomplete
# ---------------------------------------------------------------------------

def _suggest(url, lang):
    body = fetch(url, min_interval=0.35)[1]
    # Response shape: ["query",["a","b"],[],[...]]  (JSON) or window.google.ac.h(...) (JSONP)
    if body.startswith("window.google.ac.h("):
        body = body[body.find("(") + 1:body.rfind(")")]
    try:
        data = json.loads(body)
    except Exception:
        return []
    if isinstance(data, list) and len(data) >= 2 and isinstance(data[1], list):
        return data[1]
    return []


def google_suggest(seeds, lang, modifiers=None):
    modifiers = modifiers or config.SUGGEST_MODIFIERS
    out = []
    for seed in seeds:
        for mod in modifiers:
            q = f"{seed} {mod}".strip()
            url = ("https://suggestqueries.google.com/complete/search?"
                   + urllib.parse.urlencode({"client": "firefox", "hl": lang, "q": q}))
            try:
                suggs = _suggest(url, lang)
            except FetchError:
                continue
            for pos, s in enumerate(suggs):
                if not isinstance(s, str):
                    continue
                key, how = concepts.resolve_or_discover(s, allow_mint=False)
                if not key:
                    continue
                out.append(_row(
                    source="google_suggest", geo="GLOBAL", lang=lang,
                    surface="suggest", concept=key, raw_text=s,
                    metric="count", value=1.0,
                    url="https://www.google.com/search?q=" + urllib.parse.quote(s),
                    extra={"seed": seed, "modifier": mod, "position": pos,
                           "resolution": how, "intent": ontology.classify_intent(s)},
                ))
    return out, {"items": len(out)}


def youtube_suggest(seeds, lang):
    """YouTube's autocomplete carries relative popularity weights.

    The trailing integer array in the response is a rank bucket; diffing it
    over time gives a rising/falling signal for YouTube search demand.
    """
    out = []
    for seed in seeds:
        url = ("https://suggestqueries.google.com/complete/search?"
               + urllib.parse.urlencode({"client": "youtube", "ds": "yt",
                                         "hl": lang, "q": seed}))
        body = fetch(url, min_interval=0.35)[1]
        if body.startswith("window.google.ac.h("):
            body = body[body.find("(") + 1:body.rfind(")")]
        try:
            data = json.loads(body)
        except Exception:
            continue
        items = data[1] if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list) else []
        for pos, item in enumerate(items):
            if not isinstance(item, list) or not item:
                continue
            phrase = item[0]
            weights = item[2] if len(item) > 2 and isinstance(item[2], list) else []
            weight = float(sum(weights)) if weights else 0.0
            key, how = concepts.resolve_or_discover(phrase, allow_mint=False)
            if not key:
                continue
            out.append(_row(
                source="youtube_suggest", geo="GLOBAL", lang=lang,
                surface="suggest", concept=key, raw_text=phrase,
                metric="suggest_weight", value=weight,
                url="https://www.youtube.com/results?search_query=" + urllib.parse.quote(phrase),
                extra={"seed": seed, "position": pos, "resolution": how,
                       "intent": ontology.classify_intent(phrase)},
            ))
    return out, {"items": len(out)}


# ---------------------------------------------------------------------------
# 4. YouTube search via yt-dlp (keyless)
# ---------------------------------------------------------------------------

def youtube_search(queries, ytdlp_bin):
    """Date-ordered YouTube search.

    Gives us, per query: a set of fresh videos with view counts and their
    creating channels. The count of *distinct channels* per concept per cycle
    is the "independent creator growth" signal - one of the strongest early
    indicators available, because supply-side activity precedes demand-side
    virality.
    """
    out = []
    videos = 0
    for q in queries:
        cmd = [ytdlp_bin, f"ytsearchdate{config.YOUTUBE_RESULTS_PER_QUERY}:{q}",
               "--flat-playlist", "--dump-json", "--no-warnings",
               "--extractor-args", "youtubetab:approximate_date",
               "--socket-timeout", "20"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=150)
        except subprocess.TimeoutExpired:
            continue
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            title = d.get("title") or ""
            if not title:
                continue
            videos += 1
            key, how = concepts.resolve_or_discover(title, allow_mint=_mint_allowed("youtube_search"))
            if not key:
                continue
            vid = d.get("id")
            out.append(_row(
                source="youtube_search", geo="GLOBAL", lang="en",
                surface="video", concept=key, raw_text=title,
                metric="views", value=float(d.get("view_count") or 0),
                url=f"https://www.youtube.com/watch?v={vid}",
                extra={"channel": d.get("channel"), "channel_id": d.get("channel_id"),
                       "video_id": vid, "query": q, "resolution": how,
                       "duration": d.get("duration"),
                       "description": (d.get("description") or "")[:600],
                       "upload_date": d.get("upload_date") or d.get("timestamp"),
                       "intent": ontology.classify_intent(title)},
            ))
    return out, {"videos": videos}


# ---------------------------------------------------------------------------
# 5. Wikipedia pageviews (per-article daily)
# ---------------------------------------------------------------------------

def wikipedia_views(titles, lang="en"):
    """Daily view counts for resolved article titles.

    Wikipedia pageview acceleration is one of the earliest free signals for a
    genuinely new concept: a term can start drawing searches before it is a
    common search query.
    """
    out = []
    for title in titles:
        # 120 days is enough to compute a baseline and a same-season
        # comparison, and keeps the payload small enough to be quick.
        from_ymd = time.strftime("%Y%m%d", time.gmtime(time.time() - 120 * 86400))
        url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
               + f"{lang}.wikipedia/all-access/user/{urllib.parse.quote(title)}"
               + f"/daily/{from_ymd}/20991231")
        try:
            data = fetch_json(url, min_interval=0.15, timeout=12, retries=0)
        except FetchError:
            continue
        items = (data.get("items") or [])
        if not items:
            continue
        series = [(it.get("timestamp"), it.get("views")) for it in items
                  if it.get("timestamp") and it.get("views") is not None]
        series.sort()
        if len(series) < 2:
            continue
        latest_ts, latest_v = series[-1]
        prev_v = series[-2][1]
        d = datetime_from_ymd(latest_ts)
        key, how = concepts.resolve_or_discover(title, allow_mint=_mint_allowed("wikipedia_views"))
        if not key:
            continue
        out.append(_row(
            source="wikipedia_views", geo="GLOBAL", lang=lang, surface="wiki",
            concept=key, raw_text=title, metric="views", value=float(latest_v),
            url="https://%s.wikipedia.org/wiki/%s" % (lang, urllib.parse.quote(title.replace(" ", "_"))),
            extra={"article": title, "day": d, "prev_views": prev_v,
                   "resolution": how, "series_points": len(series)},
        ))
    return out, {"articles": len(out)}


def datetime_from_ymd(ts):
    try:
        return time.strftime("%Y-%m-%d", time.gmtime(int(ts)))
    except Exception:
        return None


def wikipedia_search(term, lang="en"):
    """Resolve a seed to its best Wikipedia article title (cached by caller)."""
    url = ("https://%s.wikipedia.org/w/api.php?action=query&list=search&format=json"
           "&srlimit=1&srsearch=%s" % (lang, urllib.parse.quote(term)))
    try:
        data = fetch_json(url, min_interval=1.0, timeout=15, retries=1,
                          headers={"User-Agent": config.WIKIMEDIA_UA,
                                   "Api-User-Agent": config.WIKIMEDIA_UA})
    except FetchError:
        return None
    hits = (data.get("query") or {}).get("search") or []
    return hits[0].get("title") if hits else None


# ---------------------------------------------------------------------------
# 6. Mastodon trends (free 7-day per-tag history)
# ---------------------------------------------------------------------------

def mastodon_trends():
    url = "https://mastodon.social/api/v1/trends/tags?limit=40"
    data = fetch_json(url, min_interval=1.0)
    out = []
    for tag in data:
        name = tag.get("name") or ""
        history = tag.get("history") or []
        if not history:
            continue
        for h in history:
            try:
                uses = float(h.get("uses") or 0)
            except Exception:
                uses = 0.0
            if uses <= 0:
                continue
            day = datetime_from_ymd(h.get("day"))
            key, how = concepts.resolve_or_discover(name, allow_mint=False)
            if not key:
                continue
            out.append(_row(
                source="mastodon_trends", geo="GLOBAL", lang="en", surface="social",
                concept=key, raw_text=name, metric="volume", value=uses,
                url=f"https://mastodon.social/tags/{name}",
                extra={"day": day, "accounts": h.get("accounts"), "resolution": how},
            ))
    return out, {"tags": len(data)}


# ---------------------------------------------------------------------------
# 7. Reddit (public subreddit RSS - being retired 13 Nov 2026)
# ---------------------------------------------------------------------------

def reddit_rss(subreddit):
    url = f"https://www.reddit.com/r/{subreddit}/.rss?limit=50"
    body = fetch(url, min_interval=config.REDDIT_MIN_INTERVAL_SECONDS,
                 timeout=15, retries=0)[1]
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise FetchError(url, None, f"RSS parse error: {exc}")
    out = []
    for entry in root.findall("atom:entry", NS):
        title = (entry.findtext("atom:title", "", NS) or "").strip()
        link = entry.findtext("atom:link", "", NS)
        updated = entry.findtext("atom:updated", "", NS)
        if not title:
            continue
        key, how = concepts.resolve_or_discover(title, allow_mint=False)
        if not key:
            continue
        out.append(_row(
            source="reddit_rss", geo="GLOBAL", lang="en", surface="social",
            concept=key, raw_text=title, metric="count", value=1.0,
            url=link,
            extra={"subreddit": subreddit, "updated": updated,
                   "resolution": how, "intent": ontology.classify_intent(title)},
        ))
    return out, {"entries": len(out)}


# ---------------------------------------------------------------------------
# 8. Google News RSS with a recency window
# ---------------------------------------------------------------------------

def news_rss(queries):
    out = []
    for q in queries:
        url = ("https://news.google.com/rss/search?"
               + urllib.parse.urlencode({"q": q, "hl": "en-US", "gl": "US",
                                         "ceid": "US:en", "qft": "+qdr:d"}))
        try:
            body = fetch(url, min_interval=0.4)[1]
            root = ET.fromstring(body)
        except (FetchError, ET.ParseError):
            continue
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            if not title:
                continue
            key, how = concepts.resolve_or_discover(title, allow_mint=False)
            if not key:
                continue
            out.append(_row(
                source="news_rss", geo="GLOBAL", lang="en", surface="article",
                concept=key, raw_text=title, metric="count", value=1.0,
                url=item.findtext("link"),
                extra={"query": q, "resolution": how,
                       "published": item.findtext("pubDate"),
                       "intent": ontology.classify_intent(title)},
            ))
    return out, {"items": len(out)}


# ---------------------------------------------------------------------------
# 9. Europe PMC (research emergence + evidence grounding)
# ---------------------------------------------------------------------------

def europepmc(queries):
    out = []
    for q in queries:
        url = ("https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
               + urllib.parse.urlencode({
                   "query": q, "format": "json", "pageSize": "5",
                   "sort": "P_PDATE_D desc"}))
        try:
            data = fetch_json(url, min_interval=0.3)
        except FetchError:
            continue
        for res in (data.get("resultList") or {}).get("result", []):
            title = res.get("title") or ""
            if not title:
                continue
            key, how = concepts.resolve_or_discover(title, allow_mint=_mint_allowed("europepmc"))
            if not key:
                continue
            out.append(_row(
                source="europepmc", geo="GLOBAL", lang="en", surface="academic",
                concept=key, raw_text=title, metric="count", value=1.0,
                url=("https://europepmc.org/article/"
                     + (res.get("source") or "MED") + "/" + (res.get("id") or "")),
                extra={"journal": res.get("journalTitle"), "pubYear": res.get("pubYear"),
                       "pubType": res.get("pubType"), "pmcid": res.get("pmcid"),
                       "query": q, "resolution": how},
            ))
    return out, {"items": len(out)}


# ---------------------------------------------------------------------------
# 10. iTunes / Apple Podcasts
# ---------------------------------------------------------------------------

def itunes_podcasts(queries):
    out = []
    for q in queries:
        url = ("https://itunes.apple.com/search?"
               + urllib.parse.urlencode({"term": q, "media": "podcast", "limit": "5"}))
        try:
            data = fetch_json(url, min_interval=0.3)
        except FetchError:
            continue
        for r in data.get("results", []):
            name = r.get("collectionName") or ""
            if not name:
                continue
            key, how = concepts.resolve_or_discover(name, allow_mint=False)
            if not key:
                continue
            out.append(_row(
                source="itunes_podcasts", geo="GLOBAL", lang="en", surface="podcast",
                concept=key, raw_text=name, metric="count", value=1.0,
                url=r.get("feedUrl") or r.get("collectionViewUrl"),
                extra={"artist": r.get("artistName"), "genres": r.get("genres"),
                       "releaseDate": r.get("releaseDate"), "episodes": r.get("trackCount"),
                       "query": q, "resolution": how},
            ))
    return out, {"items": len(out)}


# ---------------------------------------------------------------------------
# 11. Hacker News (Algolia - keyless)
# ---------------------------------------------------------------------------

def hn_algolia(queries):
    out = []
    for q in queries:
        url = ("https://hn.algolia.com/api/v1/search_by_date?"
               + urllib.parse.urlencode({"query": q, "tags": "story", "hitsPerPage": "10"}))
        try:
            data = fetch_json(url, min_interval=0.3)
        except FetchError:
            continue
        for hit in data.get("hits", []):
            title = hit.get("title") or hit.get("story_title") or ""
            if not title:
                continue
            key, how = concepts.resolve_or_discover(title, allow_mint=False)
            if not key:
                continue
            out.append(_row(
                source="hn_algolia", geo="GLOBAL", lang="en", surface="social",
                concept=key, raw_text=title, metric="count", value=1.0,
                url=hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                extra={"points": hit.get("points"), "comments": hit.get("num_comments"),
                       "created": hit.get("created_at"), "query": q, "resolution": how},
            ))
    return out, {"items": len(out)}


# ---------------------------------------------------------------------------
# 12. TikTok Creative Center - best effort, publicly visible surfaces only
# ---------------------------------------------------------------------------

def tiktok_creative():
    """Publicly visible TikTok Creative Center trend data.

    Reality check (verified 2026-10-21): the Creative Center's internal RPC
    endpoint returns ``{"code":40101,"msg":"no permission"}`` and the trending
    *sounds* feed was removed outright (HTTP 404). The web UI renders trends
    client-side behind the same gate.

    We therefore attempt the documented-by-observation public RPC and, if it is
    refused, report the source as blocked rather than pretending it works.
    We do not attempt to defeat the gate, solve CAPTCHAs or forge request
    signatures.
    """
    url = ("https://ads.tiktok.com/creative_radar_api/v1/popular_trend/hashtag/list"
           "?period=7&country_code=US&limit=100")
    try:
        data = fetch_json(url, min_interval=2.0, retries=0)
    except FetchError as exc:
        raise FetchError(url, getattr(exc, "status", None),
                         "Creative Center RPC refused or unreachable; "
                         "TikTok exposes no public trend API")
    if isinstance(data, dict) and data.get("code") not in (None, 0):
        raise FetchError(url, 200, f"Creative Center returned code={data.get('code')} "
                                   f"msg={data.get('msg')}")
    rows = []
    for item in (data.get("data") or {}).get("list", []) or []:
        name = item.get("hashtag_name") or item.get("hashtagName") or ""
        if not name:
            continue
        key, how = concepts.resolve_or_discover(name, allow_mint=False)
        if not key:
            continue
        rows.append(_row(
            source="tiktok_creative", geo="GLOBAL", lang="en", surface="social",
            concept=key, raw_text=name, metric="volume",
            value=float(item.get("video_views") or item.get("publish_cnt") or 0),
            url=("https://ads.tiktok.com/business/creativecenter/hashtag/"
                 + urllib.parse.quote(name) + "/pc/en"),
            extra={"rank": item.get("trend_rank"), "industry": item.get("industry_name"),
                   "resolution": how},
        ))
    return rows, {"items": len(rows)}


# ---------------------------------------------------------------------------
# 13. Official APIs that require authorisation (inert until a token exists)
# ---------------------------------------------------------------------------

def instagram_hashtag_search(token=None, tags=None):
    """Instagram Graph API hashtag search.

    Requires: Meta app + App Review + ``instagram_basic`` +
    ``Instagram Public Content Access`` + a Business/Creator account with
    Business Verification. Also capped by Meta at 30 *unique* hashtags per
    rolling 7 days per account, and it can only re-query tags we already know.
    """
    token = token or os.environ.get("INSTAGRAM_ACCESS_TOKEN")
    if not token:
        raise FetchError("instagram", None,
                         "awaiting authorisation: INSTAGRAM_ACCESS_TOKEN not set "
                         "(needs Meta App Review + Instagram Public Content Access)")
    out = []
    for tag in (tags or []):
        url = ("https://graph.facebook.com/v22.0/ig_hashtag_search?"
               + urllib.parse.urlencode({"user_id": os.environ.get("IG_USER_ID", ""),
                                         "q": tag, "access_token": token}))
        data = fetch_json(url, min_interval=0.5)
        hid = (data.get("data") or [{}])[0].get("id")
        if not hid:
            continue
        recent = ("https://graph.facebook.com/v22.0/%s/recent_media?"
                  % hid
                  + urllib.parse.urlencode({"user_id": os.environ.get("IG_USER_ID", ""),
                                            "fields": "id,caption,like_count,comments_count,timestamp",
                                            "access_token": token}))
        media = fetch_json(recent, min_interval=0.5).get("data", [])
        for m in media:
            caption = m.get("caption") or ""
            key, how = concepts.resolve_or_discover(caption, allow_mint=False)
            if not key:
                continue
            out.append(_row(
                source="instagram_hashtag", geo="GLOBAL", lang="en", surface="social",
                concept=key, raw_text=caption[:280], metric="likes",
                value=float(m.get("like_count") or 0),
                url=f"https://www.instagram.com/p/{m.get('id')}/",
                extra={"hashtag": tag, "comments": m.get("comments_count"),
                       "timestamp": m.get("timestamp"), "resolution": how},
            ))
    return out, {"items": len(out)}


def threads_keyword_search(token=None, queries=None):
    """Threads public-post keyword search (official API)."""
    token = token or os.environ.get("THREADS_ACCESS_TOKEN")
    if not token:
        raise FetchError("threads", None,
                         "awaiting authorisation: THREADS_ACCESS_TOKEN not set "
                         "(needs threads_keyword_search App Review)")
    out = []
    for q in queries or []:
        url = ("https://graph.threads.net/v1.0/keyword_search?"
               + urllib.parse.urlencode({"q": q, "search_type": "RECENT",
                                         "limit": "25", "access_token": token}))
        try:
            data = fetch_json(url, min_interval=0.5)
        except FetchError:
            continue
        for post in data.get("data", []):
            text = post.get("text") or ""
            key, how = concepts.resolve_or_discover(text, allow_mint=False)
            if not key:
                continue
            out.append(_row(
                source="threads_search", geo="GLOBAL", lang="en", surface="social",
                concept=key, raw_text=text[:280], metric="likes",
                value=float(post.get("like_count") or 0),
                url=post.get("permalink"),
                extra={"query": q, "timestamp": post.get("timestamp"),
                       "reply_count": post.get("reply_count"), "resolution": how},
            ))
    return out, {"items": len(out)}


def pinterest_trends(token=None, regions=("US",)):
    """Pinterest Trends API - the best structural fit for this vertical.

    Gives an explicit *growing* ranking with week-over-week and month-over-
    month growth plus a weekly normalised series. Requires Pinterest Standard
    access (manual review). Region buckets include SE+DK+FI+NO and ES.
    """
    token = token or os.environ.get("PINTEREST_ACCESS_TOKEN")
    if not token:
        raise FetchError("pinterest", None,
                         "awaiting authorisation: PINTEREST_ACCESS_TOKEN not set "
                         "(needs Pinterest Standard access review)")
    out = []
    for region in regions:
        url = ("https://api.pinterest.com/v5/trends/keywords/%s/top/growing?"
               % region + urllib.parse.urlencode({"limit": "50", "access_token": token}))
        try:
            data = fetch_json(url, min_interval=1.0)
        except FetchError:
            continue
        for item in (data.get("items") or []):
            term = item.get("term") or item.get("keyword") or ""
            if not term:
                continue
            key, how = concepts.resolve_or_discover(term, allow_mint=False)
            if not key:
                continue
            out.append(_row(
                source="pinterest_trends", geo=region, lang="en", surface="search",
                concept=key, raw_text=term, metric="growth",
                value=float(item.get("pct_growth_wow") or 0),
                url=f"https://trends.pinterest.com/detail/?terms={urllib.parse.quote(term)}&country={region}",
                extra={"pct_growth_mom": item.get("pct_growth_mom"),
                       "pct_growth_yoy": item.get("pct_growth_yoy"),
                       "series": item.get("time_series"), "resolution": how},
            ))
    return out, {"items": len(out)}
