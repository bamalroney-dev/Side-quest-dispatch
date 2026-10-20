"""Approval-first editorial validation. No API calls and no publishing."""
import argparse
import datetime as dt
import json
import pathlib
from urllib.parse import urlsplit

REQUIRED = ("title", "category", "url", "source", "published_at", "summary", "why_it_matters", "evidence_urls")

def timestamp(value):
    date = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("Timezone required")
    return date.astimezone(dt.timezone.utc)

def valid_https(value):
    if not isinstance(value, str):
        return False
    parts = urlsplit(value)
    return parts.scheme == "https" and bool(parts.netloc) and not parts.username and not parts.password

def validate_story(story, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if not isinstance(story, dict):
        return ["Story must be an object"]
    errors = []
    for field in REQUIRED:
        if not story.get(field):
            errors.append("Missing " + field)
    if not valid_https(story.get("url")):
        errors.append("Invalid source URL")
    try:
        age = now - timestamp(story["published_at"])
        if not dt.timedelta(0) <= age <= dt.timedelta(hours=48):
            errors.append("Article outside 48-hour window")
    except (KeyError, ValueError, AttributeError, TypeError):
        errors.append("Invalid published_at")
    evidence = story.get("evidence_urls")
    if not isinstance(evidence, list) or not evidence or not all(valid_https(u) for u in evidence):
        errors.append("Evidence must include HTTPS URLs")
    event = story.get("event")
    if event is not None:
        if not isinstance(event, dict) or not valid_https(event.get("official_url")):
            errors.append("Event requires official HTTPS URL")
        try:
            if timestamp(event["starts_at"]) < now:
                errors.append("Event is expired")
        except (KeyError, ValueError, AttributeError, TypeError):
            errors.append("Invalid event date")
    if story.get("image"):
        errors.append("Image rights review required")
    for field in ("summary", "why_it_matters"):
        if len(str(story.get(field, ""))) > 900:
            errors.append(field + " exceeds length limit")
    return errors

def validate_package(package, now=None):
    if not isinstance(package, dict) or not isinstance(package.get("stories"), list):
        return {"package": ["Expected stories array"]}
    errors, seen = {}, set()
    for i, story in enumerate(package["stories"]):
        issues = validate_story(story, now)
        url = story.get("url") if isinstance(story, dict) else None
        if url in seen:
            issues.append("Duplicate story URL")
        seen.add(url)
        if issues:
            errors[str(i)] = issues
    return errors

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=pathlib.Path)
    args = parser.parse_args()
    errors = validate_package(json.loads(args.input.read_text(encoding="utf-8")))
    print(json.dumps({"valid": not errors, "errors": errors}, indent=2))
    if errors:
        raise SystemExit(1)
    print("Draft passes structural checks only. Human factual review and approval still required.")
