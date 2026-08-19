"""Parse native vTESTstudio / CANoe test results into a normalized JSON schema.

Input:
  - vTESTstudio result XML (vTESTstudioCmd /results output)
  - CANoe result XML (/resultfile output from CANoeCmd)
  - out/flash_result.json (firmware version + expected version)

Output:
  - out/run_summary.json  -- normalized run summary consumed by the dashboard
    schema:
    {
      "run_id": "<uuid>",
      "timestamp": "ISO8601",
      "commit_sha": "...",
      "branch": "...",
      "runner": "...",
      "firmware_version": "...",
      "expected_version": "...",
      "flash_ok": true|false,
      "overall_verdict": "PASS" | "FAIL" | "ERROR",
      "suites": [
        { "name": "...", "test_cases": [
            { "name": "...", "verdict": "PASS|FAIL|ERROR",
              "duration_ms": 123, "log": "..." } ] }
      ],
      "native_report_path": "..."
    }

Run on the lab PC after each test execution (lab.yml, post Results step).
"""

import argparse
import glob
import json
import os
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

NS = {
    "vts": "http://vector.com/vTESTstudio/results",
    "canoe": "urn:schemas-vector-com:canoe:results",
}


def parse_vtest_xml(path: str) -> list:
    """Parse a vTESTstudio result XML.

    vTESTstudio result structure (varies slightly by version):
      <TestRun> <TestModule name=...> <TestCase name=... verdict=...> ...
    This parser is tolerant: it walks the tree and extracts anything that looks
    like a test case with a verdict attribute.
    """
    tree = ET.parse(path)
    cases = []
    for elem in tree.iter():
        name = elem.get("name") or elem.get("id")
        verdict = (elem.get("verdict") or elem.get("result") or "").upper()
        if name and verdict in ("PASS", "FAIL", "ERROR", "NORESULT"):
            duration = elem.get("durationMs") or elem.get("duration")
            log = ""
            log_elem = elem.find(".//log") or elem.find(".//comment")
            if log_elem is not None and log_elem.text:
                log = log_elem.text[:500]
            cases.append({
                "name": name,
                "verdict": verdict,
                "duration_ms": int(duration) if duration and duration.isdigit() else None,
                "log": log,
                "source_file": os.path.basename(path),
            })
    return cases


def parse_canoe_result_xml(path: str) -> list:
    """Parse a CANoeCmd /resultfile XML into test-case entries."""
    tree = ET.parse(path)
    cases = []
    for elem in tree.iter():
        tag = elem.tag.split("}")[-1].lower()
        if tag in ("testcase", "test") and elem.get("name"):
            verdict = (elem.get("verdict") or elem.get("result") or "ERROR").upper()
            cases.append({
                "name": elem.get("name"),
                "verdict": verdict,
                "duration_ms": None,
                "log": "",
                "source_file": os.path.basename(path),
            })
    return cases


def overall_verdict(flash_ok: bool, cases: list) -> str:
    if not flash_ok:
        return "FAIL"
    if not cases:
        return "ERROR"
    verdicts = {c["verdict"] for c in cases}
    if verdicts <= {"PASS"}:
        return "PASS"
    if verdicts <= {"PASS", "NORESULT"}:
        return "PASS"
    return "FAIL"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vtest-xml", nargs="+", help="vTESTstudio result XML files/globs")
    ap.add_argument("--canoe-xml", help="CANoe result XML file")
    ap.add_argument("--firmware-version", help="out/flash_result.json from the flash stage")
    ap.add_argument("--commit", default="", help="commit SHA")
    ap.add_argument("--runner", default="", help="runner name")
    ap.add_argument("--outdir", default="out")
    args = ap.parse_args()

    cases = []
    for pattern in (args.vtest_xml or []):
        for path in glob.glob(pattern):
            try:
                cases += parse_vtest_xml(path)
            except ET.ParseError as exc:
                print(f"[parse] WARN: could not parse {path}: {exc}")

    if args.canoe_xml and os.path.isfile(args.canoe_xml):
        try:
            cases += parse_canoe_result_xml(args.canoe_xml)
        except ET.ParseError as exc:
            print(f"[parse] WARN: could not parse {args.canoe_xml}: {exc}")

    flash_ok = True
    fw_version = expected = ""
    if args.firmware_version and os.path.isfile(args.firmware_version):
        with open(args.firmware_version) as f:
            flash = json.load(f)
        flash_ok = flash.get("flash_ok", True)
        fw_version = flash.get("version_check", {}).get("version_read", "")
        expected = flash.get("expected_version", "")

    verdict = overall_verdict(flash_ok, cases)
    summary = {
        "run_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "commit_sha": args.commit,
        "branch": os.environ.get("GITHUB_REF_NAME", ""),
        "runner": args.runner,
        "firmware_version": fw_version,
        "expected_version": expected,
        "flash_ok": flash_ok,
        "overall_verdict": verdict,
        "suites": [{"name": "default", "test_cases": cases}],
        "stats": {
            "total": len(cases),
            "passed": sum(1 for c in cases if c["verdict"] == "PASS"),
            "failed": sum(1 for c in cases if c["verdict"] == "FAIL"),
            "errors": sum(1 for c in cases if c["verdict"] == "ERROR"),
        },
    }

    os.makedirs(args.outdir, exist_ok=True)
    out_path = os.path.join(args.outdir, "run_summary.json")
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"[parse] {verdict}: {summary['stats']['passed']}/{summary['stats']['total']} passed")
    print(f"[parse] summary written to {out_path}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
