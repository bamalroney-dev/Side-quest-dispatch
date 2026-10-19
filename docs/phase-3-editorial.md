# Phase 3 editorial pipeline (review only)

The live 7:00 AM Central RSS publisher is unchanged. This branch adds an **AI-ready JSON contract and structural validator**, not an AI provider or automatic AI publishing.

## Proposed process

1. Existing RSS collector gathers source links.
2. A future editorial adapter can research and draft a JSON package matching `examples/editorial-draft.json`.
3. Run `python scripts/editorial.py examples/editorial-draft.json` to validate structure, freshness, evidence links, duplicate URLs, and event dates.
4. A human reviews source claims, attribution, image rights, and factual accuracy. Structural checks do **not** prove facts or check link availability.
5. A future, separately approved integration may convert approved drafts to Jekyll Markdown. No draft in this branch is published.

## Safety and billing

No AI API calls, API keys, billing, or automatic AI publishing. The validator rejects images pending rights review and events without future timezone-aware dates and official URLs. The current workflow remains unchanged. Merge only after review.

## Run tests

`python -m unittest discover -s tests -v`
