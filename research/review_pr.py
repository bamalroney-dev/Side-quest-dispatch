"""Build a selected-source Jekyll draft and open it for review."""

import json
import subprocess
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from .briefing import claim_lines, markdown_link
from .editorial_handoff import active_values, run_link, run_number
from .verification import briefing_candidates


def render_edition(snapshot, report, verification, receipt, run_id, selection, edition_date, now):
    run_id = run_number(run_id)
    edition = date.fromisoformat(edition_date)
    edition_date = edition.isoformat()
    as_of = max(now, datetime.combine(edition, time.min, ZoneInfo("America/Chicago")))
    if (receipt["github_run_id"], receipt["snapshot_run_id"], receipt["collected_at"]) != (
        run_id, snapshot["run_id"], snapshot["collected_at"],
    ):
        raise ValueError("The archive receipt belongs to a different research run")
    if (verification["run_id"], verification["collected_at"]) != (snapshot["run_id"], snapshot["collected_at"]):
        raise ValueError("Claim verification belongs to a different snapshot")
    selection = list(dict.fromkeys(selection))
    if not selection:
        raise ValueError("Select at least one URL from the archived briefing")
    articles = {article["canonical_url"]: article for group in briefing_candidates(snapshot, report).values()
                for article in group}
    if any(url not in receipt["included"] or url not in articles for url in selection):
        raise ValueError("Every selected URL must appear in the archived briefing")
    lines = [
        "---", "layout: post", f'title: "Side Quest Dispatch Research Roundup – {edition_date}"',
        f"date: {edition_date}", 'description: "Source-linked research from Side Quest Dispatch."',
        "tags: [research, news, gaming, disney]", "---", "",
    ]
    for url in selection:
        article = articles[url]
        finding = verification["articles"].get(url, {})
        fields = active_values(finding, as_of)
        if any(receipt["included"][url].get(key) != value for key, value in fields.items()):
            raise ValueError("Selected claims changed since archiving. Prepare a new reviewed briefing.")
        lines.append("## " + article["source"])
        lines.extend(["", markdown_link(finding.get("subject") or "Source article", url), ""])
        for line in claim_lines(finding, as_of):
            lines.extend([line, ""])
    return (
        f"review/research-{run_id}-{edition_date}",
        f"_posts/{edition_date}-side-quest-dispatch-research.md",
        "\n".join(lines),
    )


def command(*args, check=True):
    return subprocess.run(args, check=check, capture_output=True, encoding="utf-8")


def open_draft(branch, filename, content, run_id, repo, exec_command=command):
    """Push once, then create or find the draft for that exact review branch."""
    compare = f"https://github.com/{repo}/compare/main...{branch}?expand=1"
    remote = exec_command("git", "ls-remote", "--exit-code", "--heads", "origin", branch, check=False)
    if remote.returncode == 0:
        exec_command("git", "fetch", "origin", f"refs/heads/{branch}:refs/remotes/origin/{branch}")
        saved = exec_command("git", "show", f"origin/{branch}:{filename}")
        if saved.stdout != content:
            raise ValueError("Review branch already has different content. Edit its draft directly.")
    elif remote.returncode == 2:
        exec_command("git", "fetch", "origin", "main")
        exec_command("git", "switch", "--no-track", "--create", branch, "origin/main")
        with Path(filename).open("x", encoding="utf-8", newline="\n") as output:
            output.write(content)
        exec_command("git", "add", "--", filename)
        exec_command("git", "-c", "user.name=github-actions[bot]", "-c",
                     "user.email=41898282+github-actions[bot]@users.noreply.github.com",
                     "commit", "-m", f"Review research from collection {run_id}")
        exec_command("git", "push", "origin", f"HEAD:refs/heads/{branch}")
    else:
        remote.check_returncode()

    existing = exec_command("gh", "pr", "list", "--repo", repo, "--state", "all", "--base", "main",
                            "--head", branch, "--json", "url,state,isDraft")
    if pull_requests := json.loads(existing.stdout):
        return pull_requests[0]["url"]
    result = exec_command(
        "gh", "pr", "create", "--repo", repo, "--base", "main", "--head", branch, "--draft",
        "--title", f"Review Side Quest Dispatch research from run {run_id}",
        "--body", f"Editorial selections from [Research collection run {run_id}]({run_link(run_id)}). "
                   "Review the source links and proposed copy before approval.",
        check=False,
    )
    if result.returncode:
        raise ValueError(f"Draft PR creation failed. The review branch is available at {compare}")
    return result.stdout.strip()
