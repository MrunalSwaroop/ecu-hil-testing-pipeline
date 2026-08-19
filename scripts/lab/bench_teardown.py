"""Post-run bench teardown (runs `if: always()` so it executes even after failures).

1. Re-flash the golden (baseline) firmware so the bench is never left in a
   failed/test state -- next run always starts from a known-good ECU image.
2. Power down / reset bench supplies according to config/bench_profile.json.

Stub: implement your PSU reset (SCPI) and wire flash restoration to your
golden image location. Uses the same UDS flasher as the main flash stage.
"""

import argparse
import json
import subprocess
import sys

DEFAULT_GOLDEN = "firmware/golden/firmware.bin"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/bench_profile.json")
    ap.add_argument("--golden", default=DEFAULT_GOLDEN)
    args = ap.parse_args()

    import os

    failures = []

    # 1) Restore golden firmware if present
    if os.path.isfile(args.golden):
        print("[teardown] Restoring golden firmware:", args.golden)
        res = subprocess.run([
            sys.executable, "scripts/lab/flash_ecu.py",
            "--firmware", args.golden,
            "--config", "config/flash_config.json",
            "--expected-version", "",  # no version gate on teardown restore
            "--report", "out/teardown_flash_result.json",
        ], capture_output=True, text=True, check=False)
        print(res.stdout)
        if res.returncode != 0:
            failures.append("golden flash restore failed")
    else:
        print("[teardown] SKIP: no golden firmware at", args.golden)

    # 2) Power down bench (replace with your PSU SCPI sequence)
    with open(args.config) as f:
        cfg = json.load(f)
    for psu in cfg.get("powersupplies", []):
        print(f"[teardown] Powering off '{psu['name']}' (implement SCPI OFF command)")
        # TODO: send PSU OFF, e.g. "OUTP OFF\r\n"

    if failures:
        print("[teardown] WARN:", "; ".join(failures))
        return 1
    print("[teardown] Bench returned to known-good state")
    return 0


if __name__ == "__main__":
    sys.exit(main())
