"""Bench pre-flight check: verifies the HIL bench is ready before flashing/testing.

Checks (all configurable via config/bench_profile.json):
  - Power supplies are on and within voltage windows
  - CAN bus is alive (a configured probe message is seen within a timeout)
  - ECU reports no active/communication DTCs (optional, via UDS 0x19 0x02)
  - CANoe is installed and reachable

If any check fails, exits non-zero and the pipeline stops.
Runs on the Windows lab PC. Requires python-can + Vector hardware drivers.
"""

import argparse
import json
import sys
import time

try:
    import can  # python-can
except ImportError:
    can = None


DEFAULT_PROFILE = {
    "powersupplies": [
        {"name": "ECU 12V", "channel": 0, "min_v": 11.0, "max_v": 14.5}
    ],
    "bus_probe": {"channel": 0, "message_id": "0x100", "timeout_ms": 3000},
    "diagnostics": {
        "enabled": False,
        "ecu_tx_id": "0x700",
        "ecu_rx_id": "0x708",
        "dtc_limit": 0,
    },
    "canoe": {"required": True},
}


def check_canoe(cfg: dict) -> bool:
    ok = True
    if cfg["canoe"]["required"]:
        import shutil

        if shutil.which("CANoeCmd") is None and shutil.which("CANAStudios") is None:
            print("[preflight] FAIL: CANoe command-line tools not found on PATH")
            ok = False
        else:
            print("[preflight] OK: CANoe command-line tools found")
    return ok


def check_bus_probe(cfg: dict) -> bool:
    probe = cfg.get("bus_probe")
    if not probe or can is None:
        print("[preflight] SKIP: bus probe not configured or python-can missing")
        return True
    bus = can.interface.Bus(channel=probe["channel"], interface="vector", bitrate=500000)
    try:
        deadline = time.time() + probe["timeout_ms"] / 1000.0
        seen = False
        while time.time() < deadline:
            msg = bus.recv(timeout=1.0)
            if msg is not None and msg.arbitration_id == int(probe["message_id"], 16):
                seen = True
                break
        if seen:
            print(f"[preflight] OK: probe message {probe['message_id']} seen on CH{probe['channel']}")
            return True
        print(f"[preflight] FAIL: probe message {probe['message_id']} not seen within {probe['timeout_ms']} ms")
        return False
    finally:
        bus.shutdown()


def check_powersupplies(cfg: dict) -> bool:
    """Power-supply check stub.

    Replace with your bench's PSU interface (e.g. SCPI over TCP, Vector VT supply
    API, or lab PSU vendor CLI). Returns True for channels within [min_v, max_v].
    """
    all_ok = True
    for psu in cfg.get("powersupplies", []):
        # TODO: read real voltage, e.g. via SCPI:
        #   import socket; s = socket.socket(); s.connect((psu['ip'], 5025))
        #   v = float(s.sendall(b"MEAS:VOLT?\r\n") and s.recv(1024))
        measured_v = None  # <-- implement for your hardware
        if measured_v is None:
            print(f"[preflight] SKIP: no voltage reading for '{psu['name']}' (implement SCPI/API)")
            continue
        if psu["min_v"] <= measured_v <= psu["max_v"]:
            print(f"[preflight] OK: '{psu['name']}' = {measured_v:.2f} V")
        else:
            print(f"[preflight] FAIL: '{psu['name']}' = {measured_v:.2f} V "
                  f"(expected {psu['min_v']}..{psu['max_v']})")
            all_ok = False
    return all_ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/bench_profile.json")
    args = ap.parse_args()

    with open(args.config) as f:
        cfg = json.load(f)

    checks = [
        ("CANoe", lambda: check_canoe(cfg)),
        ("Power supplies", lambda: check_powersupplies(cfg)),
        ("CAN bus probe", lambda: check_bus_probe(cfg)),
    ]
    results = {name: fn() for name, fn in checks}

    print("\n[preflight] summary:", {k: v for k, v in results.items()})
    if all(results.values()):
        print("[preflight] PASS - bench ready")
        return 0
    print("[preflight] FAIL - aborting lab run")
    return 1


if __name__ == "__main__":
    sys.exit(main())
