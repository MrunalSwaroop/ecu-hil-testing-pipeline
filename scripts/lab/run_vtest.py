"""Execute vTESTstudio test lists against the HIL bench via the command line.

Strategy:
  - vTESTstudioCmd.exe /batch /config <config> /testlist <list> /results <dir>
    (preferred when vTESTstudio license is available)
  - Fallback: CANoeCmd.exe /batch /playback with a CANoe test setup that embeds
    the vTESTstudio modules

Results (native HTML/XML) are exported to --outdir and later parsed by
scripts/ingestion/parse_results.py.
"""

import argparse
import glob
import os
import subprocess
import sys


def find_exe(name: str) -> str | None:
    import shutil

    return shutil.which(name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--testlist", required=True, help="vTESTstudio test list XML")
    ap.add_argument("--config", default="config/vtest_config.cfg")
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    vtcmd = find_exe("vTESTstudioCmd")
    if vtcmd is not None:
        cmd = [
            vtcmd, "/batch", "/noGui",
            "/config", args.config,
            "/testlist", args.testlist,
            "/results", args.outdir,
        ]
    else:
        canoe = find_exe("CANoeCmd")
        if canoe is None:
            print("[run_vtest] FAIL: neither vTESTstudioCmd nor CANoeCmd on PATH",
                  file=sys.stderr)
            return 1
        cmd = [canoe, "/batch", "/noLogo", "/exit",
               "/playback", args.config,
               "/testlist", args.testlist,
               "/resultfile", os.path.join(args.outdir, "canoe_result.xml")]

    print("[run_vtest]", " ".join(cmd))
    res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=7200)
    print(res.stdout)
    if res.returncode != 0:
        print(res.stderr, file=sys.stderr)
        print("[run_vtest] FAIL: test execution returned", res.returncode)
        return 1

    exported = glob.glob(os.path.join(args.outdir, "*"))
    print(f"[run_vtest] PASS: {len(exported)} result file(s) in {args.outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
