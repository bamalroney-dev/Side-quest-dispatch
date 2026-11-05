# Pokémon TCG tracker: review checklist

Status: review only. Do not merge or publish without explicit owner approval.

## Implemented
- Jekyll page at `/pokemon-tcg/releases/` with client-side name and date filtering.
- JSON snapshot in `_data/pokemon_tcg_releases.json` with source links and verification labels.
- Date precision retained: November-only releases use `2026-11`, not an invented day.

## Source policy
- Release dates and product names: Pokémon's October and November 2026 official product roundups.
- US price reference: Celadon Info, a third-party tracker, explicitly labeled `third-party`.
- A third-party price is **not** manufacturer-confirmed MSRP. Unknown prices remain null.
- Booster display $161.64 is third-party reference, not a separately verified manufacturer MSRP.
- Never imply retailer stock is live without a timestamped retailer source.

## Before approval
- Verify Jekyll build and check mobile/table rendering.
- Independently confirm MSRP from Pokémon Center or manufacturer where possible.
- Expand verified variants and retailer links; avoid guessed stock availability.
- Decide whether the website should auto-update via a review-only GitHub Action. No automated workflow is installed yet.
- Obtain explicit approval before merging to main or publishing.

## Sources
- https://www.pokemon.com/us/pokemon-news/check-out-every-pokemon-tcg-product-release-in-october-2026
- https://www.pokemon.com/uk/news/check-out-every-pokemon-tcg-product-release-in-november-2026
- https://celadoninfo.com/us
