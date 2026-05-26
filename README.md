# war-brief

A personal morning intelligence brief on the U.S. defense industry.

Three mornings a week (Monday, Wednesday, Friday), a GitHub Actions job pulls fresh contract opportunities from SAM.gov and posts from a curated set of RSS feeds, then uses the Anthropic Claude API to synthesize the day's signal into a short brief. The output is published to GitHub Pages and read on a phone over morning coffee.

## Why

I am joining the Business Development team at Anduril and learning the defense industry from the outside. war-brief is the system I read to stay current and to track the companies, program offices, and policy shifts that matter for the job.

## Sources

- SAM.gov Opportunities API (federal contract notices)
- RSS: Anduril, Palantir, SpaceX, Kratos, Amazon Kuiper, Breaking Defense, Defense News, and selected analysts. Full list in `docs/sources.yaml`.

## Stack

Python, GitHub Actions, GitHub Pages, Anthropic Claude API.

## Setup

```bash
git clone git@github.com:olexprutza/war-brief.git
cd war-brief
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY and SAM_API_KEY
```

## License

Personal project. No license granted.
