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


def record_run(directory, collected_at, records, source_health):
    unique = {}
    for record in records:
        validate_article(record)
        unique.setdefault(record["canonical_url"], record)
    directory.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(directory / "history.sqlite3", timeout=30)) as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript(DDL)
        with db:
            db.execute("BEGIN IMMEDIATE")
            run_id = db.execute("INSERT INTO runs (health) VALUES ('{}')").lastrowid
            new = 0
            previously_seen_urls = []
            for url, record in unique.items():
                first_run = db.execute(
                    "SELECT first_run_id FROM articles WHERE canonical_url = ?", (url,),
                ).fetchone()
                if first_run:
                    previously_seen_urls.append(url)
                else:
                    new += 1
                db.execute("""
                    INSERT INTO articles (canonical_url, record, first_run_id, last_run_id)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(canonical_url) DO UPDATE SET
                        record = excluded.record, last_run_id = excluded.last_run_id
                """, (url, json.dumps(record), first_run[0] if first_run else run_id, run_id))
            snapshot = {
                "schema_version": SCHEMA_VERSION, "run_id": run_id,
                "collected_at": collected_at, "articles": list(unique.values()),
                "previously_seen_urls": previously_seen_urls,
            } if unique else None
            previous_success = db.execute(
                "SELECT snapshot FROM runs WHERE snapshot IS NOT NULL ORDER BY id DESC LIMIT 1",
            ).fetchone()
            current_snapshot = snapshot or (
                json.loads(previous_success[0]) if previous_success else None
            )
            dates = [record["published_at"] for record in unique.values() if record["published_at"]]
            health = {
                "schema_version": SCHEMA_VERSION, "run_id": run_id, "collected_at": collected_at,
                "snapshot_run_id": current_snapshot["run_id"] if current_snapshot else None,
                "sources": [{
                    **source_health,
                    "records": len(unique), "new": new, "previously_seen": len(previously_seen_urls),
                    "duplicates_in_run": len(records) - len(unique),
                    "latest_published_at": max(dates, default=None),
                    "last_success_at": current_snapshot["collected_at"] if current_snapshot else None,
                    "retries": sum(max(0, check["attempts"] - 1) for check in source_health["checks"]),
                }],
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
