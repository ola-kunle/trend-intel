"""Human-in-the-loop capture of platform trending lists.

Some platforms will not expose their trend data to an automated collector:

* **TikTok** - the Creative Center's public RPC returns ``40101 no permission``
  and the newer ``cc_portal_api`` endpoint returns HTTP 500 for anonymous
  clients; the Creator Search Insights page (``/csi``) now 302s to a 404. There
  is no public trend API, and TikTok's terms additionally prohibit automated
  and commercial screen scraping.
* **Instagram** - logged-off hashtag pages redirect to a login wall.

For those, the acquisition step is a human looking at a page they are already
logged in to, and the *system* doing what a human cannot: timestamping the
observation and tracking the topic's growth over time.

This module turns such a capture into first-class observations, exactly like
any other source, so a TikTok-originating topic gets the same baseline,
acceleration and corroboration treatment as everything else.

Two ways in, both free:

* ``python -m collector.capture`` - a local prompt on your own machine. No
  credentials, no accounts, works immediately.
* The capture panel on the dashboard - posts to Netlify Forms (free and
  unlimited on every Netlify plan). The collector ingests submissions when
  ``NETLIFY_AUTH_TOKEN`` is present as a repository secret.
"""

import json
import os
import re
import time

from . import config, ontology, store

CAPTURE_SOURCES = {
    "tiktok": "TikTok Creative Center (captured manually)",
    "instagram": "Instagram (captured manually)",
    "pinterest": "Pinterest Trends (captured manually)",
    "other": "Manual capture",
}


def _parse_tags(text):
    """Split a pasted list into clean tags.

    Accepts "#tag", "tag", comma/semicolon/newline separated, and tolerates
    the rank columns that trend tables often include.
    """
    if not text:
        return []
    text = text.replace("\r", "\n")
    out = []
    # Split on line and column breaks, but NOT on spaces: a pasted phrase such
    # as "nervous system" is one topic, not two.
    for chunk in re.split(r"[\n,;\t]+", text):
        chunk = chunk.strip().strip('"').strip("'")
        if not chunk:
            continue
        # drop a leading rank number, e.g. "12. #nervoussystem"
        chunk = re.sub(r"^\d+\s*[\.\)\:-]?\s*", "", chunk).strip()
        chunk = chunk.lstrip("#@").strip()
        if not chunk or len(chunk) > 80:
            continue
        if not re.fullmatch(r"[A-Za-z0-9_À-ɏ\- ]+", chunk):
            continue
        low = chunk.lower()
        if low not in out:
            out.append(low)
    return out


def capture_entry(tags, source="tiktok", notes="", captured_at=None, region="GLOBAL"):
    """Build one capture record."""
    return {
        "tags": tags,
        "source": source,
        "notes": notes[:500],
        "region": region,
        "captured_at": captured_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "capture_id": "cap_" + time.strftime("%Y%m%d%H%M%S", time.gmtime()) + "_" + str(len(tags)),
    }


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def store_capture(conn, entry):
    """Persist a capture in the local store (used by the CLI path)."""
    path = os.path.join(config.DATA_DIR, "manual_captures.json")
    existing = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                existing = json.load(fh)
        except Exception:
            existing = []
    existing.append(entry)
    existing = existing[-500:]
    store.write_json(path, existing)
    return path


def load_captures(conn=None):
    path = os.path.join(config.DATA_DIR, "manual_captures.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return []


def fetch_form_captures():
    """Read submissions from Netlify Forms, if a token is available.

    Netlify Forms is free and unlimited on every plan, so the browser capture
    path costs nothing. Reading submissions back needs the account token,
    which the owner can add as a repository secret (``NETLIFY_AUTH_TOKEN``).
    """
    token = os.environ.get("NETLIFY_AUTH_TOKEN")
    site_id = os.environ.get("NETLIFY_SITE_ID")
    if not token or not site_id:
        return []
    import urllib.request
    url = ("https://api.netlify.com/api/v1/sites/%s/forms" % site_id)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []

    out = []
    for form in data or []:
        title = (form.get("title") or form.get("name") or "")
        if "capture" not in title.lower():
            continue
        for sub in (form.get("submissions") or []):
            data = sub.get("data") or {}
            tags = _parse_tags(data.get("hashtags") or "")
            if not tags:
                continue
            out.append(capture_entry(
                tags,
                source=(data.get("source") or "other").lower(),
                notes=data.get("notes") or "",
                captured_at=sub.get("created_at"),
                region=(data.get("region") or "GLOBAL"),
            ))
    return out


def all_captures(conn=None):
    """Every capture, local first then form submissions, de-duplicated."""
    seen = set()
    out = []
    for e in load_captures(conn) + fetch_form_captures():
        key = (e.get("capture_id"), tuple(e.get("tags") or []))
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


# ---------------------------------------------------------------------------
# Observations
# ---------------------------------------------------------------------------

def capture_observations(conn, captures=None):
    """Turn captures into observations.

    The captured tag is recorded as an observation on the platform it came
    from. That gives every captured topic a timestamped history, which is
    what the detector needs before it can make any momentum claim.
    """
    from . import concepts
    captures = captures if captures is not None else all_captures(conn)
    rows = []
    for entry in captures:
        platform = entry.get("source", "other")
        captured_at = entry.get("captured_at")
        epoch = 0.0
        if captured_at:
            try:
                epoch = time.mktime(time.strptime(captured_at, "%Y-%m-%dT%H:%M:%SZ")) - time.timezone
            except Exception:
                epoch = time.time()
        for tag in entry.get("tags") or []:
            key, _how = concepts.resolve_tag(tag)
            if not key:
                # An unfamiliar tag is a discovery, not a discard.
                key, _how = concepts.resolve_or_discover(tag, allow_mint=True,
                                                         require_lexicon=False)
            if not key:
                continue
            rows.append({
                "ts": captured_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "epoch": epoch,
                "source": f"{platform}_manual",
                "geo": entry.get("region", "GLOBAL"),
                "lang": "en",
                "surface": "platform_trend",
                "concept": key,
                "raw_text": "#" + tag,
                "metric": "platform_trend",
                "value": 1.0,
                "url": "https://www.tiktok.com/tag/" + tag if platform == "tiktok" else None,
                "extra": {"notes": entry.get("notes", ""),
                          "capture_id": entry.get("capture_id"),
                          "rank_in_list": (entry.get("tags") or []).index(tag) + 1,
                          "total_in_capture": len(entry.get("tags") or [])},
            })
    return rows


def capture_summary(conn=None):
    """Compact view of recent captures, for the dashboard."""
    caps = all_captures(conn)
    out = []
    for e in caps[-40:]:
        out.append({
            "source": e.get("source"),
            "captured_at": e.get("captured_at"),
            "region": e.get("region"),
            "count": len(e.get("tags") or []),
            "tags": (e.get("tags") or [])[:40],
            "notes": e.get("notes", "")[:200],
        })
    out.reverse()
    return out
