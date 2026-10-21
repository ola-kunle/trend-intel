"""Persistence.

Two layers, chosen deliberately:

1. ``observations.sqlite`` — the rolling raw store (180-day window). It holds
   every timestamped observation so that growth statistics can be recomputed
   and audited. Kept out of git (binary, fast-changing) and cached between
   runs in CI.

2. ``data/series.json`` — the durable, human-readable history. Per-concept
   daily aggregates, one row per day, merged in place. Small, diff-friendly,
   and the thing the dashboard actually charts.

Git is not a database; committing the SQLite file every 20 minutes would bloat
history by gigabytes a year. Committing daily aggregates costs ~80 KB/day.
"""

import json
import os
import sqlite3
import time

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id        INTEGER PRIMARY KEY,
    ts        TEXT NOT NULL,
    epoch     REAL NOT NULL,
    source    TEXT NOT NULL,
    geo       TEXT NOT NULL,
    lang      TEXT NOT NULL,
    surface   TEXT NOT NULL,
    concept   TEXT NOT NULL,
    raw_text  TEXT NOT NULL,
    metric    TEXT NOT NULL,
    value     REAL,
    cycle     INTEGER DEFAULT 0,
    url       TEXT,
    extra     TEXT
);
CREATE INDEX IF NOT EXISTS ix_obs_concept_ts ON observations(concept, epoch);
CREATE INDEX IF NOT EXISTS ix_obs_source_ts  ON observations(source, epoch);
CREATE INDEX IF NOT EXISTS ix_obs_geo_ts     ON observations(geo, epoch);
CREATE INDEX IF NOT EXISTS ix_obs_epoch      ON observations(epoch);
CREATE INDEX IF NOT EXISTS ix_obs_cycle      ON observations(cycle);

CREATE TABLE IF NOT EXISTS concepts (
    concept    TEXT PRIMARY KEY,
    first_seen TEXT,
    last_seen  TEXT,
    category   TEXT,
    is_seed    INTEGER DEFAULT 0,
    tier       TEXT
);

CREATE TABLE IF NOT EXISTS state (
    k TEXT PRIMARY KEY,
    v TEXT
);

