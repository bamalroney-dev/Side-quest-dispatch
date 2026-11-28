import copy
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import Mock, patch

from research.editorial_handoff import archive, prepare, receipt_from_markdown, status_report, title_for
from research.review_pr import open_draft, render_edition
from test_verification import DEADLINE, GAME_URL, NOW, SCHEDULE, TCG_URL, FixtureClient, inputs, storefront
from research.verification import verify


class MemoryArchive:
    def __init__(self):
        self.pages = {}
        self.original = {}

    def review_pages(self, parent):
        return self.pages

    def markdown(self, page_id):
        return self.original[page_id]

    def create_review(self, parent, title, content):
        run_id = int(title.rsplit(" ", 1)[1])
        page = {"id": f"page-{run_id}"}
        self.pages[run_id] = page
        self.original[page["id"]] = content
        return page


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.snapshot, self.health = inputs()
        self.findings = verify(self.snapshot, self.health, FixtureClient(SCHEDULE, storefront()), NOW)
        self.repo_run_id = 46142444937

    def prepare(self, previous=()):
        return prepare(self.snapshot, self.health, self.findings,
                       self.repo_run_id, previous, NOW)

    def archive(self, store, run_id=None):
        return archive(store, "archive", self.snapshot, self.health, self.findings,
                       run_id or self.repo_run_id, NOW)

    def test_same_run_retry_finds_the_original_draft(self):
        store = MemoryArchive()
        first = self.archive(store)
        self.assertEqual(first["status"], "created")
        second = self.archive(store)
        self.assertEqual(second["status"], "existing")
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(store.pages), 1)
        self.assertIn("Publisher release date 2027-02-06", store.markdown(first["id"]))
        self.assertEqual(receipt_from_markdown(store.markdown(first["id"]) + "\nNotes\n",
                                               self.repo_run_id), first["receipt"])

    def test_ambiguous_create_is_safe_to_retry(self):
        store = MemoryArchive()
        real_create = store.create_review

        def committed_before_timeout(*args):
            real_create(*args)
            raise ValueError("Notion request did not complete")

        with patch.object(store, "create_review", side_effect=committed_before_timeout):
            with self.assertRaisesRegex(ValueError, "did not complete"):
                self.archive(store)
        self.assertEqual(self.archive(store)["status"], "existing")
        self.assertEqual(len(store.pages), 1)

    def test_coverage_ignores_collectors_seen_flag_and_holds_missing_evidence(self):
        store = MemoryArchive()
        self.snapshot["previously_seen_urls"] = [TCG_URL, GAME_URL]
        first = self.archive(store)
        self.assertIn(TCG_URL, first["receipt"]["included"])
        self.findings["articles"][TCG_URL]["claims"]["release_date"] = {"status": "unavailable"}
        retry = self.archive(store, self.repo_run_id + 1)
        self.assertEqual(retry["status"], "no_changes")
        self.assertEqual(len(store.pages), 1)
        self.findings["articles"][TCG_URL]["claims"]["release_date"].update(
            status="verified", value="2027-02-07", evidence_url="https://press.pokemon.com/en/",
        )
        changed = self.archive(store, self.repo_run_id + 2)
        self.assertEqual(changed["status"], "created")
        self.assertEqual(changed["receipt"]["included"], {TCG_URL: {"release_date": "2027-02-07"}})

    def test_only_archived_selections_get_into_the_edition(self):
        receipt, _ = self.prepare()
        result = render_edition(self.snapshot, self.health, self.findings, receipt, self.repo_run_id,
                                [GAME_URL, GAME_URL], "2026-11-28", NOW)
        self.assertTrue(result[0].startswith("review/research-"))
        self.assertEqual(result[1], "_posts/2026-11-28-side-quest-dispatch-research.md")
        self.assertEqual(result[2].count(GAME_URL), 1)
        self.assertIn(DEADLINE, result[2])
        self.assertNotIn(TCG_URL, result[2])
        self.assertNotIn("$99.99", result[2])
        expired = render_edition(self.snapshot, self.health, self.findings, receipt, self.repo_run_id,
                                 [GAME_URL], "2026-12-03", datetime.fromisoformat(DEADLINE))
        self.assertNotIn(DEADLINE, expired[2])
        future = render_edition(self.snapshot, self.health, self.findings, receipt, self.repo_run_id,
                                [GAME_URL], "2026-12-04", NOW)
        self.assertNotIn(DEADLINE, future[2])
        with self.assertRaisesRegex(ValueError, "archived briefing"):
            render_edition(self.snapshot, self.health, self.findings, receipt, self.repo_run_id,
                           ["https://example.com/unknown"], "2026-11-28", NOW)

    def test_command_center_reports_failed_and_stale_sources(self):
        health = copy.deepcopy(self.health)
        health.update(collected_at=NOW.isoformat(), snapshot_run_id=2)
        old = (NOW - timedelta(days=3)).isoformat()
        for source in health["sources"]:
            source.update(status="failed", last_success_at=old, latest_published_at=None)
        result = status_report(self.repo_run_id, health, {"status": "failed"}, NOW, last_success_id=42)
        self.assertEqual(result["latest_successful_run_id"], 42)
        self.assertFalse(result["snapshot_current"])
        self.assertTrue(result["sources"][0]["stale_collection"])
        self.assertFalse(result["sources"][0]["stale_publication"])

    def test_archived_page_title_uses_github_run_id(self):
        self.assertTrue(title_for(self.repo_run_id).endswith(str(self.repo_run_id)))
        with self.assertRaises(ValueError):
            title_for("46/1")


class DraftPRTests(unittest.TestCase):
    def test_existing_branch_reuses_existing_pr_without_pushing(self):
        def fake(*args, **kwargs):
            output = "revision" if args[1] == "ls-remote" else "draft\n" if args[1] == "show" else ""
            if args[:3] == ("gh", "pr", "list"):
                output = '[{"url":"https://github.com/owner/repo/pull/1","state":"OPEN","isDraft":true}]'
            return CompletedProcess(args, 0, output, "")

        command = Mock(side_effect=fake)
        self.assertTrue(open_draft("review/research-10", "_posts/draft.md", "draft\n", 10,
                                   "owner/repo", command).endswith("/pull/1"))
        self.assertFalse(any("push" in call.args or "create" in call.args for call in command.call_args_list))

    def test_new_branch_pushes_only_review_ref_and_requests_draft(self):
        def fake(*args, **kwargs):
            if args[:3] == ("gh", "pr", "list"):
                return CompletedProcess(args, 0, "[]", "")
            if args[:3] == ("gh", "pr", "create"):
                return CompletedProcess(args, 0, "https://github.com/owner/repo/pull/2\n", "")
            return CompletedProcess(args, 2 if args[1] == "ls-remote" else 0, "", "")

        command = Mock(side_effect=fake)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "draft.md"
            self.assertTrue(open_draft("review/research-10", str(path), "draft\n", 10,
                                       "owner/repo", command).endswith("/pull/2"))
            self.assertEqual(path.read_text(), "draft\n")
        self.assertTrue(any(call.args == ("git", "push", "origin", "HEAD:refs/heads/review/research-10")
                            for call in command.call_args_list))
        self.assertIn("--draft", command.call_args.args)
