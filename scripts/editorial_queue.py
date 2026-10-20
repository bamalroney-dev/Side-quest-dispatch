"""Offline editorial candidate ranking and human-review packet builder.

No paid APIs, AI model calls, publication, or network access. Input must be
collected RSS metadata from a trusted collector, not arbitrary article text.
"""
import argparse
import datetime as dt
import json
import pathlib
from urllib.parse import urlsplit, parse_qsl, urlencode, urlunsplit
from editorial import validate_package

WEIGHTS = {"relevance": 30, "freshness": 25, "upcoming_impact": 20,
           "significance": 15, "source_reliability": 10}
PRIORITY = {"Pokémon Trading Card Game", "Pokémon Legends: Z-A Codes and Events",
            "Disney Parks", "Walt Disney World", "Disney Cruise Line",
            "Jenks and Tulsa Family Activities", "Oklahoma Concerts and Live Music",
            "RuneScape 3", "Old School RuneScape", "Disney Lorcana"}

def canonical_url(url):
    parts = urlsplit(url)
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query)
                           if not k.lower().startswith("utm_") and
                           k.lower() not in {"fbclid", "gclid"}))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(),
                       parts.path.rstrip("/") or "/", query, ""))

def score(story, now):
    published = dt.datetime.fromisoformat(story["published_at"].replace("Z", "+00:00"))
    hours = max(0, (now - published).total_seconds() / 3600)
    freshness = max(0.0, 1.0 - hours / 48)
    relevance = 1.0 if story["category"] in PRIORITY else 0.55
    # No unsupported inference about future impact or significance.
    # These two dimensions stay zero until a reviewer supplies evidence.
    return round(WEIGHTS["relevance"] * relevance +
                 WEIGHTS["freshness"] * freshness +
                 WEIGHTS["source_reliability"] * 0.5, 2)

def select(stories, now, max_stories=25, per_category=5):
    candidates = []
    seen = set()
    for story in stories:
        if validate_package({"stories": [story]}, now):
            continue
        key = canonical_url(story["url"])
        if key in seen:
            continue
        seen.add(key)
        candidate = dict(story)
        candidate["editorial_score"] = score(story, now)
        candidate["review_status"] = "pending"
        candidates.append(candidate)
    candidates.sort(key=lambda s: (-s["editorial_score"], s["category"], s["url"]))
    counts, result = {}, []
    for item in candidates:
        category = item["category"]
        if counts.get(category, 0) >= per_category:
            continue
        counts[category] = counts.get(category, 0) + 1
        result.append(item)
        if len(result) == max_stories:
            break
    return result

def review_packet(stories, now):
    selected = select(stories, now)
    return {"schema_version": 1, "status": "review_required",
            "generated_at": now.isoformat(), "automatic_publication": False,
            "ai_provider": None, "stories": selected,
            "editorial_notes": [
                "Rankings are heuristic and not an AI evaluation.",
                "Review every summary and factual claim against source evidence.",
                "Verify URLs, upcoming event dates, code validity, and image rights manually.",
                "Do not publish this packet automatically."
            ]}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(pathlib.Path("_posts").resolve()):
        parser.error("Refusing to write into _posts")
    package = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(package, dict) or not isinstance(package.get("stories"), list):
        parser.error("Expected a JSON object containing a stories array")
    packet = review_packet(package["stories"], dt.datetime.now(dt.timezone.utc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(packet['stories'])} review candidates to {args.output}; no publication.")

if __name__ == "__main__":
    main()
