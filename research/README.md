# Research collection

The pipeline collects evidence for Side Quest Dispatch review.

| Source | Collection and coverage |
| --- | --- |
| Disney Food Blog | [FeedBurner](https://feeds.feedburner.com/disneyfoodblog/feed), then the [original RSS feed](https://www.disneyfoodblog.com/feed/), then [The Latest](https://www.disneyfoodblog.com/the-latest/). A fetch error, invalid RSS, or zero usable records advances to the next endpoint. |
| Pokémon TCG | Reuses the existing official news and press discovery parser. Candidates retain `needs_verification`. Verify release dates, products, and prices against official evidence. |
| Epic Games Store | Checks Epic's U.S. storefront data for active zero-price base-game promotions with a dated offer window. Verify claim terms on the [store](https://store.epicgames.com/en-US/free-games) before briefing readers. Repeated promotions for a product share its URL in history. |
| Amazon Luna (Prime Gaming) | The [Amazon Game Studios newsroom](https://www.amazongamestudios.com/en-us/news/) provides monthly Luna announcements. The snapshot links to the newest announcement. Individual PC claims, member eligibility, and deadlines need verification on the [claims page](https://gaming.amazon.com/). |
| Old School RuneScape | Reuses the official OSRS RSS endpoint in the editorial source registry. |

## Run locally

From the repository root with Python 3.10 or newer, preferably in a virtual environment:

```sh
python -m pip install -r research/requirements.txt
python -m research
```

Reusing the same `--output-dir` continues the collection history. The default is `research-data/`. Use `--verbose` to see why individual RSS entries were skipped.

| File | Contents |
| --- | --- |
| `latest.json` | Unique articles from the most recent usable collection, plus the URLs already seen on earlier runs. An initial failure creates an empty snapshot with a null run ID. |
| `source-health.json` | The latest attempt's source status, fallback checks, HTTP errors, retries, and new, repeated, duplicate, and skipped article counts. It includes the current snapshot's run ID and the last successful collection time. |
| `history.sqlite3` | All runs and the latest observed metadata for each canonical URL, with first and last run IDs. Back up this file to preserve history. |
| `briefing-draft.md` | The workflow generates a review draft with up to three candidates per source, with new URLs first. |

Articles are validated against [the article schema](article.schema.json). Canonicalization prefers FeedBurner's original article link, collapses the publisher's www and bare domains, strips tracking parameters and fragments, and keeps other query parameters. Publication timestamps are converted to UTC when available. Website discovery uses dated publisher links and their visible titles, coalesces repeated links, and returns up to 30 articles with a null publication timestamp and empty summary. RSS entries may also lack a publication timestamp. Metadata is source-reported and can include older articles. Use `latest_published_at` to judge feed freshness.

The database is authoritative. Each JSON file is replaced atomically, and the run IDs show which attempt a reader is seeing. A partial failure preserves the successful sources in the new snapshot and reports failures with their last successful collection times. A failed run without usable results exits with code 1 and keeps the last usable snapshot. A successful fallback or malformed records report `degraded`. Within a run, if two sources return the same canonical URL, the first collector's record goes into the snapshot and the later source reports the duplicate.

To generate the review draft locally from the current snapshot:

```sh
python -m research.briefing --output research-data/briefing-draft.md
```

The draft identifies failed sources and refuses to use a prior snapshot after a failed collection. Review the links and source claims before copying material into the Notion briefing archive.

## Run on GitHub Actions

Once GitHub registers the workflow on the default branch, open **Actions → Research collection → Run workflow** and select the desired ref. Download the `research-data` artifact from the run summary. Failed collection runs also upload their diagnostics when available. The workflow runs on manual dispatch and uploads artifacts with read-only repository permissions.

GitHub runners start with an empty filesystem. To continue history, supply the numeric `history_run_id` from a prior run in this repository whose `research-data` artifact is still available. Save `history.sqlite3` separately when you need to retain history beyond GitHub's artifact retention period.

## Troubleshoot

- Read `source-health.json` for the endpoint, error stage, attempt count, and HTTP status when available. The HTTP client uses a 12-second socket timeout and up to three attempts for transient errors. Backoff is capped at 30 seconds.
- For a 403 or an HTML challenge page, confirm the publisher's endpoint availability and try another run later. Website discovery depends on the publisher's markup and access rules.
- If the workflow cannot restore history, verify the prior run ID and artifact availability. For local storage or export errors, verify write access and free space, then rerun against the same database.

## Offline tests

```sh
python -m unittest discover -s research/tests -v
python -m unittest discover -s tests -v
```

The repository suite uses Bash and Git. Run it on Linux or WSL to match the GitHub runner. The research tests use local fixtures and mocked HTTP responses.
