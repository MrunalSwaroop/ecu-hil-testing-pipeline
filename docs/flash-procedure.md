# ECU Flash Procedure

Every lab run flashes the ECU with the newest firmware before testing, and verifies
afterwards that the ECU actually took the new software. This guarantees the
*Firmware version ↔ Test report* traceability link: no report can ever belong to a
stale or half-flashed ECU.

## Sequence

| Step | UDS service | Purpose |
|---|---|---|
| 1 | `0x10 0x03` | Enter extended diagnostic session |
| 2 | `0x27 0x01` / `0x27 0x02` | Security access (Seed & Key) |
| 3 | `0x31 0x01` (optional) | Erase memory routine |
| 4 | `0x34` | Request download (address + size) |
| 5 | `0x36` (×N) | Transfer data blocks |
| 6 | `0x37` | Request transfer exit |
| 7 | `0x11 0x01` | ECU reset (hard/application) |
| 8 | wait ~5 s | ECU reboot |
| 9 | `0xF1 0x95` | Read software version — **must match expected** |

The expected version defaults to the commit SHA in CI, so each run is provably tied
to one commit. If the read-back does not match, the run aborts with a clear failure
and the bench teardown restores the golden image before the pipeline ends.

## Three flash methods

The pipeline supports three back-ends, selected in `config/flash_config.json`:

| Method | Requires | When to use |
|---|---|---|
| `uds` (python-can) | python-can + Vector drivers | Default POC; fully scriptable, no extra Vector license |
| `capl` (CANoe) | CANoe | When you prefer running inside CANoe; uses `scripts/capl/FlashEcu.can` |
| `flashmanager` | CANoe Flash Manager license | Production setups with OEM-mandated flash description (CDD/ODX) |

## Adapting to your controller

1. **Addresses** — set `ecu_tx_id`/`ecu_rx_id` to your ECU's physical request/response
   IDs in `config/flash_config.json`.
2. **Seed & Key** — implement `compute_key()` in `scripts/lab/flash_ecu.py` with your
   ECU's algorithm (or disable with `"security_level": 0` during bring-up).
3. **Address & memory map** — adjust the download address (`0x08000000` default) and
   erase routine to your controller's memory map.
4. **Bootloader timing** — if your ECU needs a specific power-cycle or P2 timing,
   extend the waits/retries in `flash_ecu.py`.
5. **Version DID** — `0xF195` is the standard software-version DID; use `0xF189`
   (software fingerprint) or another DID if your OEM defines it differently.

## Golden image

Keep a known-good firmware at `firmware/golden/firmware.bin`. `bench_teardown.py`
re-flashes it after every run (even failed ones), so the bench is always left in a
usable state. Commit updates to this file like any other code change.
