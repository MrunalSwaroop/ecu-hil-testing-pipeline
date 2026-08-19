"""Store normalized run summaries into a SQLite results database.

The DB (out/results.db) is the data source for the dashboard API server
(scripts/ingestion/server.py).

Usage (lab runner):
  python scripts/ingestion/post_results.py --db out/results.db [--summary out/run_summary.json]
"""

import argparse
import json
import os
import sqlite3
import sys

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    commit_sha TEXT,
    branch TEXT,
    runner TEXT,
    firmware_version TEXT,
    expected_version TEXT,
    flash_ok INTEGER,
    overall_verdict TEXT,
    total INTEGER,
    passed INTEGER,
    failed INTEGER,
    errors INTEGER,
    raw_summary TEXT
);

CREATE TABLE IF NOT EXISTS test_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    suite TEXT,
    name TEXT NOT NULL,
    verdict TEXT NOT NULL,
    duration_ms INTEGER,
    log TEXT,
    source_file TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_cases_run ON test_cases(run_id);
CREATE INDEX IF NOT EXISTS idx_runs_ts ON runs(timestamp);
"""


def upsert_run(db: sqlite3.Connection, summary: dict) -> None:
    stats = summary.get("stats", {})
    db.execute(
        """INSERT OR REPLACE INTO runs
           (run_id, timestamp, commit_sha, branch, runner, firmware_version,
            expected_version, flash_ok, overall_verdict, total, passed, failed,
            errors, raw_summary)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            summary["run_id"], summary["timestamp"], summary.get("commit_sha"),
            summary.get("branch"), summary.get("runner"),
            summary.get("firmware_version"), summary.get("expected_version"),
            int(summary.get("flash_ok", False)), summary.get("overall_verdict"),
            stats.get("total"), stats.get("passed"), stats.get("failed"),
            stats.get("errors"), json.dumps(summary),
        ),
    )
    db.execute("DELETE FROM test_cases WHERE run_id = ?", (summary["run_id"],))
    for suite in summary.get("suites", []):
        for tc in suite.get("test_cases", []):
            db.execute(
                """INSERT INTO test_cases
                   (run_id, suite, name, verdict, duration_ms, log, source_file)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (summary["run_id"], suite.get("name"), tc["name"], tc["verdict"],
                 tc.get("duration_ms"), tc.get("log"), tc.get("source_file")),
            )
    db.commit()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="out/results.db")
    ap.add_argument("--summary", default="out/run_summary.json")
    args = ap.parse_args()

    if not os.path.isfile(args.summary):
        print(f"[ingestion] SKIP: no summary at {args.summary}", file=sys.stderr)
        return 0

    with open(args.summary) as f:
        summary = json.load(f)

    os.makedirs(os.path.dirname(args.db) or ".", exist_ok=True)
    conn = sqlite3.connect(args.db)
    conn.executescript(SCHEMA)
    upsert_run(conn, summary)

    print(f"[ingestion] stored run {summary['run_id']} ({summary['overall_verdict']})")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
