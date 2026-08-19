"""Build (compile) CANoe test CAPL modules via CANoe command line.

Uses CANAStudios (CANoe's CAPL build tool) in batch mode. Exits non-zero if any
module fails to compile, stopping the pipeline before test execution.
"""

import argparse
import glob
import subprocess
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/canoe_config.cfg")
    ap.add_argument("--sources", default="capl/", help="directory containing .can modules")
    args = ap.parse_args()

    modules = sorted(glob.glob(f"{args.sources}/**/*.can", recursive=True))
    if not modules:
        print("[build_capl] No .can modules found under", args.sources)
        return 1

    # CANAStudios batch compile: one output DLL per module
    for mod in modules:
        out = mod.replace(".can", ".dll").replace("\\", "/")
        cmd = ["CANAStudios", "/batch", "/output", out, "/compile", mod]
        print("[build_capl]", " ".join(cmd))
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        print(res.stdout)
        if res.returncode != 0:
            print(res.stderr, file=sys.stderr)
            print(f"[build_capl] FAIL: {mod} did not compile")
            return 1

    print(f"[build_capl] PASS: {len(modules)} module(s) compiled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
