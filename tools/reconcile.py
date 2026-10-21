"""Reconcile two copies of the observation store.

The store lives in two places: the repository (a durable weekly checkpoint)
and the Actions cache (a fast per-run restore). The cache restore blindly
overwrites the checked-out copy, which means a stale cache can replace a
newer repository copy and silently roll the history backwards.

This picks the copy with more distinct collection cycles - and, if they are
equal, the one with more observations - and leaves it in place.

    python -m tools.reconcile data/observations.sqlite cache/observations.sqlite
"""

import os
import shutil
import sqlite3
import sys


def stats(path):
    if not os.path.exists(path):
        return None
    try:
        conn = sqlite3.connect(path)
        row = conn.execute(
            "SELECT COUNT(DISTINCT cycle) c, COUNT(*) n FROM observations"
        ).fetchone()
        conn.close()
        if not row or row[1] == 0:
            return {"path": path, "cycles": 0, "observations": 0}
        return {"path": path, "cycles": row[0], "observations": row[1]}
    except Exception as exc:
        return {"path": path, "cycles": 0, "observations": 0, "error": str(exc)}


def main():
    primary = sys.argv[1] if len(sys.argv) > 1 else "data/observations.sqlite"
    secondary = sys.argv[2] if len(sys.argv) > 2 else "cache/observations.sqlite"

    a = stats(primary)
    b = stats(secondary)
    print("primary  :", a)
    print("secondary:", b)

    if b is None:
        print("no secondary copy; keeping primary")
        return 0

    take_secondary = (b["cycles"], b["observations"]) > (a["cycles"], a["observations"]) if a else True
    if take_secondary:
        os.makedirs(os.path.dirname(primary) or ".", exist_ok=True)
        shutil.copyfile(secondary, primary)
        print(f"adopted secondary ({b['cycles']} cycles, {b['observations']} observations)")
    else:
        print(f"kept primary ({a['cycles']} cycles, {a['observations']} observations)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
