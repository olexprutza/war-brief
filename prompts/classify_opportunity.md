# Classify a SAM.gov opportunity

Given one SAM.gov opportunity, decide its relevance to Anduril's product lines and to the broader defense-tech watchlist.

## Input

A JSON object with these fields (some may be missing):
- `title`
- `solicitationNumber`
- `department` / `subTier` / `office`
- `naicsCode`
- `classificationCode` (PSC)
- `description`
- `postedDate`
- `responseDeadLine`
- `link`

## Output

Return a JSON object with exactly these fields, no prose:

```json
{
  "relevance": "direct" | "adjacent" | "skip",
  "category": "autonomy-air" | "autonomy-ground" | "autonomy-maritime" | "c-uas" | "isr" | "ew" | "c2-software" | "space" | "other",
  "rationale": "one short sentence",
  "keywords_matched": ["..."]
}
```

## Rules

- `direct` means it maps cleanly to an Anduril product line (Lattice, Ghost, Altius, Anvil, Roadrunner, Sentry, Dive-LD, Fury, Pulsar, Bolt) or a near neighbor.
- `adjacent` means it could matter to track (sensors, comms, satellite ground, AI/ML infrastructure).
- `skip` means everything else.
- Be honest about uncertainty. If the description is too thin to tell, mark `skip` and say so in the rationale.
- No prose outside the JSON object. No code fences.
