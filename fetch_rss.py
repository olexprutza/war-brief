"""
RSS fetcher for war-brief.
Reads docs/sources.yaml, pulls every feed, filters by recency and (optionally) author.
"""

from __future__ import annotations

import socket
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import feedparser
import yaml

SOURCES_PATH = Path("docs/sources.yaml")

# Some publishers (Substack especially) block requests that don't look like a browser.
# Setting these gets us back into Substack, Medium, and a few other strict hosts.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Safari/605.1.15"
)
REQUEST_HEADERS = {
    "User-Agent": BROWSER_USER_AGENT,
    "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
    "Accept-Language": "en-US,en;q=0.9",
}

# Don't let a single slow feed hang the whole run.
FEED_TIMEOUT_SECONDS = 15


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
    """Check if entry's author matches any name in the filter (substring match, case-insensitive)."""
    if not author_filter:
        return True
    author_text = (getattr(entry, "author", "") or "").lower()
    if not author_text:
        # Some feeds put author info in dc:creator or authors[]
        authors = getattr(entry, "authors", []) or []
        author_text = " ".join(a.get("name", "") for a in authors).lower()
    return any(name.lower() in author_text for name in author_filter)


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

        # Temporarily lower the socket timeout so a dead host can't hang us.
        previous_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(FEED_TIMEOUT_SECONDS)
        try:
            parsed = feedparser.parse(url, request_headers=REQUEST_HEADERS)
        except Exception as e:
            print(f"    ! fetch failed: {e}")
            socket.setdefaulttimeout(previous_timeout)
            continue
        finally:
            socket.setdefaulttimeout(previous_timeout)

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
            # Strip HTML tags crudely. Good enough for synthesis input.
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

    # Most recent first
    items.sort(key=lambda x: x["published"], reverse=True)

    # Summary so you can scan feed health at a glance
    print("\n  Feed summary (sorted by yield):")
    for name, kept in sorted(per_feed_counts, key=lambda x: -x[1]):
        marker = " " if kept > 0 else "!"
        print(f"    [{marker}] {kept:>3}  {name}")

    return items


def _strip_html(text: str) -> str:
    """Crude tag stripper. Avoids adding a dependency on BeautifulSoup."""
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
