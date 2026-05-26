# war-brief

A personal morning intelligence brief on the U.S. defense industry. Pulls contract opportunities from SAM.gov and posts from a chosen set of RSS feeds, then synthesizes the day's signal into a short brief read on a phone. Hosted on GitHub Pages, run on a GitHub Actions schedule (Monday, Wednesday, Friday mornings).

Single user, single maintainer: Olexa Prutza.

## Tech stack

- Python 3.11+
- GitHub Actions (cron schedule)
- GitHub Pages (static site hosting)
- Anthropic Claude API for synthesis
- SAM.gov public Opportunities API
- `feedparser` for RSS, `requests` for HTTP, `python-dotenv` for local secrets

## Layout

```
war-brief/
├── CLAUDE.md              # this file
├── README.md              # human-facing project description
├── .gitignore
├── .env.example           # template for local secrets, safe to commit
├── requirements.txt
├── src/
│   ├── fetch_sam.py       # pulls SAM.gov opportunities
│   ├── fetch_rss.py       # pulls RSS feeds
│   ├── synthesize.py      # calls Claude API to build the brief
│   └── render.py          # writes the static HTML for GitHub Pages
├── prompts/               # prompt text files, version-controlled
├── docs/                  # reference material: glossary, people, programs
├── samples/               # past brief outputs for reference
├── public/                # generated static site, deployed to Pages
└── .github/workflows/
    └── brief.yml          # daily cron + deploy
```

## Commands

Local setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # then fill in real keys
```

Local run:

```bash
python -m src.fetch_sam
python -m src.fetch_rss
python -m src.synthesize
python -m src.render
```

Manually trigger the Action: GitHub UI → Actions → war-brief → Run workflow.

## Secrets

Local: `.env` file, never committed. Loaded with `python-dotenv`.

CI: GitHub Actions secrets at Settings → Secrets and variables → Actions. Required keys:

- `ANTHROPIC_API_KEY`
- `SAM_API_KEY`

`.env` and any file matching `.env.*` (except `.env.example`) are gitignored.

## Writing rules for Claude

When generating prose for the brief, code comments, commit messages, or any text the user reads:

- Lean toward Anglo-Saxon-rooted English. Plain words over Latinate ones when both work.
- No sycophancy. No "Great question!" No "Let's take a moment to see what we've accomplished."
- No antithesis as a rhetorical crutch. Drop "It's not X, it's Y" when a direct statement does the job.
- No restating what the user just said.
- No unsolicited career or theological commentary.
- When a mistake happens, say so plainly and explain the fix.
- Concise beats warm.

## Coding conventions

- Python: standard library first, then `requests`, `feedparser`, `anthropic`, `python-dotenv`. Keep dependencies few.
- One module per concern. `fetch_*` modules only fetch and return data structures. Synthesis and rendering are separate.
- Source lists (RSS feeds, SAM.gov queries) live in `docs/sources.yaml`, not hardcoded.
- Prompts live in `prompts/*.md`, loaded as text at runtime. Do not embed long prompts in `.py` files.
- Acronyms get expanded on first use in any prose output. The glossary lives at `docs/glossary.md`.

## Domain context

The user is preparing to join Anduril's Business Development team. The brief should sharpen his read on:

- DoW (Department of War) acquisition reform: OTA (Other Transaction Authority), middle-tier acquisition, software acquisition pathway.
- Program offices and PEOs (Program Executive Offices) relevant to autonomous systems and counter-UAS (counter-Unmanned Aerial Systems).
- Competitive landscape: Anduril, Palantir, SpaceX, Kratos, Amazon Kuiper.
- Analysts and writers worth following. List lives in `docs/people.md`.

The user is new to the defense industry but technically capable. Explain acronyms on first use. Do not over-explain code patterns he has already shown he knows (venv, `.env`, basic Git, SSH).

## Do not touch

- `.env` (local secrets)
- Anything under `public/` is generated. Edit the source modules and rebuild.
- Force pushes to `main`.
