import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from jsonschema import ValidationError

from research import __main__, disney_food_blog
from research.http import FetchError, Response
from research.models import Draft202012Validator, SCHEMA, validate_article
from research.storage import record_run

FIXTURES = Path(__file__).with_name("fixtures")
NOW = "2026-11-26T15:00:00+00:00"


def fixture(name):
    return (FIXTURES / name).read_bytes()


class FixtureClient:
    def __init__(self, *results):
        self.results = iter(results)
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        result = next(self.results)
        if isinstance(result, FetchError):
            raise result
        return Response(result, url, 1)


class CollectionTests(unittest.TestCase):
    def test_feedburner_prefers_original_link_and_normalizes_metadata(self):
        client = FixtureClient(fixture("feedburner.xml"))
        records, health = disney_food_blog.collect(client)
        self.assertEqual(client.urls, [disney_food_blog.ENDPOINTS[0][1]])
        self.assertEqual(health["method"], "feedburner")
        self.assertEqual(health["checks"][0]["skipped"], 1)
        self.assertEqual(records[0]["title"], "Festival Snacks & Drinks")
        self.assertEqual(records[0]["summary"], "What’s new at the festival.")
        self.assertEqual(records[0]["published_at"], "2026-11-25T15:15:00+00:00")
        self.assertEqual(records[0]["canonical_url"], records[1]["canonical_url"])
        self.assertEqual(records[0]["canonical_url"],
                         "https://www.disneyfoodblog.com/2026/11/25/festival-snacks")

    def test_invalid_xml_falls_back_to_original_feed(self):
        client = FixtureClient(b"<rss><unclosed>", fixture("original.xml"))
        records, health = disney_food_blog.collect(client)
        self.assertEqual(health["status"], "degraded")
        self.assertEqual(health["method"], "original_rss")
        self.assertEqual(health["checks"][0]["stage"], "parse")
        self.assertEqual(len(records), 2)
        self.assertTrue(records[1]["canonical_url"].endswith("/holiday-menus"))
        self.assertIsNone(records[1]["published_at"])

    def test_fetch_error_and_empty_feed_fall_back_to_website(self):
        client = FixtureClient(FetchError("HTTP 503", 3, 503), b'<rss version="2.0"><channel/></rss>',
                               fixture("latest.html"))
        records, health = disney_food_blog.collect(client)
        self.assertEqual(client.urls, [url for _, url in disney_food_blog.ENDPOINTS])
        self.assertEqual(health["method"], "website")
        self.assertEqual(health["checks"][0]["http_status"], 503)
        self.assertEqual(health["checks"][0]["attempts"], 3)
        self.assertEqual([record["title"] for record in records], ["Festival Snacks", "Holiday Menus"])
        self.assertIsNone(records[0]["published_at"])

    def test_schema_rejects_missing_title_insecure_url_and_naive_timestamp(self):
        Draft202012Validator.check_schema(SCHEMA)
        records, _ = disney_food_blog.collect(FixtureClient(fixture("original.xml")))
        for invalid in (
            {"title": ""}, {"canonical_url": "http://www.disneyfoodblog.com/"},
            {"published_at": "2026-11-26T12:00:00"}, {"unexpected": True},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                validate_article({**records[0], **invalid})


class StorageTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)

    def read(self, name):
        return json.loads((self.directory / name).read_text(encoding="utf-8"))

    def test_history_deduplicates_within_runs_and_across_endpoints(self):
        first, primary = disney_food_blog.collect(FixtureClient(fixture("feedburner.xml")))
        record_run(self.directory, NOW, first, primary)
        report = self.read("source-health.json")["sources"][0]
        self.assertEqual((report["records"], report["new"], report["duplicates_in_run"]), (1, 1, 1))
        backup, health = disney_food_blog.collect(
            FixtureClient(FetchError("timed out", 3), fixture("original.xml")),
        )
        record_run(self.directory, NOW, backup, health)
        snapshot = self.read("latest.json")
        self.assertEqual(snapshot["previously_seen_urls"], [first[0]["canonical_url"]])
        report = self.read("source-health.json")["sources"][0]
        self.assertEqual((report["records"], report["new"], report["previously_seen"]), (2, 1, 1))
        self.assertEqual(report["retries"], 2)
        with closing(sqlite3.connect(self.directory / "history.sqlite3")) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM articles").fetchone(), (2,))
            self.assertEqual(db.execute(
                "SELECT first_run_id, last_run_id FROM articles WHERE canonical_url = ?",
                (first[0]["canonical_url"],),
            ).fetchone(), (1, 2))

    def test_total_failure_preserves_latest_success_and_returns_nonzero(self):
        first = disney_food_blog.collect(FixtureClient(fixture("original.xml")))
        record_run(self.directory, NOW, *first)
        success = self.read("latest.json")
        failure = FixtureClient(FetchError("forbidden", 1, 403), b"<html></html>", b"<html></html>")
        with patch.object(__main__, "HttpClient", return_value=failure), patch.object(
            sys, "argv", ["research", "--output-dir", str(self.directory)],
        ):
            self.assertEqual(__main__.main(), 1)
        self.assertEqual(self.read("latest.json"), success)
        report = self.read("source-health.json")
        self.assertEqual(report["run_id"], 2)
        self.assertEqual(report["snapshot_run_id"], 1)
        self.assertEqual(report["sources"][0]["status"], "failed")

    def test_first_run_failure_writes_empty_snapshot_and_report(self):
        failure = disney_food_blog.collect(FixtureClient(*[FetchError("offline", 3)] * 3))
        record_run(self.directory, NOW, *failure)
        self.assertEqual(self.read("latest.json")["articles"], [])
        self.assertIsNone(self.read("source-health.json")["snapshot_run_id"])
