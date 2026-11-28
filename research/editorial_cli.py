"""Run the manual editorial handoff or prepare a selected review PR."""

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .editorial_handoff import (
    archive, prepare, receipt_from_markdown, run_number, status_markdown, status_report, title_for,
)
from .notion_archive import NotionArchive
from .review_pr import command, open_draft, render_edition
from .storage import write_json


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def notion():
    parent = os.environ.get("NOTION_BRIEFING_PARENT_ID")
    if not parent:
        raise ValueError("Set NOTION_BRIEFING_PARENT_ID to the archive's page ID")
    return NotionArchive(os.environ.get("NOTION_TOKEN")), parent


def check_provenance(repo, run_id):
    source = json.loads(command("gh", "api", f"repos/{repo}/actions/runs/{run_id}").stdout)
    if (
        source["path"] != ".github/workflows/research-collection.yml"
        or source["head_branch"] != "main"
        or source["event"] not in {"workflow_dispatch", "schedule"}
        or source["status"] != "completed"
    ):
        raise ValueError("Use a completed Research collection run on main")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("archive", "preview", "review"))
    parser.add_argument("--run-id", type=run_number, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--receipts", type=Path, help="Prior receipt JSON array for an offline preview")
    parser.add_argument("--receipt", type=Path, help="Archived receipt JSON for an offline review preview")
    parser.add_argument("--last-success-run-id", type=run_number)
    parser.add_argument("--edition-date")
    parser.add_argument("--select-url", action="append", default=[])
    parser.add_argument("--open-pr", action="store_true")
    parser.add_argument("--check-run-provenance", action="store_true")
    args = parser.parse_args()
    if args.open_pr and (args.operation != "review" or args.receipt):
        parser.error("Opening a draft PR requires a receipt read directly from Notion")
    if args.operation == "review" and not args.edition_date:
        parser.error("Review requires --edition-date")
    return parser, args


def run_review(args, snapshot, report, verification, now):
    if args.receipt:
        receipt = read_json(args.receipt)
    else:
        store, parent = notion()
        page = store.review_pages(parent).get(args.run_id)
        if not page:
            raise ValueError("No Notion review draft exists for this GitHub run")
        receipt = receipt_from_markdown(store.markdown(page["id"]), args.run_id)
    branch, filename, content = render_edition(
        snapshot, report, verification, receipt, args.run_id,
        args.select_url or os.environ.get("RESEARCH_SELECTED_URLS", "").split(), args.edition_date, now,
    )
    (args.output_dir / "edition-preview.md").write_text(content, encoding="utf-8")
    if args.open_pr:
        repo = os.environ.get("GITHUB_REPOSITORY", "bamalroney-dev/Side-quest-dispatch")
        url = open_draft(branch, filename, content, args.run_id, repo)
        print(url)


def main():
    parser, args = parse_args()
    now = datetime.now(timezone.utc)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        if args.check_run_provenance:
            check_provenance(os.environ.get("GITHUB_REPOSITORY", "bamalroney-dev/Side-quest-dispatch"),
                             args.run_id)
        report = read_json(args.data_dir / "source-health.json")
        handoff = {"status": "failed"}
        try:
            snapshot = read_json(args.data_dir / "latest.json")
            verification = read_json(args.data_dir / "claim-verification.json")
            if args.operation == "review":
                run_review(args, snapshot, report, verification, now)
                return
            if args.operation == "archive":
                store, parent = notion()
                handoff = archive(store, parent, snapshot, report, verification, args.run_id, now)
            else:
                receipts = read_json(args.receipts) if args.receipts else []
                receipt, content = prepare(snapshot, report, verification, args.run_id, receipts, now)
                handoff = {"status": "preview" if content else "no_changes", "receipt": receipt}
                if content:
                    (args.output_dir / "notion-review.md").write_text(content, encoding="utf-8")
                    print(title_for(args.run_id))
            write_json(args.output_dir / "archive-receipt.json", handoff["receipt"])
            print(f"Editorial handoff {handoff['status']}")
        finally:
            if args.operation != "review":
                status = status_report(args.run_id, report, handoff, now,
                                       last_success_id=args.last_success_run_id)
                # Workflow output is readable by repository users. Keep private Notion IDs out of uploads.
                status.pop("notion_page_id", None)
                write_json(args.output_dir / "command-center.json", status)
                (args.output_dir / "command-center.md").write_text(
                    status_markdown(status), encoding="utf-8",
                )
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Editorial handoff failed. {exc}\n")


if __name__ == "__main__":
    main()
