"""
War-brief: daily defense industry intelligence brief.
Pulls from SAM.gov, synthesizes via Claude, prints to terminal.
"""

import os
import requests
from datetime import datetime, timedelta
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

SAM_KEY = os.getenv("SAM_GOV_API_KEY")
client = Anthropic()

# NAICS codes relevant to defense tech.
# 541715: R&D in physical, engineering, life sciences
# 334511: Search, detection, navigation, guidance instruments
# 336411: Aircraft manufacturing
# 336414: Guided missile and space vehicle manufacturing
# 541512: Computer systems design services (often DoD-relevant)
NAICS_CODES = ["541715", "334511", "336411", "336414", "541512"]

# Companies we care about most.
# The script flags any opportunity that mentions these.
WATCH_COMPANIES = ["Anduril", "Palantir", "SpaceX", "Kratos", "Amazon", "Kuiper", "Starshield"]


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


def format_for_claude(opportunities):
    """Turn the raw SAM.gov response into a clean text block for Claude."""
    if not opportunities:
        return "No new opportunities in the last 24 hours."
    
    lines = []
    for opp in opportunities:
        title = opp.get("title", "Untitled")
        agency = opp.get("fullParentPathName", "Unknown agency")
        posted = opp.get("postedDate", "")
        notice_type = opp.get("type", "")
        desc = opp.get("description", "")[:500]  # cap description length
        link = opp.get("uiLink", "")
        
        lines.append(f"---")
        lines.append(f"TITLE: {title}")
        lines.append(f"AGENCY: {agency}")
        lines.append(f"POSTED: {posted}")
        lines.append(f"TYPE: {notice_type}")
        lines.append(f"DESCRIPTION: {desc}")
        lines.append(f"LINK: {link}")
    
    return "\n".join(lines)


def synthesize_brief(opportunities_text):
    """Send opportunities to Claude with a synthesis prompt."""
    
    watch_list = ", ".join(WATCH_COMPANIES)
    
    prompt = f"""You are my morning defense industry analyst. I am preparing for a Business Development role at Anduril.

Below are contract opportunities posted to SAM.gov in the last 24 hours, filtered to defense-relevant NAICS codes.

Your task:

1. Identify the 3-7 most consequential opportunities. Skip routine ones (basic supplies, facility maintenance, low-dollar set-asides) unless they reveal something about acquisition patterns.

2. For each chosen opportunity, give me:
   - One-sentence summary of what is being sought
   - The agency or program office
   - Why it matters competitively, especially for {watch_list}
   - Whether it suggests a shift in DoW (Department of War) acquisition behavior

3. End with three sharp questions a BD analyst at Anduril should be asking based on what you see.

4. If you see any opportunities directly mentioning {watch_list}, flag them at the top.

Be terse. No filler. No "I hope this helps." Write like you respect my time.

OPPORTUNITIES:

{opportunities_text}
"""
    
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    return message.content[0].text


def main():
    print(f"\n=== War-brief for {datetime.now().strftime('%A, %B %d, %Y')} ===\n")
    print("Fetching SAM.gov opportunities...")
    
    opportunities = fetch_sam_opportunities()
    print(f"\nTotal raw opportunities pulled: {len(opportunities)}\n")
    
    formatted = format_for_claude(opportunities)
    
    print("Sending to Claude for synthesis...\n")
    brief = synthesize_brief(formatted)
    
    print("=" * 60)
    print(brief)
    print("=" * 60)
    print(f"\nSource: SAM.gov public Contract Opportunities API. U.S. Government public data.\n")


if __name__ == "__main__":
    main()
