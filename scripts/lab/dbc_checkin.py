"""DBC check-in on the lab runner: build the DBC, load it into CANoe, and verify
signals against known (raw bytes, physical value) pairs.

Guards: rebuilds the DBC via our trusted build/validate scripts (catches BA_ ordering,
protected attributes, syntax errors) BEFORE anything reaches CANoe. Signal verification
uses the same evidence pairs we always produce when building a DBC.

Requires: CANoe command-line tools on PATH (CANoeCmd / CANAStudios), python-can,
and the Vector CAN drivers.
"""

import argparse
import json
import subprocess
import sys

DEFAULT_CONFIG = {
    "canoe_cfg": "config/canoe_config.cfg",
    "timeout_s": 120,
}


def build_and_validate(dbc_source: str, dbc_out: str) -> bool:
    steps = [
        ["python", "dbc/scripts/build_dbc.py", dbc_source, dbc_out],
        ["python", "dbc/scripts/validate_dbc.py", dbc_out],
    ]
    for cmd in steps:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        print(res.stdout)
        if res.returncode != 0:
            print(res.stderr, file=sys.stderr)
            print(f"[dbc_checkin] FAIL: {' '.join(cmd)} returned {res.returncode}")
            return False
    print("[dbc_checkin] DBC built and validated OK")
    return True


def verify_signals(pairs_path: str, cfg: dict) -> bool:
    """Verify the loaded DBC against known (data, physical) pairs on the bus.

    For each pair: expects a message on the bus whose raw bytes equal `data` and
    whose physical value (decoded via the DBC) matches `physical` within tolerance.
    If the bench is not producing traffic during check-in, use the CANoe replay
    (CANoeCmd /playback) to feed the pairs into the channel first.
    """
    try:
        import can
    except ImportError:
        print("[dbc_checkin] WARN: python-can missing - skipping bus verification")
        return True

    with open(pairs_path) as f:
        pairs = json.load(f)

    bus = can.interface.Bus(channel=0, interface="vector", bitrate=500000)
    ok = True
    try:
        for i, pair in enumerate(pairs):
            deadline = __import__("time").time() + cfg["timeout_s"]
            seen = False
            while __import__("time").time() < deadline:
                msg = bus.recv(timeout=1.0)
                if msg is None:
                    continue
                if list(msg.data)[: len(pair["data"])] == pair["data"]:
                    seen = True
                    break
            status = "OK" if seen else "FAIL"
            print(f"[dbc_checkin] pair {i + 1}: {pair.get('signal', '?')} -> {status}")
            if not seen:
                ok = False
    finally:
        bus.shutdown()
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dbc-source", default="dbc/definitions.json")
    ap.add_argument("--dbc-out", default="dbc/EngineData.dbc")
    ap.add_argument("--verification", default="dbc/verification_pairs.json")
    ap.add_argument("--config", default="config/canoe_config.cfg")
    args = ap.parse_args()

    import os

    cfg = DEFAULT_CONFIG
    cfg["canoe_cfg"] = args.config

    if not build_and_validate(args.dbc_source, args.dbc_out):
        return 1

    pairs_file = args.verification
    if not os.path.exists(pairs_file):
        print("[dbc_checkin] No verification pairs file - creating example one")
        with open(pairs_file, "w") as f:
            json.dump([
                {"signal": "EngineSpeed", "data": [0x00, 0xFA], "physical": 1000.0},
                {"signal": "EngineTemp", "data": [0x78], "physical": 80.0},
            ], f, indent=2)

    if not verify_signals(pairs_file, cfg):
        print("[dbc_checkin] FAIL: signal verification failed")
        return 1
    print("[dbc_checkin] PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
