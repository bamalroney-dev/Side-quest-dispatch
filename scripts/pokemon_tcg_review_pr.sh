#!/usr/bin/env bash
# Preserve the review branch's history and queue; never force-push or merge.
set -euo pipefail
branch="automation/pokemon-tcg-candidates"
queue="data/pokemon-tcg-review-queue.json"

case "${1:-}" in
  prepare)
    git config user.name "github-actions[bot]"
    git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
    if git ls-remote --exit-code --heads origin "$branch" >/dev/null; then
      git fetch origin "refs/heads/$branch:refs/remotes/origin/$branch"
      git switch --create "$branch" --track "origin/$branch"
      echo "Resuming existing review branch (history and queue preserved)"
    else
      git switch --create "$branch"
      echo "Created new review branch from main"
    fi
    ;;
  publish)
    if ! git diff --quiet -- "$queue"; then
      git add -- "$queue"
      git commit -m "Review newly discovered Pokémon TCG announcements"
      # Never force push. If remote moved, fail safely for a later retry.
      git push origin "HEAD:refs/heads/$branch"
    fi
    # With no candidate changes, avoid opening an empty PR.
    if git diff --quiet origin/main...HEAD -- "$queue"; then
      echo "No candidate changes to review"
      exit 0
    fi
    # A failed GitHub CLI query must fail the job, not be mistaken for no PR.
    existing="$(gh pr list --state open --head "$branch" --base main --json number --jq '.[0].number // empty')"
    if [[ -n "$existing" ]]; then
      echo "Review PR #$existing already exists"
    else
      gh pr create --base main --head "$branch" \
        --title "Review Pokémon TCG announcement candidates" \
        --body "Official-source discovery only. Verify product identity, release date, and manufacturer MSRP before transferring entries to the published tracker. Do not auto-merge." \
        --draft
    fi
    ;;
  *) echo "Usage: $0 prepare|publish" >&2; exit 2 ;;
esac
