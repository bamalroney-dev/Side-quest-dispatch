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
      git switch --no-track --create "$branch" "origin/$branch"
      echo "Resuming existing review branch (history and queue preserved)"
    else
      git switch --create "$branch"
      echo "Created new review branch from main"
    fi
    ;;
  publish)
    if ! merge_base="$(git merge-base origin/main HEAD)"; then
      echo "Cannot compare the review branch with origin/main. Verify the checkout has full history and the branches share a common ancestor." >&2
      exit 1
    fi
    if ! git diff --quiet -- "$queue"; then
      git add -- "$queue"
      git commit -m "Review newly discovered Pokémon TCG announcements"
      # Never force push. If remote moved, fail safely for a later retry.
      git push origin "HEAD:refs/heads/$branch"
    fi
    # With no candidate changes, avoid opening an empty PR.
    if git diff --quiet "$merge_base" HEAD -- "$queue"; then
      echo "No candidate changes to review"
      exit 0
    else
      diff_status=$?
      if [[ "$diff_status" != 1 ]]; then
        exit "$diff_status"
      fi
    fi
    # A failed GitHub CLI query must fail the job, not be mistaken for no PR.
    existing="$(gh pr list --state open --head "$branch" --base main --json number --jq '.[0].number // empty')"
    if [[ -n "$existing" ]]; then
      echo "Review PR #$existing already exists"
      exit 0
    fi

    if result="$(gh pr create --base main --head "$branch" \
      --title "Review Pokémon TCG announcement candidates" \
      --body "Official-source discovery only. Verify product identity, release date, and manufacturer MSRP before transferring entries to the published tracker. Do not auto-merge." \
      --draft 2>&1)"; then
      printf '%s\n' "$result"
    else
      pr_status=$?
      if [[ "$result" != *"GitHub Actions is not permitted to create or approve pull requests"* ]]; then
        printf '%s\n' "$result" >&2
        exit "$pr_status"
      fi

      compare_url="${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:?}/compare/main...${branch}?expand=1"
      echo "::warning::The review queue is available on $branch. GitHub blocked automatic PR creation. Open a review PR manually at $compare_url"
      if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
        printf 'GitHub blocked automatic PR creation. [Open a review PR manually](%s).\n' "$compare_url" >> "$GITHUB_STEP_SUMMARY"
      fi
    fi
    ;;
  *) echo "Usage: $0 prepare|publish" >&2; exit 2 ;;
esac
