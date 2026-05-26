"""
War-brief: defense industry intelligence brief.
Pulls writers (RSS) + contract opportunities (SAM.gov), synthesizes via Claude,
writes to public/ for GitHub Pages.
"""

import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import requests
from anthropic import Anthropic
from dotenv import load_dotenv

from fetch_rss import fetch_rss_items, format_for_claude as format_rss_for_claude

load_dotenv()

SAM_KEY = os.getenv("SAM_GOV_API_KEY")
client = Anthropic()

MODEL = "claude-sonnet-4-6"  # bumped from claude-sonnet-4-5

NAICS_CODES = ["541715", "334511", "336411", "336414", "541512"]
WATCH_COMPANIES = ["Anduril", "Palantir", "SpaceX", "Kratos", "Amazon", "Kuiper", "Starshield"]

PUBLIC_DIR = Path("public")


def fetch_sam_opportunities():
    """Fetch contract opportunities from SAM.gov posted in the last 24 hours."""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%m/%d/%Y")
    today = datetime.now().strftime("%m/%d/%Y")

    all_opportunities = []

    for code in NAICS_CODES:
        url = "https://api.sam.gov/opportunities/v2/search"
        params = {
            "api_key": SAM_KEY,
            "postedFrom": yesterday,
            "postedTo": today,
            "ncode": code,
            "limit": 50,
        }
        response = requests.get(url, params=params)
        if response.status_code != 200:
            print(f"  ! SAM.gov error for NAICS {code}: {response.status_code}")
            continue
        data = response.json()
        opps = data.get("opportunitiesData", [])
        print(f"  - NAICS {code}: {len(opps)} opportunities")
        all_opportunities.extend(opps)

    return all_opportunities


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
    """Send everything to Claude with the new prompt shape."""
    watch_list = ", ".join(WATCH_COMPANIES)

    prompt_path = Path("prompts/synthesize_brief.md")
    base_prompt = prompt_path.read_text() if prompt_path.exists() else _fallback_prompt()

    prompt = f"""{base_prompt}

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
    """If prompts/synthesize_brief.md is missing, fall back to a minimal inline prompt."""
    return (
        "You are an analyst writing a morning defense industry brief for a single reader "
        "preparing for a Business Development role at Anduril. Lead with the must-reads from "
        "tracked writers; keep contract opportunities tight. Every cited item must include its "
        "direct URL. Be terse. Use markdown."
    )


def render_markdown_to_html(md: str) -> str:
    """Minimal markdown-to-HTML converter. Headers, bold, italic, links, lists, paragraphs."""
    # Escape HTML first
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

        # Headers
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            close_paragraph()
            close_list()
            level = len(m.group(1))
            content = _inline_md(m.group(2))
            out.append(f"<h{level}>{content}</h{level}>")
            continue

        # Horizontal rule
        if re.match(r"^-{3,}\s*$", line):
            close_paragraph()
            close_list()
            out.append("<hr>")
            continue

        # List items
        m = re.match(r"^\s*[-*]\s+(.*)$", line)
        if m:
            close_paragraph()
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline_md(m.group(1))}</li>")
            continue

        # Paragraph
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
    # Links: [text](url)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>',
        text,
    )
    # Bold: **text**
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    # Italic: *text*
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    # Inline code
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text


def write_outputs(brief_markdown: str):
    """Write the brief as dated markdown, current index.html, and update archive.html."""
    PUBLIC_DIR.mkdir(exist_ok=True)

    today_str = datetime.now().strftime("%Y-%m-%d")
    pretty_date = datetime.now().strftime("%A, %B %d, %Y")

    # Dated markdown archive
    md_path = PUBLIC_DIR / f"{today_str}.md"
    md_path.write_text(brief_markdown, encoding="utf-8")
    print(f"Wrote {md_path}")

    # Dated HTML
    body_html = render_markdown_to_html(brief_markdown)
    page_html = _wrap_html(body_html, pretty_date, today_str)

    dated_html_path = PUBLIC_DIR / f"{today_str}.html"
    dated_html_path.write_text(page_html, encoding="utf-8")
    print(f"Wrote {dated_html_path}")

    # Latest brief lives at index.html
    index_path = PUBLIC_DIR / "index.html"
    index_path.write_text(page_html, encoding="utf-8")
    print(f"Wrote {index_path}")

    # Archive page lists all dated briefs
    _write_archive()

    # Make sure static files (style.css, sources.html) get copied into public/.
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
    """Build archive.html from every *.md in public/."""
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
    print(f"\n=== war-brief · {datetime.now().strftime('%A, %B %d, %Y')} ===\n")

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
