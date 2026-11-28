"""Prepare and archive review drafts from verified research artifacts."""

import json
import re
from datetime import timedelta

from scripts.editorial import timestamp

from .briefing import draft, markdown_link
from .verification import briefing_candidates

REPO_URL = "https://github.com/bamalroney-dev/Side-quest-dispatch"
ARCHIVE_TITLE = "Side Quest Dispatch Research Review"
RECEIPT_HEADING = "Archive receipt"
VERIFIED_FIELDS = {"release_date", "current_price", "claim_deadline"}


def run_number(value):
    if not re.fullmatch(r"[1-9][0-9]{0,19}", str(value)):
        raise ValueError("Use the GitHub Actions run ID from the run URL")
    return int(value)


def title_for(run_id):
    return f"{ARCHIVE_TITLE} {run_number(run_id)}"


def run_link(run_id):
    return f"{REPO_URL}/actions/runs/{run_number(run_id)}"


def active_values(finding, now):
    claims = finding.get("claims", {})
    fields = {key: claim["value"] for key, claim in claims.items()
              if key in VERIFIED_FIELDS and claim["status"] == "verified"}
    if ("current_price" not in fields or "claim_deadline" not in fields
            or timestamp(fields["claim_deadline"]) <= now):
        fields.pop("current_price", None)
        fields.pop("claim_deadline", None)
    return fields


def receipt_from_markdown(markdown, run_id):
    matches = re.findall(r"^#{1,4} Archive receipt\s*\n\s*```json\s*\n(.+?)\n```$",
                         markdown, re.MULTILINE | re.DOTALL)
    if len(matches) != 1:
        raise ValueError(f"Archive receipt is missing for run {run_id}")
    receipt = json.loads(matches[0])
    if (receipt.get("schema_version") != 1 or receipt.get("github_run_id") != run_id
            or not isinstance(receipt.get("included"), dict)):
        raise ValueError(f"Invalid archive receipt for run {run_id}")
    return receipt


def prepare(snapshot, report, verification, run_id, prior_receipts, now):
    run_id = run_number(run_id)
    candidates = briefing_candidates(snapshot, report)
    if (verification["run_id"], verification["collected_at"]) != (snapshot["run_id"], snapshot["collected_at"]):
        raise ValueError("Claim verification belongs to a different snapshot")
    covered = {}
    for receipt in sorted(prior_receipts, key=lambda item: item["github_run_id"]):
        if receipt["github_run_id"] >= run_id:
            raise ValueError("A review for this run or a newer run is already archived")
        for url, fields in receipt["included"].items():
            covered.setdefault(url, {}).update(fields)

    included = {}
    for articles in candidates.values():
        for article in articles:
            url = article["canonical_url"]
            fields = active_values(verification["articles"].get(url, {}), now)
            if url not in covered or any(covered[url].get(key) != value for key, value in fields.items()):
                included[url] = fields
    receipt = {
        "schema_version": 1, "github_run_id": run_id, "snapshot_run_id": snapshot["run_id"],
        "collected_at": snapshot["collected_at"], "included": included,
    }
    if not included:
        return receipt, ""
    rendered = draft(snapshot, report, verification, now=now, included_urls=included)
    _, _, body = rendered.partition("\n\n")
    # The first part is the Markdown title. Notion displays the page title separately.
    encoded = json.dumps(receipt, ensure_ascii=False, separators=(",", ":"))
    content = (
        f"Editorial review draft from {markdown_link('the GitHub Actions run', run_link(run_id))}.\n\n"
        f"{body.rstrip()}\n\n"
        f"## {RECEIPT_HEADING}\n\n```json\n{encoded}\n```\n"
    )
    return receipt, content


def archive(store, parent, snapshot, report, verification, run_id, now):
    run_id = run_number(run_id)
    pages = store.review_pages(parent)
    if run_id in pages:
        page = pages[run_id]
        receipt = receipt_from_markdown(store.markdown(page["id"]), run_id)
        if (receipt["snapshot_run_id"], receipt["collected_at"]) != (
            snapshot["run_id"], snapshot["collected_at"],
        ):
            raise ValueError("The archived review belongs to a different snapshot")
        return {"status": "existing", "id": page["id"], "receipt": receipt}
    receipts = [receipt_from_markdown(store.markdown(page["id"]), number)
                for number, page in pages.items()]
    receipt, content = prepare(snapshot, report, verification, run_id, receipts, now)
    if not content:
        return {"status": "no_changes", "id": None, "receipt": receipt}
    page = store.create_review(parent, title_for(run_id), content)
    if receipt_from_markdown(store.markdown(page["id"]), run_id) != receipt:
        raise ValueError("Notion did not return the expected archive receipt")
    return {"status": "created", "id": page["id"], "receipt": receipt}


def status_report(run_id, report, handoff, now, *, last_success_id=None, max_age_hours=48):
    run_id = run_number(run_id)
    current = report.get("snapshot_run_id") == report.get("run_id")
    older_than = now - timedelta(hours=max_age_hours)
    latest_success = max((number for number in (run_id if current else None, last_success_id)
                          if number is not None), default=None)
    return {
        "github_run_id": run_id,
        "latest_successful_run_id": latest_success,
        "collected_at": report["collected_at"],
        "checked_at": now.isoformat(),
        "snapshot_current": current,
        "archive_status": handoff["status"],
        "notion_page_id": handoff.get("id"),
        "sources": [{
            "source": source["source"],
            "status": source["status"],
            "last_success_at": source["last_success_at"],
            "latest_published_at": source["latest_published_at"],
            "new": source["new"],
            "previously_seen": source["previously_seen"],
            "stale_collection": not source["last_success_at"]
            or timestamp(source["last_success_at"]) < older_than,
            "stale_publication": bool(source["latest_published_at"])
            and timestamp(source["latest_published_at"]) < older_than,
        } for source in report["sources"]],
    }


def status_markdown(status, notion_url=None):
    checked = status["github_run_id"]
    successful = status["latest_successful_run_id"]
    links = [] if checked == successful else [markdown_link("Checked GitHub Actions run", run_link(checked))]
    if successful:
        links.append(markdown_link("Latest successful collection", run_link(successful)))
    if notion_url:
        links.append(markdown_link("Notion review draft", notion_url))
    labels = {"created": "Draft created", "existing": "Draft already in the archive",
              "no_changes": "No new or changed items to archive", "preview": "Awaiting Notion handoff",
              "failed": "Handoff needs attention"}
    lines = [
        f"Collection checked {status['checked_at']}. {labels[status['archive_status']]}.",
        "", " · ".join(links), "",
    ]
    for source in status["sources"]:
        flags = [source["status"]]
        if source["stale_collection"]:
            flags.append("collection stale")
        if source["stale_publication"]:
            flags.append("latest dated item is stale")
        lines.append(f"- **{source['source']}** · {', '.join(flags)} · "
                     f"{source['new']} new · {source['previously_seen']} previously collected")
    return "\n".join(lines) + "\n"