CREATE TABLE IF NOT EXISTS source_health (
    id         INTEGER PRIMARY KEY,
    ts         TEXT NOT NULL,
    source     TEXT NOT NULL,
    ok         INTEGER NOT NULL,
    items      INTEGER DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    message    TEXT
);
CREATE INDEX IF NOT EXISTS ix_health_source_ts ON source_health(source, epoch_placeholder);
"""

# SQLite does not allow a column named "epoch" to be indexed by a placeholder
# that does not exist, so the health index is created separately.
_SCHEMA = _SCHEMA.replace(
    "CREATE INDEX IF NOT EXISTS ix_health_source_ts ON source_health(source, epoch_placeholder);",
    "CREATE INDEX IF NOT EXISTS ix_health_source_ts ON source_health(source, ts);",
)

RETENTION_DAYS = 180


def connect(path=None):
    path = path or config.DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(_SCHEMA)
    return conn


def prune(conn, days=RETENTION_DAYS):
    cutoff = time.time() - days * 86400
    conn.execute("DELETE FROM observations WHERE epoch < ?", (cutoff,))
    conn.commit()


def insert_observations(conn, rows):
    """rows: iterable of dicts with the observation schema."""
    if not rows:
        return 0
    payload = []
    now = time.time()
    for r in rows:
        payload.append((
            r["ts"], r.get("epoch", now), r["source"], r.get("geo", "GLOBAL"),
            r.get("lang", "en"), r.get("surface", "search"), r.get("concept") or "",
            r.get("raw_text", ""), r.get("metric", "count"), r.get("value"),
            int(r.get("cycle", 0) or 0),
            r.get("url"), json.dumps(r.get("extra") or {}, ensure_ascii=False),
        ))
    conn.executemany(
        "INSERT INTO observations "
        "(ts, epoch, source, geo, lang, surface, concept, raw_text, metric, value, cycle, url, extra) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", payload)
    conn.commit()
    return len(payload)


def upsert_concepts(conn, concepts):
    if not concepts:
        return
    conn.executemany(
        "INSERT INTO concepts (concept, first_seen, last_seen, category, is_seed, tier) "
        "VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(concept) DO UPDATE SET "
        "  last_seen=excluded.last_seen, "
        "  category=COALESCE(concepts.category, excluded.category), "
        "  is_seed=MAX(concepts.is_seed, excluded.is_seed), "
        "  tier=COALESCE(concepts.tier, excluded.tier)",
        [(c["concept"], c.get("first_seen"), c.get("last_seen"), c.get("category"),
          1 if c.get("is_seed") else 0, c.get("tier")) for c in concepts])
    conn.commit()


def get_state(conn, key, default=None):
    row = conn.execute("SELECT v FROM state WHERE k=?", (key,)).fetchone()
    return row["v"] if row else default


def set_state(conn, key, value):
    conn.execute("INSERT INTO state (k, v) VALUES (?,?) "
                 "ON CONFLICT(k) DO UPDATE SET v=excluded.v", (key, str(value)))
    conn.commit()


def record_health(conn, source, ok, items=0, latency_ms=0, message=""):
    conn.execute(
        "INSERT INTO source_health (ts, source, ok, items, latency_ms, message) VALUES (?,?,?,?,?,?)",
        (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), source,
         1 if ok else 0, items, latency_ms, message[:400]))
    conn.commit()


def health_history(conn, source, limit=40):
    rows = conn.execute(
        "SELECT ts, ok, items, latency_ms, message FROM source_health "
        "WHERE source=? ORDER BY id DESC LIMIT ?", (source, limit)).fetchall()
    return [dict(r) for r in reversed(rows)]


def recent_observations(conn, since_epoch, geo=None):
    if geo:
        rows = conn.execute(
            "SELECT * FROM observations WHERE epoch >= ? AND (geo=? OR geo='GLOBAL')",
            (since_epoch, geo)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM observations WHERE epoch >= ?", (since_epoch,)).fetchall()
    return [dict(r) for r in rows]


def observation_counts_by_concept(conn, since_epoch, geo=None):
    if geo:
        rows = conn.execute(
            "SELECT concept, COUNT(*) n FROM observations "
            "WHERE epoch >= ? AND (geo=? OR geo='GLOBAL') GROUP BY concept",
            (since_epoch, geo)).fetchall()
    else:
        rows = conn.execute(
            "SELECT concept, COUNT(*) n FROM observations "
            "WHERE epoch >= ? GROUP BY concept", (since_epoch,)).fetchall()
    return {r["concept"]: r["n"] for r in rows}


def distinct_sources_for(conn, concept, since_epoch, geo=None):
    if geo:
        rows = conn.execute(
            "SELECT DISTINCT source FROM observations "
            "WHERE concept=? AND epoch >= ? AND (geo=? OR geo='GLOBAL')",
            (concept, since_epoch, geo)).fetchall()
    else:
        rows = conn.execute(
            "SELECT DISTINCT source FROM observations WHERE concept=? AND epoch >= ?",
            (concept, since_epoch)).fetchall()
    return sorted({r["source"] for r in rows})


def concept_buckets(conn, concept, since_epoch, bucket_seconds=3600, geo=None):
    """Return {bucket_epoch: {metric: value}} for a concept."""
    if geo:
        rows = conn.execute(
            "SELECT epoch, metric, value, source FROM observations "
            "WHERE concept=? AND epoch >= ? AND (geo=? OR geo='GLOBAL')",
            (concept, since_epoch, geo)).fetchall()
    else:
        rows = conn.execute(
            "SELECT epoch, metric, value, source FROM observations "
            "WHERE concept=? AND epoch >= ?", (concept, since_epoch)).fetchall()
    out = {}
    for r in rows:
        b = int(r["epoch"] // bucket_seconds) * bucket_seconds
        slot = out.setdefault(b, {"count": 0, "views": 0.0, "volume": 0.0,
                                  "comments": 0.0, "sources": set(), "rank_sum": 0.0,
                                  "rank_n": 0})
        slot["count"] += 1
        slot["sources"].add(r["source"])
        v = r["value"]
        if v is None:
            continue
        if r["metric"] in ("views", "volume", "comments"):
            slot[r["metric"]] += float(v)
        elif r["metric"] == "rank":
            slot["rank_sum"] += float(v)
            slot["rank_n"] += 1
    for slot in out.values():
        slot["sources"] = sorted(slot["sources"])
        slot["avg_rank"] = (slot["rank_sum"] / slot["rank_n"]) if slot["rank_n"] else None
    return out


def new_phrasings(conn, within_hours=72, limit=80):
    """Search phrasings that were observed for the *first time* recently.

    A suggestion that has never been seen before and is already being
    offered by an autocomplete endpoint is one of the clearest early
    signals available for free: the demand exists before there is content
    to serve it.

    Returns rows whose first-ever observation falls inside the window.
    """
    cutoff = time.time() - within_hours * 3600
    rows = conn.execute(
        "SELECT raw_text, concept, source, geo, lang, MIN(epoch) first_seen, "
        "       COUNT(*) n, MAX(ts) last_ts, MAX(url) url "
        "FROM observations "
        "WHERE source IN ('google_suggest','youtube_suggest') "
        "GROUP BY raw_text, source "
        "HAVING first_seen >= ? "
        "ORDER BY first_seen DESC LIMIT ?",
        (cutoff, limit)).fetchall()
    out = []
    for r in rows:
        text = r["raw_text"]
        out.append({
            "text": text[:200],
            "concept": r["concept"],
            "source": r["source"],
            "geo": r["geo"],
            "lang": r["lang"],
            "first_seen": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(r["first_seen"])),
            "first_seen_epoch": r["first_seen"],
            "last_seen": r["last_ts"],
            "occurrences": r["n"],
            "url": r["url"],
        })
    return out


def daily_aggregates(conn, days=120):
    """Per-concept per-day aggregates used to build the durable series."""
    cutoff = time.time() - days * 86400
    rows = conn.execute(
        "SELECT concept, date(ts) d, source, geo, metric, SUM(value) s, COUNT(*) n "
        "FROM observations WHERE epoch >= ? GROUP BY concept, d, source, geo, metric",
        (cutoff,)).fetchall()
    agg = {}
    for r in rows:
        key = f"{r['concept']}|{r['d']}"
        slot = agg.setdefault(key, {
            "concept": r["concept"], "date": r["d"], "count": 0,
            "views": 0.0, "volume": 0.0, "comments": 0.0,
            "sources": set(), "geos": set(),
        })
        slot["count"] += r["n"]
        slot["sources"].add(r["source"])
        slot["geos"].add(r["geo"])
        if r["metric"] in ("views", "volume", "comments") and r["s"] is not None:
            slot[r["metric"]] += float(r["s"])
    for slot in agg.values():
        slot["sources"] = sorted(slot["sources"])
        slot["geos"] = sorted(slot["geos"])
        slot["views"] = round(slot["views"], 1)
        slot["volume"] = round(slot["volume"], 1)
        slot["comments"] = round(slot["comments"], 1)
    return list(agg.values())


def load_series(path=None):
    path = path or os.path.join(config.DATA_DIR, "series.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return []


def merge_series(existing, incoming, max_days=400):
    """Merge daily aggregates keyed by (concept, date); keep the newer value."""
    merged = {}
    for row in existing:
        merged[(row["concept"], row["date"])] = row
    for row in incoming:
        merged[(row["concept"], row["date"])] = row
    rows = list(merged.values())
    rows.sort(key=lambda r: (r["concept"], r["date"]))
    if len(rows) > max_days:
        # Trim oldest dates per concept rather than truncating the tail.
        by_concept = {}
        for r in rows:
            by_concept.setdefault(r["concept"], []).append(r)
        trimmed = []
        for c, items in by_concept.items():
            trimmed.extend(items[-max_days:])
        rows = trimmed
        rows.sort(key=lambda r: (r["concept"], r["date"]))
    return rows


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)
    return os.path.getsize(path)
