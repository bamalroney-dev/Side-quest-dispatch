# Pokémon TCG discovery automation

This is a **review-only** discovery system. It does not change the public tracker, merge a PR, or publish a site.

- Current Jekyll tracker: `pokemon-tcg/releases.md`
- Published dataset: `_data/pokemon_tcg_releases.json`
- Proposed announcements: `data/pokemon-tcg-review-queue.json`
- Run manually: `python scripts/pokemon_tcg_discovery.py`
- Preview without writing: `python scripts/pokemon_tcg_discovery.py --dry-run`
- Tests: `python -m unittest discover -s tests -p 'test_pokemon_tcg_discovery.py' -v`

The discovery job scans official Pokémon news and press pages twice daily **only after this workflow reaches the default branch**. Until then, use manual runs on this feature branch. GitHub Actions may need permission to create pull requests (Settings > Actions > General). An existing review PR may require manual reconciliation if its branch diverges.

**Important:** A news headline is not a product SKU. Candidates intentionally have no release date or MSRP until someone checks the original official announcement. The tracker dataset requires unique IDs and never treats third-party reference prices as manufacturer MSRP. Existing prices were migrated to `reference_price_usd`, with `msrp_usd: null`.

Before merging this feature: run tests, build Jekyll, check tracker on mobile, verify discovered candidate links, and confirm Actions permissions. The review PR should be reviewed, not auto-merged.
