"""Small HTTP helper: retries, pacing, honest error surfacing.

Every source module goes through here so that failure modes are uniform and
reportable, rather than each source inventing its own error handling.
"""

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config

_LAST_CALL = {}


class FetchError(Exception):
    def __init__(self, url, status=None, message=None):
        self.url = url
        self.status = status
        super().__init__(message or f"HTTP {status} for {url}")


def _throttle(key, min_interval):
    """Sleep so that repeated calls to the same host respect a floor."""
    now = time.time()
    last = _LAST_CALL.get(key, 0.0)
    wait = min_interval - (now - last)
    if wait > 0:
        time.sleep(wait)
    _LAST_CALL[key] = time.time()


def fetch(url, *, headers=None, data=None, min_interval=0.0,
          timeout=None, retries=None, allow_404=False, backoff=None):
    """Fetch a URL and return (status, body_text).

    Raises FetchError on network failure or non-2xx (unless allow_404).
    """
    timeout = timeout or config.HTTP_TIMEOUT
    retries = config.HTTP_RETRIES if retries is None else retries
    hdrs = {
        "User-Agent": config.USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
    }
    if headers:
        hdrs.update(headers)

    host = urllib.parse.urlparse(url).netloc
    last_err = None

    for attempt in range(retries + 1):
        if min_interval:
            _throttle(host, min_interval)
        try:
            req = urllib.request.Request(url, data=data, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return resp.status, body
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            if exc.code == 404 and allow_404:
                return 404, body
            last_err = FetchError(url, exc.code, f"HTTP {exc.code} for {url}")
            # Client errors other than 429 will not fix themselves.
            if exc.code not in (429, 500, 502, 503, 504):
                raise last_err
            if exc.code == 429:
                # Rate limited: back off hard and then stop trying.
                time.sleep(8.0 + random.uniform(0, 4.0))
        except Exception as exc:  # network-level
            last_err = FetchError(url, None, f"{type(exc).__name__} for {url}: {exc}")

        if attempt < retries:
            mult = backoff if backoff is not None else config.HTTP_BACKOFF
            time.sleep(mult * (2 ** attempt) + random.uniform(0, 1.0))

    raise last_err or FetchError(url, None, "unknown fetch failure")


def fetch_json(url, **kwargs):
    status, body = fetch(url, **kwargs)
    try:
        return json.loads(body)
    except Exception as exc:
        raise FetchError(url, status, f"invalid JSON from {url}: {exc}")


def fetch_text(url, **kwargs):
    return fetch(url, **kwargs)[1]
