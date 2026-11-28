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
| `briefing-draft.md` | The workflow generates a review draft with up to three linked candidates per source, with new URLs first. |
| `claim-verification.json` | Source URLs and field-level results for the selected gaming candidates. Results can be verified, unverified, conflicting, or unavailable. |

Articles are validated against [the article schema](article.schema.json). Canonicalization prefers FeedBurner's original article link, collapses the publisher's www and bare domains, strips tracking parameters and fragments, and keeps other query parameters. Publication timestamps are converted to UTC when available. Website discovery uses dated publisher links and their visible titles, coalesces repeated links, and returns up to 30 articles with a null publication timestamp and empty summary. RSS entries may also lack a publication timestamp. Metadata is source-reported and can include older articles. Use `latest_published_at` to judge feed freshness.

The database is authoritative. Each JSON file is replaced atomically, and the run IDs show which attempt a reader is seeing. A partial failure preserves the successful sources in the new snapshot and reports failures with their last successful collection times. A failed run without usable results exits with code 1 and keeps the last usable snapshot. A successful fallback or malformed records report `degraded`. Within a run, if two sources return the same canonical URL, the first collector's record goes into the snapshot and the later source reports the duplicate.

To generate the review draft locally from the current snapshot:

```sh
python -m research.briefing --verify --output research-data/briefing-draft.md
```

The draft identifies failed sources and refuses to use a prior snapshot after a failed collection. It links to candidate sources and includes only structured claims that passed verification. The original headlines and summaries remain in `latest.json`. Omitting `--verify` generates a link-only draft without fetching evidence.

Pokémon release dates require a unique product match and an exact date in the official press schedule. Pokémon MSRP still requires separate official product evidence. Epic's price and deadline require a fresh U.S. catalog response that matches the collected product and promotion window. The briefing omits expired offers. Amazon Luna's announcement can help identify games for review. Account-specific claims, eligibility, and deadlines require a separate check.

## Run on GitHub Actions

Once GitHub registers the workflow on the default branch, open **Actions → Research collection → Run workflow** and select the desired ref. Download the `research-data` artifact from the run summary. Failed collection runs also upload their diagnostics when available. The workflow runs on manual dispatch and uploads artifacts with read-only repository permissions.

GitHub runners start with an empty filesystem. To continue history, supply the numeric `history_run_id` from a prior run in this repository whose `research-data` artifact is still available. Save `history.sqlite3` separately when you need to retain history beyond GitHub's artifact retention period.

## Editorial handoff

**Research editorial handoff** is a separate manual workflow. It reads a completed **Research collection** run on `main`. Use the large run ID from the Actions URL for both operations.

1. Configure the `NOTION_TOKEN` repository secret with a Notion connection that has read and insert access to the briefing archive. Connect it to the archive page in Notion and set its UUID as the `NOTION_BRIEFING_PARENT_ID` repository variable.
2. Run **Research editorial handoff** on `main` with **archive**. The workflow creates a review page titled **Side Quest Dispatch Research Review** followed by the run ID. A repeat checks the page and its receipt before reusing it. Use one handoff path at a time for each run.
3. An editor reviews the sources in that page and copies the exact source URLs they select. Run the workflow with **draft_pr**, the same run ID, the selected URLs separated by spaces, and the proposed edition date. The workflow proposes a separate research roundup in a draft PR from a review branch. It checks the archived receipt before accepting any URL. If the repository policy blocks Actions from creating a PR, the run reports the review-branch comparison link for opening it manually.
4. Use the **editorial-status** artifact to refresh the **Side Quest Dispatch Research Status** Page in the Personal Command Center. The report includes source and handoff status and flags dated source material or last successful collections older than 48 hours. The GitHub workflow generates the report. Updating the Space Page is a manual handoff through its connected Pages tool.

The Notion archive receipt records which source URLs appeared in the review draft and their verified fields at the time. Collection history still tracks which URLs were fetched. Repeat coverage stays out of later Notion drafts unless a verified field changes. If a run has no new or changed items, the workflow reports that outcome without creating a review page.

For a local preview, download and extract the collection artifact:

```sh
python -m research.editorial_cli preview --run-id 46142444937 --data-dir research-data --output-dir research-data/editorial-preview
```

The preview produces Notion-ready Markdown, a receipt, and a status report. Pass `--receipts` with a JSON array of prior archive receipts to preview coverage filtering. To preview a particular publication selection, use `review` with `--edition-date`, one or more `--select-url` options, and `--receipt` with the archive receipt. This writes `edition-preview.md` locally. The publication workflow reads the actual receipt from Notion before opening a draft PR.

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
