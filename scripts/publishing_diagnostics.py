"""Structured, non-sensitive diagnostics for the daily dispatch."""
import json

OUTCOMES = {"generated", "already_exists", "no_fresh_stories", "early_dst_skip", "dry_run"}

def emit_outcome(outcome, *, date, selected=0, report=None, post=None):
    if outcome not in OUTCOMES:
        raise ValueError(f"Unknown publishing outcome: {outcome}")
    payload = {"schema_version": 1, "outcome": outcome, "date": date,
               "selected": selected, "categories": report or {}}
    if post:
        payload["post"] = post
    print("DISPATCH_RESULT " + json.dumps(payload, sort_keys=True))
    return payload

def classify_story(item, now, seen, run_keys, story_key):
    age = now - item["published"]
    if age.total_seconds() < 0:
        return "future_dated"
    if age.total_seconds() > 48 * 3600:
        return "stale"
    key = story_key(item["url"])
    if key in seen:
        return "previously_published"
    if key in run_keys:
        return "duplicate_this_run"
    return "eligible"
