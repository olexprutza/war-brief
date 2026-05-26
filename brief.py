"""
War-brief: defense industry intelligence brief.
Pulls writers (RSS) + contract opportunities (SAM.gov), synthesizes via Claude,
writes to public/ for GitHub Pages.

All dates are in America/New_York so the brief reads naturally on a US morning,
regardless of where the GitHub runner happens to be running.
"""

import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from anthropic import Anthropic
from dotenv import load_dotenv

from fetch_rss import fetch_rss_items, format_for_claude as format_rss_for_claude

load_dotenv()

SAM_KEY = os.getenv("SAM_GOV_API_KEY")
client = Anthropic()

MODEL = "claude-sonnet-4-6"

NAICS_CODES = ["541715", "334511", "336411", "336414", "541512"]
WATCH_COMPANIES = ["Anduril", "Palantir", "SpaceX", "Kratos", "Amazon", "Kuiper", "Starshield"]

PUBLIC_DIR = Path("public")
EASTERN = ZoneInfo("America/New_York")

# SAM.gov rate-limit hygiene
SAM_SLEEP_SECONDS = 1.5  # delay between calls
SAM_RETRY_DELAY = 8      # wait this long on a 429 before one retry
SAM_MAX_RETRIES = 1


def now_eastern() -> datetime:
    return datetime.now(EASTERN)


def fetch_sam_opportunities():
    """Fetch contract opportunities from SAM.gov posted in the last 24 hours."""
    yesterday = (now_eastern() - timedelta(days=1)).strftime("%m/%d/%Y")
    today = now_eastern().strftime("%m/%d/%Y")

    all_opportunities = []

    for code in NAICS_CODES:
        opps = _fetch_one_naics(code, yesterday, today)
        all_opportunities.extend(opps)
        time.sleep(SAM_SLEEP_SECONDS)

    return all_opportunities


def _fetch_one_naics(code: str, posted_from: str, posted_to: str) -> list:
    """Fetch one NAICS code from SAM.gov, with one retry on 429."""
    url = "https://api.sam.gov/opportunities/v2/search"
    params = {
        "api_key": SAM_KEY,
        "postedFrom": posted_from,
        "postedTo": posted_to,
        "ncode": code,
        "limit": 50,
    }

    for attempt in range(SAM_MAX_RETRIES + 1):
        try:
            response = requests.get(url, params=params, timeout=20)
        except requests.RequestException as e:
            print(f"  ! SAM.gov network error for NAICS {code}: {e}")
            return []

        if response.status_code == 200:
            data = response.json()
            opps = data.get("opportunitiesData", [])
            print(f"  - NAICS {code}: {len(opps)} opportunities")
            return opps

        if response.status_code == 429 and attempt < SAM_MAX_RETRIES:
            print(f"  ! SAM.gov rate-limited on NAICS {code}; sleeping {SAM_RETRY_DELAY}s and retrying")
            time.sleep(SAM_RETRY_DELAY)
            continue

        print(f"  ! SAM.gov error for NAICS {code}: {response.status_code}")
        return []

    return []


def format_sam_for_claude(opportunities):
    if not opportunities:
        return "No new opportunities in the last 24 hours."

    lines = []
    for opp in opportunities:
        lines.append("---")
        lines.append(f"TITLE: {opp.get('title', 'Untitled')}")
        lines.append(f"AGENCY: {opp.get('fullParentPathName', 'Unknown agency')}")
        lines.append(f"POSTED: {opp.get('postedDate', '')}")
        lines.append(f"TYPE: {opp.get('type', '')}")
        lines.append(f"DESCRIPTION: {opp.get('description', '')[:500]}")
        lines.append(f"LINK: {opp.get('uiLink', '')}")

    return "\n".join(lines)


def synthesize_brief(rss_text: str, sam_text: str) -> str:
    """Send everything to Claude with the prompt from prompts/synthesize_brief.md."""
    watch_list = ", ".join(WATCH_COMPANIES)
    today_pretty = now_eastern().strftime("%A, %B %d, %Y")

    prompt_path = Path("prompts/synthesize_brief.md")
    base_prompt = prompt_path.read_text() if prompt_path.exists() else _fallback_prompt()

    prompt = f"""{base_prompt}

TODAY: {today_pretty}
WATCH LIST: {watch_list}

---

WRITING FROM TRACKED SOURCES (last 3 days):

{rss_text}

---

CONTRACT OPPORTUNITIES (SAM.gov, last 24 hours):

{sam_text}
"""

    message = client.messages.create(
        model=MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def _fallback_prompt() -> str:
    return (
        "You are an analyst writing a morning defense industry brief for a single reader "
        "preparing for a Business Development role at Anduril. Lead with the must-reads from "
        "tracked writers; keep contract opportunities tight. Every cited item must include its "
        "direct URL. Be terse. Use markdown."
    )


def render_markdown_to_html(md: str) -> str:
    """Minimal markdown-to-HTML converter."""
    md = md.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    lines = md.split("\n")
    out = []
    in_list = False
    in_paragraph = False

    def close_paragraph():
        nonlocal in_paragraph
        if in_paragraph:
            out.append("</p>")
            in_paragraph = False

    def close_list():
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            close_paragraph()
            close_list()
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            close_paragraph()
            close_list()
            level = len(m.group(1))
            content = _inline_md(m.group(2))
            out.append(f"<h{level}>{content}</h{level}>")
            continue

        if re.match(r"^-{3,}\s*$", line):
            close_paragraph()
            close_list()
            out.append("<hr>")
            continue

        m = re.match(r"^\s*[-*]\s+(.*)$", line)
        if m:
            close_paragraph()
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline_md(m.group(1))}</li>")
            continue

        close_list()
        if not in_paragraph:
            out.append("<p>")
            in_paragraph = True
        out.append(_inline_md(line))

    close_paragraph()
    close_list()
    return "\n".join(out)


