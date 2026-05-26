"""
RSS fetcher for war-brief.
Reads docs/sources.yaml, pulls every feed, filters by recency and (optionally) author.

We fetch with `requests` directly so we control the HTTP headers, then hand the raw
bytes to feedparser. This is more reliable than letting feedparser do its own HTTP,
which tends to lose headers along the way and get blocked by Substack-style hosts.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import feedparser
import requests
import yaml

SOURCES_PATH = Path("docs/sources.yaml")

# Browser-shaped headers. Substack, Medium, and several CDN-fronted sites
# reject server-flavored requests; this gets us through most of them.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.5 Safari/605.1.15"
    ),
    "Accept": (
        "application/rss+xml, application/atom+xml, application/xml;q=0.9, "
        "text/xml;q=0.8, text/html;q=0.7, */*;q=0.5"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
}

REQUEST_TIMEOUT_SECONDS = 15


def load_sources() -> dict[str, Any]:
    with SOURCES_PATH.open() as f:
        return yaml.safe_load(f)


def entry_datetime(entry: Any) -> datetime | None:
    """Pull a UTC datetime from a feedparser entry, or None if unavailable."""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        t = getattr(entry, attr, None)
        if t:
            return datetime.fromtimestamp(time.mktime(t), tz=timezone.utc)
    return None


def entry_matches_author(entry: Any, author_filter: list[str]) -> bool:
    """Substring match, case-insensitive, against entry.author or entry.authors[]."""
    if not author_filter:
        return True
    author_text = (getattr(entry, "author", "") or "").lower()
    if not author_text:
        authors = getattr(entry, "authors", []) or []
        author_text = " ".join(a.get("name", "") for a in authors).lower()
    return any(name.lower() in author_text for name in author_filter)


def fetch_feed_bytes(url: str) -> bytes | None:
    """Fetch a URL with browser headers. Returns response bytes or None on failure."""
    try:
        response = requests.get(
            url,
            headers=BROWSER_HEADERS,
            timeout=REQUEST_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
    except requests.RequestException as e:
        print(f"    ! HTTP error: {e}")
        return None

    if response.status_code != 200:
        print(f"    ! HTTP {response.status_code}")
        return None

    return response.content


def fetch_rss_items() -> list[dict[str, Any]]:
    """Return a list of fresh RSS items across all configured feeds."""
    sources = load_sources()
    lookback_days = sources.get("rss_lookback_days", 3)
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    items: list[dict[str, Any]] = []
    per_feed_counts: list[tuple[str, int]] = []

    for feed in sources.get("rss_feeds", []):
        name = feed["name"]
        url = feed["url"]
        author_filter = feed.get("author_filter", [])

        print(f"  - {name}: fetching {url}")

        raw = fetch_feed_bytes(url)
        if raw is None:
            per_feed_counts.append((name, 0))
            continue

        parsed = feedparser.parse(raw)

        if parsed.bozo:
            err = getattr(parsed, "bozo_exception", "unknown error")
            print(f"    ! feed parse warning: {err}")

        kept = 0
        for entry in parsed.entries:
            dt = entry_datetime(entry)
            if dt is None or dt < cutoff:
                continue
            if not entry_matches_author(entry, author_filter):
                continue

            summary = (
                getattr(entry, "summary", "")
                or getattr(entry, "description", "")
                or ""
            )
            summary = _strip_html(summary)[:600]

            items.append(
                {
                    "source": name,
                    "tags": feed.get("tags", []),
                    "title": getattr(entry, "title", "Untitled"),
                    "link": getattr(entry, "link", ""),
                    "published": dt.isoformat(),
                    "author": getattr(entry, "author", ""),
                    "summary": summary,
                }
            )
            kept += 1

        print(f"    kept {kept} item(s)")
        per_feed_counts.append((name, kept))

    items.sort(key=lambda x: x["published"], reverse=True)

    print("\n  Feed summary (sorted by yield):")
    for name, kept in sorted(per_feed_counts, key=lambda x: -x[1]):
        marker = " " if kept > 0 else "!"
        print(f"    [{marker}] {kept:>3}  {name}")

    return items


def _strip_html(text: str) -> str:
    """Crude tag stripper. Avoids adding a BeautifulSoup dependency."""
    import re

    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def format_for_claude(items: list[dict[str, Any]]) -> str:
    """Turn fresh RSS items into a clean text block for the synthesis prompt."""
    if not items:
        return "No fresh writing from tracked sources in the lookback window."

    lines = []
    for item in items:
        lines.append("---")
        lines.append(f"SOURCE: {item['source']}")
        lines.append(f"TITLE: {item['title']}")
        if item.get("author"):
            lines.append(f"AUTHOR: {item['author']}")
        lines.append(f"PUBLISHED: {item['published']}")
        lines.append(f"LINK: {item['link']}")
        if item.get("summary"):
            lines.append(f"SUMMARY: {item['summary']}")

    return "\n".join(lines)


if __name__ == "__main__":
    fetched = fetch_rss_items()
    print(f"\nTotal items: {len(fetched)}")
    print(format_for_claude(fetched[:5]))
