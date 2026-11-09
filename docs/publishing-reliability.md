# Publishing reliability: review plan

This branch is **review-only**. Do not merge or publish without approval.

## Observed baseline (November 2026)

- Scheduled Nov 6, 7, and 8 runs completed and committed 21, 15, and 13 stories.
- Scheduled jobs were delayed hours past 7 AM Central. The current late-run guard allows them.
- The Pokémon News RSS feed repeatedly returned HTTP 404. Do not replace it with an unverified URL.
- A successful job can mean `already_exists` or `no_fresh_stories`, not publication.
- A generator-created file is **not** proof of a git push or Pages deployment.

## Review changes

- Every generator exit emits a machine-readable `DISPATCH_RESULT` with one of `generated`, `already_exists`, `no_fresh_stories`, `early_dst_skip`, or `dry_run`.
- Category diagnostics count stale, future-dated, previously published, same-run duplicates, and category-limit rejections, alongside feed errors.
- Daily workflow renders an Actions step summary, while retaining its existing commit behavior.
- `Dispatch Recovery Preview` is manually triggered, **read-only**, and runs the generator with `--dry-run`. It neither commits nor deploys.
- Tests cover diagnostic classifications, output parsing, dry-run file safety, and existing-edition protection.

## Recovery procedure (after approval and merge)

1. Inspect the daily workflow's summary and git commit step, then the separate Pages deployment.
2. If a post already exists, **do not overwrite it**; inspect that edition.
3. If no post exists, run `Dispatch Recovery Preview` from Actions. Confirm `dry_run` and selected story count.
4. If the preview is satisfactory, explicitly authorize a manual run of the existing `Daily Side Quest Dispatch` workflow on `main`. It can create and push a post, so do not invoke it without approval.
5. Verify the post commit, story index, and Pages deployment. Never infer publication solely from `generated`.
6. If no qualifying stories exist, treat `no_fresh_stories` as a legitimate skip and investigate source coverage separately.

## Known limitations

- GitHub Actions scheduling delay is controlled by GitHub, not the generator.
- Broken feeds are reported but not automatically replaced.
- A read-only preview fetches live RSS feeds; its results may differ from a later manual publishing run.
- There is no automatic retry or push from this review branch.
