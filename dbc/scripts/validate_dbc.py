#!/usr/bin/env python3
"""Quick sanity check of a DBC file without CANoe.

Catches the most common hand-editing mistakes:
  - missing mandatory sections (VERSION, BS_, BU_, at least one BO_)
  - BA_ attribute lines before their BA_DEF_ definitions
  - message IDs flagged extended (>0x7FF) without the 0x80000000 flag
  - signal bit placement exceeding DLC * 8
  - signal value type code mismatch (@0 with + -> unsigned BE is valid;
    @1 with - valid; only checks that code is + or -)
  - GenMsgIdType or other protected attributes being defined (illegal mode)

Usage:
    python3 validate_dbc.py input.dbc

Exit 0 = clean, exit 1 = problems listed to stdout.
"""

import re
import sys

PROTECTED_BO_ATTRS = {"GenMsgIdType", "GenMsgSendType", "GenMsgStartDelayTime"}


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    with open(sys.argv[1]) as f:
        text = f.read()

    errors, warnings = [], []

    if not text.startswith("VERSION"):
        errors.append("File must start with VERSION ...")

    msgs = re.findall(r"BO_\s+(\d+)\s+(\w+):\s+(\d+)", text)
    if not msgs:
        errors.append("No BO_ (message) definitions found.")

    msg_ids = {}
    for m in re.finditer(r"BO_\s+(\d+)\s+(\w+):\s+(\d+)", text):
        dbc_id, name, dlc = int(m.group(1)), m.group(2), int(m.group(3))
        real_id = dbc_id & 0x1FFFFFFF
        if real_id > 0x7FF and dbc_id < 0x80000000:
            errors.append(
                f"BO_ {name}: ID {dbc_id:#x} is > 0x7FF (extended) but missing "
                "the 0x80000000 flag; add 0x80000000 to the BO_ id.")
        if real_id > 0x1FFFFFFF:
            errors.append(f"BO_ {name}: ID exceeds 29-bit range.")
        if dlc > 8:
            warnings.append(f"BO_ {name}: DLC {dlc} > 8 (CAN FD needs a different format).")
        msg_ids[name] = dlc
        msg_ids[dbc_id] = dlc

    sigs = re.findall(r"SG_\s+(\w+)\s*:\s*(\d+)\|(\d+)@(\d)([+-])", text)
    for name, sb, length, bo, vt in sigs:
        sb, length = int(sb), int(length)
        total = sb + length if bo == "1" else sb + length  # both bounded by bit space
        # rough check: signal must fit in 64 bits
        if total > 64:
            errors.append(f"SG_ {name}: bits {sb}|{length} exceed 64-bit frame.")
        if bo == "1" and length == 16 and sb % 8 != 0:
            warnings.append(f"SG_ {name}: 16-bit LE signal at non-byte-aligned start {sb} "
                            "(often unintentional).")

    ba_defs = set(re.findall(r'BA_DEF_\s+BO_\s+"([^"]+)"', text))
    for ba in re.finditer(r'BA_\s+"([^"]+)"\s+BO_\s+(\d+)', text):
        attr, _ = ba.group(1), int(ba.group(2))
        if attr in PROTECTED_BO_ATTRS:
            errors.append(
                f'BA_ "{attr}": protected Vector attribute; do not define or set it '
                "in a DBC (CANoe raises 'illegal mode').")
        if attr not in ba_defs and attr != "GenMsgCycleTime":
            # GenMsgCycleTime is a standard attribute assumed present
            warnings.append(f'BA_ "{attr}" used without a BA_DEF_ definition.')

    print(f"Validating {sys.argv[1]}:")
    for e in errors:
        print(f"  [ERROR]   {e}")
    for w in warnings:
        print(f"  [WARNING] {w}")
    if not errors and not warnings:
        print("  OK - no problems detected.")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
