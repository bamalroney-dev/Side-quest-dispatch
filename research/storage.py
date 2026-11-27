"""Transactional collection history and atomically replaced JSON exports."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import NamedTemporaryFile

from .models import validate_article

SCHEMA_VERSION = 1
DDL = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    snapshot TEXT,
    health TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS articles (
    canonical_url TEXT PRIMARY KEY,
    record TEXT NOT NULL,
    first_run_id INTEGER NOT NULL REFERENCES runs(id),
    last_run_id INTEGER NOT NULL REFERENCES runs(id)
);
"""


def write_json(path, document):
    temporary_path = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(document, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def record_run(directory, collected_at, batches):
    for records, _ in batches:
        for record in records:
            validate_article(record)
    directory.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(directory / "history.sqlite3", timeout=30)) as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript(DDL)
        with db:
            db.execute("BEGIN IMMEDIATE")
            prior_report = db.execute("SELECT health FROM runs ORDER BY id DESC LIMIT 1").fetchone()
            last_successes = {
                source["source"]: source["last_success_at"]
                for source in json.loads(prior_report[0])["sources"]
            } if prior_report else {}
            run_id = db.execute("INSERT INTO runs (health) VALUES ('{}')").lastrowid
            unique = {}
            previously_seen_urls = []
            sources = []
            for records, source_health in batches:
                new, repeated, dates = 0, 0, []
                for record in records:
                    url = record["canonical_url"]
                    if url in unique:
                        continue
                    unique[url] = record
                    if record["published_at"]:
                        dates.append(record["published_at"])
                    inserted = db.execute("""
                        INSERT INTO articles (canonical_url, record, first_run_id, last_run_id)
                        VALUES (?, ?, ?, ?) ON CONFLICT(canonical_url) DO NOTHING
                    """, (url, json.dumps(record), run_id, run_id))
                    if inserted.rowcount:
                        new += 1
                    else:
                        repeated += 1
                        previously_seen_urls.append(url)
                        db.execute("UPDATE articles SET record = ?, last_run_id = ? WHERE canonical_url = ?",
                                   (json.dumps(record), run_id, url))
                sources.append({
                    **source_health,
                    "records": new + repeated, "new": new, "previously_seen": repeated,
                    "duplicates_in_run": len(records) - new - repeated,
                    "latest_published_at": max(dates, default=None),
                    "last_success_at": (
                        last_successes.get(source_health["source"])
                        if source_health["status"] == "failed" else collected_at
                    ),
                    "retries": sum(max(0, check["attempts"] - 1) for check in source_health["checks"]),
                })
            usable = bool(unique) or all(source["status"] != "failed" for source in sources)
            snapshot = {
                "schema_version": SCHEMA_VERSION, "run_id": run_id,
                "collected_at": collected_at, "articles": list(unique.values()),
                "previously_seen_urls": previously_seen_urls,
            } if usable else None
            previous_success = db.execute(
                "SELECT id FROM runs WHERE snapshot IS NOT NULL ORDER BY id DESC LIMIT 1",
            ).fetchone()
            health = {
                "schema_version": SCHEMA_VERSION, "run_id": run_id, "collected_at": collected_at,
                "snapshot_run_id": run_id if usable else previous_success[0] if previous_success else None,
                "sources": sources,
            }
            db.execute("UPDATE runs SET snapshot = ?, health = ? WHERE id = ?",
                       (json.dumps(snapshot) if snapshot else None, json.dumps(health), run_id))

        # Export from committed state while holding the writer lock, so overlapping
        # collectors cannot replace a newer run's exports with an older run.
        with db:
            db.execute("BEGIN IMMEDIATE")
            latest = db.execute(
                "SELECT snapshot FROM runs WHERE snapshot IS NOT NULL ORDER BY id DESC LIMIT 1",
            ).fetchone()
            report = db.execute("SELECT health FROM runs ORDER BY id DESC LIMIT 1").fetchone()
            write_json(directory / "latest.json", json.loads(latest[0]) if latest else {
                "schema_version": SCHEMA_VERSION, "run_id": None,
                "collected_at": None, "articles": [], "previously_seen_urls": [],
            })
            write_json(directory / "source-health.json", json.loads(report[0]))
    return usable
