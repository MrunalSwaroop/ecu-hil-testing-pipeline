"""Lightweight REST API serving the results database to the dashboard.

Run on the lab PC (or any machine that holds results.db):
  python scripts/ingestion/server.py --db out/results.db --port 8765

Endpoints:
  GET /api/runs              -> list of runs (newest first)
  GET /api/runs/{run_id}     -> run detail with test cases
  GET /api/trends            -> aggregated pass rate per commit (for trend chart)
  GET /api/regressions       -> test cases that passed before but fail now

Served to the dashboard (scripts/ingestion/dashboard/ or GitHub Pages) via CORS.
"""

import argparse
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer

DB_PATH = "out/results.db"


class ResultsHandler(BaseHTTPRequestHandler):
    def _row_to_dict(self, row, columns):
        return dict(zip(columns, row))

    def do_GET(self):
        path = self.path.split("?")[0]
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            if path == "/api/runs":
                rows = conn.execute(
                    "SELECT * FROM runs ORDER BY timestamp DESC LIMIT 100"
                ).fetchall()
                data = [dict(r) for r in rows]
            elif path.startswith("/api/runs/"):
                run_id = path[len("/api/runs/"):]
                run = conn.execute(
                    "SELECT * FROM runs WHERE run_id = ?", (run_id,)
                ).fetchone()
                if run is None:
                    self._json(404, {"error": "run not found"})
                    return
                cases = [dict(r) for r in conn.execute(
                    "SELECT * FROM test_cases WHERE run_id = ?", (run_id,)
                ).fetchall()]
                data = {**dict(run), "test_cases": cases}
            elif path == "/api/trends":
                rows = conn.execute(
                    """SELECT timestamp, commit_sha, branch, overall_verdict,
                              total, passed, firmware_version
                       FROM runs ORDER BY timestamp ASC LIMIT 500"""
                ).fetchall()
                data = [dict(r) for r in rows]
            elif path == "/api/regressions":
                # cases that failed in the latest run but passed in any earlier run
                latest = conn.execute(
                    "SELECT run_id FROM runs ORDER BY timestamp DESC LIMIT 1"
                ).fetchone()
                if latest is None:
                    data = []
                else:
                    failed_now = conn.execute(
                        """SELECT DISTINCT name FROM test_cases
                           WHERE run_id = ? AND verdict = 'FAIL'""",
                        (latest["run_id"],),
                    ).fetchall()
                    regs = []
                    for (name,) in failed_now:
                        earlier_pass = conn.execute(
                            """SELECT run_id FROM test_cases
                               WHERE name = ? AND verdict = 'PASS'
                               ORDER BY id DESC LIMIT 1""",
                            (name,),
                        ).fetchone()
                        if earlier_pass:
                            regs.append({"name": name,
                                         "first_pass_run": earlier_pass["run_id"]})
                    data = regs
            else:
                self._json(404, {"error": "not found"})
                return
            self._json(200, data)
        finally:
            conn.close()

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, *_args):  # silence request logging
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="out/results.db")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()

    global DB_PATH
    DB_PATH = args.db
    server = HTTPServer(("0.0.0.0", args.port), ResultsHandler)
    print(f"[server] results API on http://0.0.0.0:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
