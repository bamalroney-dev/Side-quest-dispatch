"""Generate a review-only briefing from the current collection snapshot."""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from scripts.editorial import timestamp

from .http import HttpClient
from .storage import write_json
from .verification import briefing_candidates, verify


def markdown_text(text):
    return re.sub(r"([\\`*_\[\]<>#!|~])", r"\\\1", text)


def markdown_link(title, url):
    return f"[{markdown_text(title)}](<{quote(url, safe=':/?&=%;+$,@!~*-._')}>)"


def claim_lines(finding, now):
    claims = finding.get("claims", {})
    release = claims.get("release_date", {})
    price = claims.get("current_price", {})
    deadline = claims.get("claim_deadline", {})
    lines = []
    if release.get("status") == "verified":
        lines.append(f"Publisher release date {release['value']}. "
                     + markdown_link("Official schedule", release["evidence_url"]))
    if (deadline.get("status") == "verified" and price.get("status") == "verified"
            and timestamp(deadline["value"]) > now):
        cents = price["value"]["amount_cents"]
        lines.append(f"U.S. store price USD {cents // 100}.{cents % 100:02d} until {deadline['value']}. "
                     + markdown_link("Official offer data", price["evidence_url"]))
    return lines


def draft(snapshot, report, verification=None, *, now=None):
    candidates = briefing_candidates(snapshot, report)
    run_id = snapshot["run_id"]
    findings = {}
    if verification:
        if (verification["run_id"], verification["collected_at"]) != (run_id, snapshot["collected_at"]):
            raise ValueError("Claim verification belongs to a different snapshot.")
        findings = verification["articles"]
    now = now or datetime.now(timezone.utc)
    lines = [
        "# Side Quest Dispatch research briefing draft", "",
        f"Collected at {snapshot['collected_at']} · Collection run {run_id}", "",
        "Review these source links and verified fields before publication. "
        "The original headlines and summaries are in latest.json.", "",
    ]
    if verification:
        lines.extend(["See claim-verification.json for fields still awaiting evidence.", ""])
    for source in report["sources"]:
        name = source["source"]
        lines.extend([f"## {name}", "",
                      f"Source health **{source['status']}** · {source['new']} new · "
                      f"{source['previously_seen']} previously seen", ""])
        articles = candidates[name]
        reported = set()
        for article in articles:
            url = article["canonical_url"]
            finding = findings.get(url, {})
            label = finding.get("subject") or "Open source"
            if label == "Open source" and article["published_at"]:
                label = f"Open source from {article['published_at'][:10]} UTC"
            lines.append("- " + markdown_link(label, url))
            for line in claim_lines(finding, now):
                key = (label, line)
                if key not in reported:
                    lines.append(f"  {line}")
                    reported.add(key)
        if not articles:
            lines.append("No candidates in this snapshot.")
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("research-data"))
    parser.add_argument("--output", type=Path, help="Write UTF-8 Markdown to this path")
    parser.add_argument("--verify", action="store_true", help="Check official evidence before drafting")
    args = parser.parse_args()
    snapshot = json.loads((args.data_dir / "latest.json").read_text(encoding="utf-8"))
    report = json.loads((args.data_dir / "source-health.json").read_text(encoding="utf-8"))
    try:
        findings = None
        if args.verify:
            findings = verify(snapshot, report, HttpClient(), datetime.now(timezone.utc))
            write_json(args.data_dir / "claim-verification.json", findings)
        briefing = draft(snapshot, report, findings)
    except ValueError as exc:
        parser.error(str(exc))
    if args.output:
        args.output.write_text(briefing, encoding="utf-8")
    else:
        print(briefing, end="")


if __name__ == "__main__":
    main()
