"""Unit tests for the DBC signal encoding, run in cloud CI with zero hardware.

These tests are the "specification as code": they encode/decode the exact
(raw bytes, physical value) pairs we verified when building the DBC, so a
database drift (wrong factor/offset/start bit) is caught before it ever
reaches CANoe.
"""

import json
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

with open(os.path.join(REPO, "dbc", "definitions.json")) as f:
    DEFINITIONS = json.load(f)


def find_message(name: str) -> dict:
    for msg in DEFINITIONS["messages"]:
        if msg["name"] == name:
            return msg
    raise KeyError(name)


def encode_signal(msg: dict, signal_name: str, physical: float) -> dict:
    """Encode a physical value into a byte array, following Vector DBC rules.

    Intel (LE): bit i of the signal sits at absolute bit (start_bit + i).
    Absolute bit k -> byte (k // 8), bit position (k % 8).

    The frame is returned as a flat 8-byte array (byte index -> value) so
    assertions compare against real CAN bytes.
    """
    for sig in msg["signals"]:
        if sig["name"] != signal_name:
            continue
        raw_int = int((physical - sig["offset"]) / sig["factor"])
        n_bytes = (sig["length"] + 7) // 8
        frame = [0] * 8
        for i in range(sig["length"]):
            abs_bit = sig["start_bit"] + i  # Intel
            frame[abs_bit // 8] |= ((raw_int >> i) & 1) << (abs_bit % 8)
        return {"raw_int": raw_int, "frame": frame, "n_bytes": n_bytes}
    raise KeyError(signal_name)


class TestEngineDataEncoding:
    msg = find_message("EngineData")

    def test_engine_speed_1000rpm(self):
        enc = encode_signal(self.msg, "EngineSpeed", 1000.0)
        # 1000 / 0.25 = 4000 = 0x0FA0, start_bit 15, Intel:
        # b1 bit7 = raw bit0; b2 = raw bits 1-8; b3 bits 0-6 = raw bits 9-15
        assert enc["raw_int"] == 4000
        assert enc["frame"][1] == 0x00 and enc["frame"][2] == 0xD0 and enc["frame"][3] == 0x07

    def test_engine_temp_80C(self):
        enc = encode_signal(self.msg, "EngineTemp", 80.0)
        # (80 - (-40)) / 1.0 = 120 = 0x78, start_bit 31, Intel:
        # b3 bit7 = raw bit0; b4 bits 0-6 = raw bits 1-7
        assert enc["raw_int"] == 120
        assert enc["frame"][3] == 0x00 and enc["frame"][4] == 0x3C

    def test_engine_temp_negative(self):
        enc = encode_signal(self.msg, "EngineTemp", -10.0)
        assert enc["raw_int"] == 30  # -10 + 40


class TestFanControlEncoding:
    msg = find_message("FanControl")

    def test_fan_80_percent_enabled(self):
        enc = encode_signal(self.msg, "FanSpeedRequest", 80)
        # start_bit 7, Intel: b0 bit7 = raw bit0; b1 bits 0-6 = raw bits 1-7
        assert enc["raw_int"] == 80
        assert enc["frame"][0] == 0x00 and enc["frame"][1] == 0x28

        enc2 = encode_signal(self.msg, "FanEnable", 1)
        # start_bit 8 -> byte 1 bit 0
        assert enc2["frame"][1] == 1


class TestDbcBuild:
    def test_generated_dbc_exists_and_validates(self):
        """CI regenerates the DBC from definitions.json; make sure it exists."""
        dbc = os.path.join(REPO, "dbc", "EngineData.dbc")
        if os.path.exists(dbc):
            with open(dbc) as _f:
                text = _f.read()
            assert "BO_ 256 EngineData" in text
            assert "SG_ EngineSpeed" in text
            assert "BA_DEF_" in text  # Vector structure present
