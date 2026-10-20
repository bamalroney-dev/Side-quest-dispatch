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

## Offline review packet (added)

The new `scripts/editorial_queue.py` ranks previously researched, source-linked JSON stories and creates a review-only packet. It does **not** call AI or retrieve article bodies. The candidate selection score currently uses only category priority, publication freshness, and a neutral reliability placeholder. Impact and significance remain unscored until supporting evidence and a reviewer exist.

```sh
python scripts/editorial_queue.py input/verified-stories.json --output review/queue.json
python -m unittest discover -s tests -v
```

The input `stories` array uses the same schema as `examples/editorial-draft.json`, including actual source evidence and summaries. The example is illustrative and will fail the 48-hour freshness rule after its sample date. The output has `review_status: pending` and `automatic_publication: false`. Writing directly into `_posts` is refused.

**Next unimplemented steps:** collecting article-level evidence, a real AI adapter with user-approved billing and secrets, claim-level verification, a reviewer approval interface, and a separate approved publication command. Do not merge this branch expecting full automatic AI editing.

## CI

`.github/workflows/editorial-checks.yml` runs offline tests on pull requests affecting editorial code and supports manual triggering. It cannot deploy or write to the repository. The original 7 AM Central publisher is unchanged.

## Step 2: article evidence collector

`scripts/article_evidence.py` reads a JSON `stories` array, fetches public HTML from an explicit publisher-domain allowlist, and saves a **review-only** evidence packet. It captures article title, a publisher-claimed date, metadata description, and up to 8,000 characters of page text. These fields are **not independently fact-checked**. Failures are marked `needs_manual_review`, never silently treated as verified.

The fetcher has HTTPS/domain checks, rejects redirects, checks DNS for non-public addresses, enforces request timeout and response-size limits, and never executes scripts. Publisher access restrictions must be respected. It is not a hardened security boundary against DNS rebinding; only run it with trusted collector-produced URLs in the GitHub runner, not as an arbitrary public URL service.

Example after preparing fresh stories in `review/stories.json`:

```sh
python scripts/article_evidence.py review/stories.json --output review/evidence.json --limit 10
python -m unittest discover -s tests -v
```

The `review/stories.json` input can be produced by the existing `editorial_queue.py` (its output has a `stories` array). **Do not commit retrieved article text to the public repository**; review it locally and respect publishers' terms and copyright. The collector is not wired into the scheduled workflow.

## Step 3: real-world validation checklist

1. Select up to 10 **recent** article URLs from your RSS feed output, across Disney, Pokémon, RuneScape, and BBC.
2. Run the command above locally in a trusted Python 3.12+ environment.
3. Inspect `review/evidence.json` and compare each extracted excerpt and metadata field with its original source page. Flag cookie notices, navigation text, missing dates, paywalls, and errors.
4. Count `extracted_unverified` vs. `needs_manual_review`. A successful extraction **does not** mean the content is verified.
5. Share only redacted status/error summaries for troubleshooting, not full copyrighted article bodies.
6. Run offline CI tests on the PR. Do not merge or enable AI publication yet.

Known limitations: simplistic HTML extraction includes page navigation and other boilerplate; metadata dates may be absent or misleading; publishers can redirect or block automated clients; host allowlist may need review as official article domains evolve. Full article extraction and factual validation are not yet solved.
