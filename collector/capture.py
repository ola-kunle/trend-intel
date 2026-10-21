"""Local capture of a platform trending list.

    python -m collector.capture
    python -m collector.capture --source tiktok --file trending.txt
    cat trending.txt | python -m collector.capture --source tiktok

Why this exists
---------------
TikTok and Instagram will not give an automated collector their trend data:
TikTok's Creative Center RPC returns ``40101`` for anonymous clients and its
newer endpoint returns HTTP 500; Instagram's hashtag pages redirect to a
login wall. Both platforms' terms also prohibit automated and commercial
screen scraping.

The legitimate route is for a person to look at the page they are already
logged in to and copy the list. This tool takes that paste, timestamps it, and
turns it into first-class observations - so a TikTok-originating topic gets the
same baseline, acceleration and cross-source corroboration as every other
topic, and starts accruing history from the moment you first notice it.

Run it once a week, in the browser, on the page you would have checked anyway.
"""

import argparse
import os
import sys
import time

from . import config, manual_captures, store

BANNER = """
Capture a trending list
=======================
Paste the trending hashtags, one per line (or comma separated).
"#", rank numbers and extra columns are stripped automatically.
""".strip()


def read_input(args):
    if args.file:
        with open(args.file, "r", encoding="utf-8") as fh:
            return fh.read()
    if not sys.stdin.isatty():
        return sys.stdin.read()
    print(BANNER)
    print("\n(press Ctrl-D when finished)\n")
    return sys.stdin.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="tiktok",
                    choices=sorted(manual_captures.CAPTURE_SOURCES.keys()),
                    help="which platform the list came from")
    ap.add_argument("--region", default="GLOBAL",
                    help="geography the list covers (GLOBAL, US, FI, ES, ...)")
    ap.add_argument("--file", help="read the list from a file instead of stdin")
    ap.add_argument("--notes", default="", help="free-text note stored with the capture")
    args = ap.parse_args()

    raw = read_input(args)
    tags = manual_captures._parse_tags(raw)
    if not tags:
        print("No usable tags found. Nothing was captured.")
        return 1

    entry = manual_captures.capture_entry(
        tags, source=args.source, notes=args.notes, region=args.region)

    conn = store.connect()
    path = manual_captures.store_capture(conn, entry)

    # Also write it into the observation store immediately so the dashboard
    # reflects it without waiting for the next scheduled cycle.
    rows = manual_captures.capture_observations(conn, [entry])
    store.insert_observations(conn, rows)
    store.record_health(conn, f"{args.source}_manual", True, len(rows), 0,
                         "manual capture")

    print(f"Captured {len(tags)} tags from {args.source}:")
    for i, t in enumerate(tags[:25], 1):
        print(f"  {i:3d}. {t}")
    if len(tags) > 25:
        print(f"  ... and {len(tags) - 25} more")
    print(f"\nSaved to {path}")
    print(f"{len(rows)} observations written to {config.DB_PATH}")
    print("\nThese tags are now tracked topics: each future collection cycle "
          "measures their volume, and they gain a baseline once the collector "
          "has seen them four times.")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
