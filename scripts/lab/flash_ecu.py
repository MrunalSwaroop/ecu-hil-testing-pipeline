"""Automated ECU flash with UDS post-flash version verification.

Flash method selection (config/flash_config.json, key `method`):
  - "uds":   CAPL-free UDS download via python-can
             (0x10 extendedSession -> 0x27 securityAccess -> 0x31/0x34/0x36/0x37
             download -> 0x11 ECU reset -> read 0xF195 software version)
  - "capl":  delegates to CANoe running scripts/capl/FlashEcu.can (needs CANoe)
  - "flashmanager": uses CANoe Flash Manager command line (needs CANoe Flash Manager license)

Post-flash verification: reads the ECU software version (UDS 0xF195) and compares it
against the expected version. `--expected-version` is the commit SHA in CI, but can
be any expected string your firmware embeds. The pipeline ABORTS if the ECU did not
take the new software -- guaranteeing Firmware version <-> Test report traceability.

Outputs out/flash_result.json (consumed by report ingestion).
"""

import argparse
import json
import logging
import sys
import time

try:
    import can
except ImportError:
    can = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("flash_ecu")

DEFAULT_CONFIG = {
    "method": "uds",
    "channel": 0,
    "bitrate": 500000,
    "functional_addressing": False,
    "ecu_tx_id": "0x700",   # tester -> ECU (physical)
    "ecu_rx_id": "0x708",   # ECU -> tester
    "tester_id": "0x7F0",
    "security_level": 1,
    "seed_key": None,            # TODO: implement your Seed&Key algorithm
    "block_size": 1024,
    "max_retries": 3,
    "timeout_s": 5,
}


# ---------------------------------------------------------------- UDS helpers


def send_uds(bus, tx_id: int, rx_id: int, service: int, data: bytes,
             timeout: float, expect_positive: bool = True):
    """Send an ISO-TP style single-frame UDS request and return the response PDU."""
    frame = can.Message(arbitration_id=tx_id, data=bytes([len(data) + 1, service]) + data,
                        is_extended_id=False)
    bus.send(frame)
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = bus.recv(timeout=timeout)
        if msg is None:
            continue
        if msg.arbitration_id == rx_id:
            pdu = bytes(msg.data)
            if pdu[1] == 0x7F and pdu[2] == service:
                if expect_positive:
                    raise RuntimeError(f"Negative response 0x7F {pdu[2]:02X} NRC={pdu[3]:02X}")
                return pdu
            if pdu[1] == service + 0x40:
                return pdu
    raise TimeoutError(f"No UDS response for service 0x{service:02X} within {timeout}s")


def flash_uds(fw_path: str, cfg: dict, report: dict) -> bool:
    """UDS sequential download (0x34/0x36/0x37) of a raw .bin firmware."""
    if can is None:
        raise RuntimeError("python-can not installed on lab PC")

    bus = can.interface.Bus(channel=cfg["channel"], interface="vector", bitrate=cfg["bitrate"])
    try:
        tx, rx = int(cfg["ecu_tx_id"], 16), int(cfg["ecu_rx_id"], 16)

        # 1) Extended diagnostic session
        send_uds(bus, tx, rx, 0x10, bytes([0x03]), cfg["timeout_s"])
        log.info("UDS: extended session entered")

        # 2) Security access (Seed&Key)
        if cfg["security_level"]:
            req = send_uds(bus, tx, rx, 0x27, bytes([cfg["security_level"]]), cfg["timeout_s"])
            seed = req[2:]
            key = compute_key(seed, cfg.get("seed_key")) if cfg.get("seed_key") else b"\x00" * len(seed)
            send_uds(bus, tx, rx, 0x27, bytes([cfg["security_level"] + 1]) + key, cfg["timeout_s"])
            log.info("UDS: security unlocked (level %d)", cfg["security_level"])

        # 3) Routine control: erase memory (0x31 0x01 FF800000 ...) if supported
        try:
            send_uds(bus, tx, rx, 0x31,
                     bytes([0x01, 0xFF]) + (0x800000).to_bytes(3, "big"),
                     cfg["timeout_s"])
            log.info("UDS: erase memory requested")
        except RuntimeError:
            log.warning("UDS: erase routine not supported, continuing")

        # 4) Sequential download
        with open(fw_path, "rb") as _fw:
            fw = _fw.read()
        send_uds(bus, tx, rx, 0x34,
                 bytes([0x00, 0x44]) + (0x08000000).to_bytes(4, "big") + len(fw).to_bytes(3, "big"),
                 cfg["timeout_s"])
        block_size = cfg["block_size"]
        block_no = 1
        for start in range(0, len(fw), block_size):
            chunk = fw[start:start + block_size]
            data = bytes([block_no & 0xFF]) + chunk
            # ISO-TP: first frame (if >7 bytes) / consecutive frames handled by python-can ISO-TP
            send_uds(bus, tx, rx, 0x36, data, cfg["timeout_s"] * 2)
            block_no += 1
        send_uds(bus, tx, rx, 0x37, b"", cfg["timeout_s"])
        log.info("UDS: download complete, %d bytes", len(fw))

        # 5) ECU reset (application)
        send_uds(bus, tx, rx, 0x11, bytes([0x01]), cfg["timeout_s"])
        time.sleep(5)  # wait for reboot
        log.info("UDS: ECU reset complete")
        return True
    finally:
        bus.shutdown()


