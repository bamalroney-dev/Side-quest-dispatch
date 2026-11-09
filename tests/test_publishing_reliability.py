import contextlib
import datetime as dt
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import build_dispatch as dispatch
from publishing_diagnostics import classify_story, emit_outcome
from dispatch_summary import parse_result, render

class PublishingReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime.now(dt.timezone.utc)
        self.item = {"title": "Test update", "url": "https://example.org/new",
                     "published": self.now - dt.timedelta(minutes=10),
                     "description": "A fresh update.", "source": "Fixture"}

    def test_rejection_reasons(self):
        key = dispatch.story_key(self.item["url"])
        self.assertEqual(classify_story(self.item, self.now, {}, set(), dispatch.story_key), "eligible")
        self.assertEqual(classify_story(self.item, self.now, {key: "yesterday"}, set(), dispatch.story_key), "previously_published")
        self.assertEqual(classify_story(self.item, self.now, {}, {key}, dispatch.story_key), "duplicate_this_run")
        self.assertEqual(classify_story({**self.item, "published": self.now + dt.timedelta(minutes=1)}, self.now, {}, set(), dispatch.story_key), "future_dated")
        self.assertEqual(classify_story({**self.item, "published": self.now - dt.timedelta(hours=49)}, self.now, {}, set(), dispatch.story_key), "stale")

    def test_outcome_round_trip_and_summary(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            emit_outcome("no_fresh_stories", date="2026-11-09", report={})
        result = parse_result(out.getvalue())
        self.assertEqual(result["outcome"], "no_fresh_stories")
        self.assertIn("no_fresh_stories", render(result))

    def test_missing_outcome_is_error(self):
        with self.assertRaises(ValueError):
            parse_result("No new qualifying dispatch to publish.")

    def test_invalid_outcome_rejected(self):
        with self.assertRaises(ValueError):
            emit_outcome("success_without_post", date="2026-11-09")

    def test_dry_run_never_writes_post_or_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            posts = root / "_posts"
            index = root / "data" / "story-index.json"
            with (patch.object(dispatch, "POSTS", posts),
                  patch.object(dispatch, "INDEX", index),
                  patch.object(dispatch, "FEEDS", {"Disney Parks": [("Fixture", "https://example.org/feed")]}),
                  patch.object(dispatch, "RESEARCH_TARGETS", {}),
                  patch.object(dispatch, "read_feed", return_value=[self.item]),
                  patch.object(sys, "argv", ["build_dispatch.py", "--dry-run"])):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    dispatch.main()
            self.assertFalse(posts.exists())
            self.assertFalse(index.exists())
            self.assertEqual(parse_result(output.getvalue())["outcome"], "dry_run")

    def test_existing_edition_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            posts = pathlib.Path(tmp)
            today = dt.datetime.now(dt.timezone.utc).astimezone(dispatch.TZ).date().isoformat()
            post = posts / f"{today}-side-quest-dispatch.md"
            post.write_text("Original edition", encoding="utf-8")
            with patch.object(dispatch, "POSTS", posts), patch.object(sys, "argv", ["build_dispatch.py"]):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    dispatch.main()
            self.assertEqual(post.read_text(), "Original edition")
            self.assertEqual(parse_result(output.getvalue())["outcome"], "already_exists")

if __name__ == "__main__":
    unittest.main()
