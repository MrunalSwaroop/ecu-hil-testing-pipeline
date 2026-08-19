#!/usr/bin/env python3
"""Generate a Vector-format DBC file from a Python definition.

Usage:
    python3 build_dbc.py definitions.json output.dbc

The JSON input is a dict (or list of dicts) describing messages, e.g.:

{
  "version": "",
  "buses": ["CAN"],
  "messages": [
    {
      "id": "0x305",          # hex string; extended CAN IDs may be up to 0x1FFFFFFF
      "name": "AngleMsg",
      "dlc": 5,
      "cycle_time_ms": null,  # optional int; omitted from output when null
      "comment": null,        # optional string
      "signals": [
        {
          "name": "Angle",
          "start_bit": 7,
          "length": 16,
          "byte_order": "motorola",   # "motorola" (big-endian) or "intel" (little-endian)
          "value_type": "signed",     # "signed" or "unsigned"
          "factor": 0.1,
          "offset": 0.0,
          "min": -1512,
          "max": 1512,
          "unit": "deg",
          "comment": null
        }
      ]
    }
  ]
}

Byte order notes (Vector DBC convention):
  Motorola (big-endian): @0  -- signal starts at the MSB start bit
  Intel    (little-endian): @1 -- signal starts at the LSB start bit

IMPORTANT extended ID rule: in the DBC file the ID must have 0x80000000 added
(extended-frame flag). This script does that automatically for any id > 0x7FF.
"""

import json
import sys


def to_motorola_code(byte_order: str) -> str:
    return "0" if byte_order.lower().startswith("mot") else "1"


def to_value_code(value_type: str) -> str:
    return "-" if value_type.lower().startswith("sign") else "+"


def format_number(v):
    """Emit numbers compactly: integers without decimals, floats as-is."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return repr(v)


def build_dbc_text(defn) -> str:
    if isinstance(defn, list):
        msgs = [m for d in defn for m in d.get("messages", [])]
        version = defn[0].get("version", "") if defn else ""
    else:
        msgs = defn["messages"]
        version = defn.get("version", "")

    lines = [
        f'VERSION "{version}"',
        "",
        "NS_ :",
        "\tNS_DESC_",
        "\tCM_",
        "\tBA_DEF_",
        "\tBA_",
        "\tVAL_",
        "\tCAT_DEF_",
        "\tCAT_",
        "\tFILTER",
        "\tBA_DEF_DEF_",
        "\tEV_DATA_",
        "\tENVVAR_DATA_",
        "\tSGTYPE_",
        "\tSGTYPE_VAL_",
        "\tBA_DEF_SGTYPE_",
        "\tBA_SGTYPE_",
        "\tSIG_TYPE_REF_",
        "\tVAL_TABLE_",
        "\tSIG_GROUP_",
        "\tSIG_VALTYPE_",
        "\tSIGTYPE_VALTYPE_",
        "\tBO_TX_BU_",
        "\tBA_REL_",
        "\tCOMMENT_",
        "\tSG_MUL_VAL_",
        "",
        "BS_:",
        "",
        "BU_:",
        "",
    ]

    for msg in msgs:
        can_id = int(str(msg["id"]).replace("0x", "").replace("X", ""), 16)
        dbc_id = can_id + 0x80000000 if can_id > 0x7FF else can_id
        lines.append(f'BO_ {dbc_id} {msg["name"]}: {msg["dlc"]} Vector__XXX')
        for sig in msg["signals"]:
            bo = to_motorola_code(sig["byte_order"])
            vt = to_value_code(sig["value_type"])
            unit = sig.get("unit", "") or '""'
            if not unit.startswith('"'):
                unit = f'"{unit}"'
            lines.append(
                f" SG_ {sig['name']} : {sig['start_bit']}|{sig['length']}@{bo}{vt} "
                f"({format_number(sig['factor'])},{format_number(sig['offset'])}) "
                f"[{format_number(sig['min'])}|{format_number(sig['max'])}] {unit} Vector__XXX"
            )
        lines.append("")

    # Comments
    for msg in msgs:
        can_id = int(str(msg["id"]).replace("0x", "").replace("X", ""), 16)
        dbc_id = can_id + 0x80000000 if can_id > 0x7FF else can_id
        if msg.get("comment"):
            lines.append(f'CM_ BO_ {dbc_id} "{msg["comment"]}";')
        for sig in msg["signals"]:
            if sig.get("comment"):
                lines.append(f'CM_ SG_ {dbc_id} {sig["name"]} "{sig["comment"]}";')
    has_comments = any(
        m.get("comment") or any(s.get("comment") for s in m["signals"]) for m in msgs
    )
    if has_comments:
        lines.append("")

    # GenMsgCycleTime attribute (only if at least one message declares it)
    timed_msgs = [m for m in msgs if m.get("cycle_time_ms") is not None]
    if timed_msgs:
        lines += [
            'BA_DEF_ BO_ "GenMsgCycleTime" INT 0 10000;',
            'BA_DEF_DEF_ "GenMsgCycleTime" 0;',
        ]
        for m in timed_msgs:
            can_id = int(str(m["id"]).replace("0x", "").replace("X", ""), 16)
            dbc_id = can_id + 0x80000000 if can_id > 0x7FF else can_id
            lines.append(f'BA_ "GenMsgCycleTime" BO_ {dbc_id} {m["cycle_time_ms"]};')
        lines.append("")

    if lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    with open(sys.argv[1]) as f:
        defn = json.load(f)
    text = build_dbc_text(defn)
    with open(sys.argv[2], "w") as f:
        f.write(text)
    print(f"Wrote {sys.argv[2]}")


if __name__ == "__main__":
    main()
