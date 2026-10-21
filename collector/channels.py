"""YouTube channel watchlist.

The collector watches a set of creators who actually publish on the vertical
and polls their public RSS feeds. Upload *velocity* is a supply-side early
signal: a creator who normally posts weekly and suddenly posts three videos
on a new subject is telling you something about that subject, and it arrives
before any engagement metric would.

The watchlist is discovered rather than hand-maintained - the bootstrap asks
YouTube for the top channels on each vertical term and keeps the ones that
publish there regularly. It is stored as a plain JSON file so it can be
inspected and edited by hand.
"""

import json
import os
import time

from . import config

WATCHLIST_PATH = os.path.join(config.DATA_DIR, "channel_watchlist.json")

# Seeds for the discovery pass. Chosen to span the vertical: clinical
# hypnosis, somatic work, sleep and meditation content, and the
# personality-development side of the market.
BOOTSTRAP_QUERIES = [
    "hypnotherapy", "clinical hypnosis", "nervous system regulation",
    "somatic therapy", "somatic exercises", "self hypnosis anxiety",
    "burnout recovery", "inner child healing", "sleep meditation",
    "manifestation law of attraction", "reiki healing",
    "subconscious reprogramming", "EMDR trauma", "mindfulness meditation",
    "trauma release therapy", "shadow work meditation", "breathwork",
    "guided meditation sleep", "hypnosis for sleep", "self love",
]


def load():
    if os.path.exists(WATCHLIST_PATH):
        try:
            with open(WATCHLIST_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data.get("channels", {})
        except Exception:
            return {}
    return {}


def save(channels):
    from . import store
    store.write_json(WATCHLIST_PATH, {
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "count": len(channels),
        "channels": channels,
    })


def add(channels, channel_id, name, hits=1, source="discovery"):
    if not channel_id:
        return channels
    entry = channels.get(channel_id)
    if entry:
        entry["hits"] = entry.get("hits", 1) + hits
        entry["last_seen"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    else:
        channels[channel_id] = {
            "name": name or channel_id,
            "hits": hits,
            "source": source,
            "added": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "last_seen": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    return channels


def pairs(channels=None, limit=60):
    """(channel_id, name) pairs for the RSS poller."""
    channels = channels if channels is not None else load()
    items = sorted(channels.items(), key=lambda kv: -kv[1].get("hits", 1))
    return [(cid, meta.get("name", cid)) for cid, meta in items[:limit]]


def discover(yt_dlp_bin, queries=None, results_per_query=8, max_new=40):
    """Find channels publishing on the vertical and add them to the watchlist.

    Uses the same keyless YouTube search the rest of the collector uses.
    """
    import subprocess
    import json as _json
    queries = queries or BOOTSTRAP_QUERIES
    channels = load()
    before = set(channels)
    for q in queries:
        cmd = [yt_dlp_bin, "ytsearch%d:%s" % (results_per_query, q),
               "--flat-playlist", "--dump-json", "--no-warnings"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            continue
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                d = _json.loads(line)
            except Exception:
                continue
            cid = d.get("channel_id")
            if cid:
                add(channels, cid, d.get("channel"), 1, "discovery:" + q)
    new = set(channels) - before
    # keep the watchlist bounded
    if len(channels) > 120:
        keep = sorted(channels.items(), key=lambda kv: -kv[1].get("hits", 1))[:120]
        channels = dict(keep)
    save(channels)
    return channels, len(new)
