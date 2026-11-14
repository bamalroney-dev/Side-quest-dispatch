"""Convert structured generator output into a readable GitHub Actions summary."""
import json
import os
import pathlib
import sys

def parse_result(log):
    for line in reversed(log.splitlines()):
        if line.startswith("DISPATCH_RESULT "):
            return json.loads(line.partition(" ")[2])
    raise ValueError("Missing DISPATCH_RESULT; generation may have stopped unexpectedly")

def render(result):
    lines = ["## Side Quest Dispatch publishing report", "",
             f"- **Generator outcome:** `{result['outcome']}`",
             f"- **Edition date:** {result['date']}",
             f"- **Selected stories:** {result['selected']}"]
    if result.get("post"):
        lines.append(f"- **Post:** `{result['post']}`")
    lines.extend(["", "| Category | Retrieved | Selected | Feed errors | Rejected |",
                  "|---|---:|---:|---:|---:|"])
    for name, stats in sorted(result.get("categories", {}).items()):
        rejected = sum(stats.get("rejected", {}).values())
        lines.append(f"| {name.replace('|', '/')} | {stats['retrieved']} | {stats['selected']} | {len(stats['errors'])} | {rejected} |")
    lines += ["", "**Note:** A generated post is not proof of a successful git push or Pages deployment. Check subsequent steps and Pages workflow."]
    return "\n".join(lines) + "\n"

def main():
    log = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
    summary = render(parse_result(log))
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as output:
            output.write(summary)
    print(summary)

if __name__ == "__main__":
    main()