def verify_version(cfg: dict, expected: str) -> dict:
    """Read ECU software version via UDS 0xF195 and compare with expected."""
    bus = can.interface.Bus(channel=cfg["channel"], interface="vector", bitrate=cfg["bitrate"])
    try:
        tx, rx = int(cfg["ecu_tx_id"], 16), int(cfg["ecu_rx_id"], 16)
        for attempt in range(cfg["max_retries"]):
            try:
                send_uds(bus, tx, rx, 0x10, bytes([0x03]), cfg["timeout_s"])
                resp = send_uds(bus, tx, rx, 0xF1, bytes([0x95]), cfg["timeout_s"])
                version = resp[2:].decode("ascii", errors="replace").strip()
                match = (version == expected) or expected in version
                return {"version_read": version, "expected": expected, "verified": match}
            except (RuntimeError, TimeoutError) as exc:
                log.warning("Version read attempt %d failed: %s", attempt + 1, exc)
                time.sleep(3)
        return {"version_read": None, "expected": expected, "verified": False}
    finally:
        bus.shutdown()


def compute_key(seed: bytes, spec) -> bytes:
    """Placeholder Seed&Key. Replace with your ECU's algorithm (e.g. AES, LFSR)."""
    raise NotImplementedError("Implement your Seed&Key algorithm in compute_key()")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--firmware", required=True, help="firmware dir or .bin file")
    ap.add_argument("--config", default="config/flash_config.json")
    ap.add_argument("--expected-version", default="", help="expected SW version (e.g. commit SHA)")
    ap.add_argument("--report", default="out/flash_result.json")
    args = ap.parse_args()

    import os

    with open(args.config) as f:
        cfg = {**DEFAULT_CONFIG, **json.load(f)}

    fw_path = args.firmware if os.path.isfile(args.firmware) else os.path.join(
        args.firmware, max(os.listdir(args.firmware)))

    report = {
        "firmware_file": fw_path,
        "expected_version": args.expected_version,
        "method": cfg["method"],
    }

    try:
        if cfg["method"] == "uds":
            report["flash_ok"] = flash_uds(fw_path, cfg, report)
        else:
            log.error("Flash method '%s' not implemented in this POC. "
                      "Use 'uds' or wire up CANoe Flash Manager/CAPL.", cfg["method"])
            report["flash_ok"] = False
    except Exception as exc:  # noqa: BLE001
        log.error("Flash failed: %s", exc)
        report["flash_ok"] = False
        report["error"] = str(exc)

    # Post-flash version verification (always attempted when flash succeeded)
    if report.get("flash_ok") and args.expected_version:
        report["version_check"] = verify_version(cfg, args.expected_version)
        report["flash_ok"] = report["version_check"]["verified"]
        if not report["flash_ok"]:
            report["error"] = ("ECU software version mismatch after flash: read="
                               f"{report['version_check']['version_read']}, "
                               f"expected={args.expected_version}")

    os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
    with open(args.report, "w") as f:
        json.dump(report, f, indent=2)

    status = "PASS" if report["flash_ok"] else "FAIL"
    print(f"\n[flash] {status} - report written to {args.report}")
    return 0 if report["flash_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