def _inline_md(text: str) -> str:
    """Inline markdown: bold, italic, links, inline code."""
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>',
        text,
    )
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text


def write_outputs(brief_markdown: str):
    """Write dated markdown, dated HTML, index.html, and refresh archive.html."""
    PUBLIC_DIR.mkdir(exist_ok=True)

    today_str = now_eastern().strftime("%Y-%m-%d")
    pretty_date = now_eastern().strftime("%A, %B %d, %Y")

    md_path = PUBLIC_DIR / f"{today_str}.md"
    md_path.write_text(brief_markdown, encoding="utf-8")
    print(f"Wrote {md_path}")

    body_html = render_markdown_to_html(brief_markdown)
    page_html = _wrap_html(body_html, pretty_date, today_str)

    dated_html_path = PUBLIC_DIR / f"{today_str}.html"
    dated_html_path.write_text(page_html, encoding="utf-8")
    print(f"Wrote {dated_html_path}")

    index_path = PUBLIC_DIR / "index.html"
    index_path.write_text(page_html, encoding="utf-8")
    print(f"Wrote {index_path}")

    _write_archive()
    _ensure_static_files()


def _wrap_html(body_html: str, pretty_date: str, iso_date: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>war-brief · {pretty_date}</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<header class="masthead">
  <div class="masthead-inner">
    <a href="index.html" class="brand">war-brief</a>
    <time datetime="{iso_date}" class="date">{pretty_date}</time>
  <nav>
    <a href="archive.html">archive</a>
    <a href="sources.html">sources</a>
  </nav>
  </div>
</header>
<main class="brief">
{body_html}
</main>
<footer class="brief-footer">
  <p>Sources: SAM.gov public Contract Opportunities API and selected RSS feeds. Synthesized by Anthropic Claude. <a href="https://github.com/olexprutza/war-brief">Source code</a>.</p>
</footer>
</body>
</html>
"""


def _write_archive():
    """Build archive.html from every dated *.md in public/."""
    dated_files = sorted(
        [p for p in PUBLIC_DIR.glob("*.md") if re.match(r"\d{4}-\d{2}-\d{2}\.md", p.name)],
        reverse=True,
    )

    items_html = []
    for f in dated_files:
        date_str = f.stem
        try:
            pretty = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %B %d, %Y")
        except ValueError:
            pretty = date_str
        items_html.append(
            f'<li><a href="{date_str}.html">{pretty}</a></li>'
        )

    list_html = "\n".join(items_html) if items_html else "<li>No briefs yet.</li>"

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>war-brief · archive</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<header class="masthead">
  <div class="masthead-inner">
    <a href="index.html" class="brand">war-brief</a>
    <span class="date">archive</span>
  <nav>
    <a href="index.html">latest</a>
    <a href="sources.html">sources</a>
  </nav>
  </div>
</header>
<main class="brief">
<h1>All briefs</h1>
<ul class="archive-list">
{list_html}
</ul>
</main>
<footer class="brief-footer">
  <p><a href="https://github.com/olexprutza/war-brief">Source code</a>.</p>
</footer>
</body>
</html>
"""
    (PUBLIC_DIR / "archive.html").write_text(page, encoding="utf-8")
    print(f"Wrote {PUBLIC_DIR / 'archive.html'}")


def _ensure_static_files():
    """Copy static files (style.css, sources.html) from the repo root into public/."""
    for filename in ("style.css", "sources.html"):
        src = Path(filename)
        if src.exists():
            dest = PUBLIC_DIR / filename
            dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"Wrote {dest}")
        else:
            print(f"  ! {filename} not found at repo root")


def main():
    print(f"\n=== war-brief · {now_eastern().strftime('%A, %B %d, %Y')} (Eastern) ===\n")

    print("Fetching RSS feeds...")
    rss_items = fetch_rss_items()
    print(f"\nTotal fresh RSS items: {len(rss_items)}\n")

    print("Fetching SAM.gov opportunities...")
    sam_opps = fetch_sam_opportunities()
    print(f"\nTotal SAM opportunities: {len(sam_opps)}\n")

    rss_text = format_rss_for_claude(rss_items)
    sam_text = format_sam_for_claude(sam_opps)

    print(f"Sending to {MODEL}...\n")
    brief = synthesize_brief(rss_text, sam_text)

    write_outputs(brief)

    print("\n" + "=" * 60)
    print(brief)
    print("=" * 60)


if __name__ == "__main__":
    main()
