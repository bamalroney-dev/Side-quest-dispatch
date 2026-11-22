"""Local Git regression tests for the review-only Pokémon discovery workflow."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/pokemon_tcg_review_pr.sh"
QUEUE = "data/pokemon-tcg-review-queue.json"


class ReviewWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.remote = self.base / "remote.git"
        self.seed = self.base / "seed"
        self.work = self.base / "work"
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.git("init", "--bare", str(self.remote), cwd=self.base)
        self.git("init", "-b", "main", str(self.seed), cwd=self.base)
        self.git("config", "user.name", "Test", cwd=self.seed)
        self.git("config", "user.email", "test@example.com", cwd=self.seed)
        (self.seed / "data").mkdir()
        (self.seed / QUEUE).write_text('{"schema_version":1,"candidates":[]}\n')
        self.git("add", ".", cwd=self.seed)
        self.git("commit", "-m", "main", cwd=self.seed)
        self.git("remote", "add", "origin", str(self.remote), cwd=self.seed)
        self.git("push", "-u", "origin", "main", cwd=self.seed)
        self.git("symbolic-ref", "HEAD", "refs/heads/main", cwd=self.remote)
        self.git("clone", "--branch", "main", str(self.remote), str(self.work), cwd=self.base)
        (self.bin / "gh").write_text(
            '#!/usr/bin/env bash\n'
            'if [[ "${GH_FAIL:-}" == "1" ]]; then exit 7; fi\n'
            'if [[ "${GH_EXISTING:-}" == "1" && "$1" == "pr" && "$2" == "list" ]]; then echo 12; fi\n'
            'if [[ "$1" == "pr" && "$2" == "create" ]]; then echo created >> "$GH_LOG"; fi\n'
        )
        (self.bin / "gh").chmod(0o755)
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", GH_LOG=str(self.base / "gh.log"))

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.work, text=True, capture_output=True, check=True).stdout

    def run_script(self, action, success=True):
        p = subprocess.run(["bash", str(SCRIPT), action], cwd=self.work, env=self.env, text=True, capture_output=True)
        if success and p.returncode != 0:
            self.fail(f"{action} failed: {p.stderr} {p.stdout}")
        return p

    def populate_queue(self, value):
        import json
        (self.work / QUEUE).write_text(json.dumps({
            "schema_version": 1,
            "candidates": [{"source_url": value, "review_status": "needs_verification"}]
        }) + "\n")

    def test_new_branch_created_without_force_push(self):
        self.run_script("prepare")
        self.populate_queue("https://www.pokemon.com/one")
        self.run_script("publish")
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "HEAD").strip(), "automation/pokemon-tcg-candidates")
        self.assertIn("one", (self.work / QUEUE).read_text())
        self.assertIn("created", (self.base / "gh.log").read_text())

    def test_existing_branch_history_and_queue_are_preserved(self):
        self.run_script("prepare")
        self.populate_queue("https://www.pokemon.com/one")
        self.run_script("publish")
        prior = self.git("rev-parse", "HEAD").strip()
        self.git("switch", "main")
        self.git("branch", "-D", "automation/pokemon-tcg-candidates")
        self.env["GH_EXISTING"] = "1"
        self.run_script("prepare")
        self.assertIn("one", (self.work / QUEUE).read_text())
        self.populate_queue("https://www.pokemon.com/two")
        self.run_script("publish")
        self.assertEqual(self.git("merge-base", "--is-ancestor", prior, "HEAD"), "")
        self.assertIn("two", (self.work / QUEUE).read_text())
        self.assertEqual((self.base / "gh.log").read_text().count("created"), 1)

    def test_gh_query_failure_propagates(self):
        self.run_script("prepare")
        self.populate_queue("https://www.pokemon.com/one")
        self.env["GH_FAIL"] = "1"
        self.assertNotEqual(self.run_script("publish", success=False).returncode, 0)

    def test_no_changes_creates_no_empty_pr(self):
        self.run_script("prepare")
        self.run_script("publish")
        self.assertFalse((self.base / "gh.log").exists())

    def test_remote_moves_rejects_non_fast_forward(self):
        self.run_script("prepare")
        self.populate_queue("https://www.pokemon.com/one")
        self.run_script("publish")
        self.git("switch", "main")
        self.git("branch", "-D", "automation/pokemon-tcg-candidates")
        self.run_script("prepare")
        self.populate_queue("https://www.pokemon.com/two")
        self.git("clone", str(self.remote), str(self.base / "other"), cwd=self.base)
        other = self.base / "other"
        self.git("switch", "automation/pokemon-tcg-candidates", cwd=other)
        self.git("config", "user.name", "Other", cwd=other)
        self.git("config", "user.email", "other@example.com", cwd=other)
        (other / "note").write_text("updated")
        self.git("add", ".", cwd=other)
        self.git("commit", "-m", "concurrent update", cwd=other)
        self.git("push", "origin", "HEAD", cwd=other)
        self.assertNotEqual(self.run_script("publish", success=False).returncode, 0)


if __name__ == "__main__":
    unittest.main()
