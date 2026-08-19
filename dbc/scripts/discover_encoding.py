#!/usr/bin/env python3
"""Reverse-engineer a signal's encoding from CAN data pairs.

Feed it pairs of (raw CAN bytes, physical value) and it tests common
encodings: little-endian vs big-endian, unsigned vs signed, factors and
offsets, and start-bit placements.

Usage:
    python3 discover_encoding.py pairs.json

pairs.json is a list of objects (byte values are decimal ints):
[
  {"data": [8, 221, 0, 7, 66], "physical": 226.9},
  {"data": [10, 176, 0, 7, 114], "physical": 273.6}
]

The "physical" field may also be the DBC-reported (wrong) value when the
goal is to find the byte-swap relationship between two decodings.
"""

import json
import sys


def _bits(data):
    """CAN bit i -> character in string; bit 0 = LSB of byte 0."""
    return "".join(format(b, "08b")[::-1] for b in data)


def le_extract(data, start_bit, length):
    """Intel (little-endian): LSB at start_bit, bits ascend."""
    bits = _bits(data)
    return int(bits[start_bit:start_bit + length][::-1], 2)


def be_extract(data, start_bit, length):
    """Motorola (big-endian): MSB at start_bit, bits descend, wrapping
    from bit 0 of byte k to bit 7 of byte k+1."""
    bits = _bits(data)
    if start_bit + length - 1 >= len(bits) * 8:
        return None
    n_bits = len(bits)
    out, pos = [], start_bit
    for _ in range(length):
        out.append(bits[pos])
        if pos % 8 == 0:
            nxt = pos + 15
            pos = nxt if nxt + length - len(out) <= n_bits else n_bits
        else:
            pos -= 1
        if pos >= n_bits:
            return None
    return int("".join(out), 2)


def signed_value(raw, length):
    return raw if raw < (1 << (length - 1)) else raw - (1 << length)


FACTORS = [0.1, 1.0, 0.01, 0.001, 0.00390625, 0.25, 0.5, 0.125, 0.2, 0.02]


def test(data, phys):
    hits = []
    for bo_name, fn in (("BE", be_extract), ("LE", le_extract)):
        for length in (1, 2, 4, 8, 12, 16, 32):
            for sb in range(max(0, len(data) * 8 - length + 1)):
                raw = fn(data, sb, length)
                if raw is None:
                    continue
                for signed in (False, True):
                    val = signed_value(raw, length) if signed else raw
                    for factor in FACTORS:
                        phys_calc = val * factor
                        if abs(phys_calc - phys) < 1e-6 * max(1, abs(phys)):
                            hits.append(dict(
                                byte_order=bo_name, start_bit=sb, length=length,
                                signed=signed, factor=factor, raw=raw,
                                physical=phys_calc))
    # Also test byte-swapped 2-byte pairs (common quick diagnostic):
    # raw LE of the same two bytes = physical with factor 0.1 etc.
    return hits


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    with open(sys.argv[1]) as f:
        pairs = json.load(f)

    for i, p in enumerate(pairs):
        data = [int(x, 16, 0) if isinstance(x, str) else int(x) for x in p["data"]]
        phys = float(p["physical"])
        print(f"\n--- Pair {i}: data={' '.join(format(b,'02X') for b in data)} -> {phys}")
        hits = test(data, phys)
        seen = set()
        for h in hits:
            key = (h["byte_order"], h["start_bit"], h["length"], h["signed"], h["factor"])
            if key in seen:
                continue
            seen.add(key)
            print(f"  {h['byte_order']} start_bit={h['start_bit']} len={h['length']} "
                  f"signed={h['signed']} factor={h['factor']} -> raw {h['raw']} "
                  f"({hex(h['raw'])}) = {h['physical']}")
        if not hits:
            print("  No exact match among common encodings; consider an unusual "
                  "factor, an offset, or compare byte-swap relations between pairs.")


if __name__ == "__main__":
    main()
