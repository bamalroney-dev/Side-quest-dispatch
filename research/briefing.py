"""Generate a review-only briefing from the current collection snapshot."""

import argparse
import json
import re
from pathlib import Path
from urllib.parse import quote

from .models import validate_article


def markdown_text(text):
    return re.sub(r"([\\`*_\[\]<>#!|~])", r"\\\1", text)


def draft(snapshot, report):
    run_id = snapshot["run_id"]
    if run_id is None or run_id != report["run_id"] or run_id != report["snapshot_run_id"]:
        raise ValueError("Latest attempt has no current snapshot. Check source-health.json.")

    articles_by_source = {}
    for article in snapshot["articles"]:
        validate_article(article)
        articles_by_source.setdefault(article["source"], []).append(article)

    seen = set(snapshot["previously_seen_urls"])
    lines = [
        "# Side Quest Dispatch research briefing draft", "",
        f"Collected at {snapshot['collected_at']} · Collection run {run_id}", "",
        "Review source links and confirm any release dates, prices, or claim terms before publication.", "",
    ]
    for source in report["sources"]:
        name = source["source"]
        lines.extend([f"## {name}", "",
                      f"Source health **{source['status']}** · {source['new']} new · "
                      f"{source['previously_seen']} previously seen", ""])
        articles = sorted(
            articles_by_source.get(name, ()),
            key=lambda article: (article["canonical_url"] not in seen, article["published_at"] or ""),
            reverse=True,
        )
        for article in articles[:3]:
            url = quote(article["canonical_url"], safe=":/?&=%;+$,@!~*-._")
            title = markdown_text(article["title"])
            review = " · needs verification" if article.get("review_status") else ""
            lines.append(f"- [{title}](<{url}>){review}")
            if article["summary"]:
                lines.append(f"  {markdown_text(article['summary'])}")
            if window := article.get("offer_window"):
                lines.append(f"  {window['market']} store window ends {window['ends_at']}.")
        if not articles:
            lines.append("No candidates in this snapshot.")
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("research-data"))
    parser.add_argument("--output", type=Path, help="Write UTF-8 Markdown to this path")
    args = parser.parse_args()
    snapshot = json.loads((args.data_dir / "latest.json").read_text(encoding="utf-8"))
    report = json.loads((args.data_dir / "source-health.json").read_text(encoding="utf-8"))
    try:
        briefing = draft(snapshot, report)
    except ValueError as exc:
        parser.error(str(exc))
    if args.output:
        args.output.write_text(briefing, encoding="utf-8")
    else:
        print(briefing, end="")


if __name__ == "__main__":
    main()
