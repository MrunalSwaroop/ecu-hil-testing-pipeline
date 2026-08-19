# Troubleshooting & Workflow Reference

## What runs when

| Trigger | What happens |
|---|---|
| Push to `main` | Cloud CI (DBC validate + pytest). On green, lab workflow is dispatched automatically. |
| Pull request | Cloud CI only (lab never runs on PRs — keeps the bench free). |
| Manual (Actions tab) | *HIL Lab Run* with inputs: `run_flash` on/off, `test_suite` smoke/full. |

## Common failure modes

### Cloud CI fails, lab never runs
The DBC validator caught a defect before it could reach CANoe. Typical causes:

| Validator message | Meaning |
|---|---|
| `BA_ before BA_DEF_` | Attribute assignment precedes its definition — reorder in `definitions.json` |
| `protected attribute GenMsgIdType` | Vector system attribute used in the file — remove it |
| `syntax error` | Malformed DBC line — regenerate via `build_dbc.py` |

### Lab job never starts
The self-hosted runner is offline or not labelled `hil-bench`. CI still passes (the
lab stage is intentionally non-blocking in the POC). See
[`lab-runner-setup.md`](lab-runner-setup.md).

### Flash fails
Check in order: CAN bus wiring/supplies (pre-flight log), addresses in
`config/flash_config.json`, Seed & Key implementation, memory address/erase routine,
bootloader timing. The flash report at `out/flash_result.json` contains the exact
negative-response NRC when applicable.

### Tests fail but the ECU is fine
Look at the drill-down in the dashboard: per-case verdicts + logs. If a single case
flaps, it is flagged as a regression only if it passed in a previous run with a
*verified* flash — the firmware version stamp prevents false regressions from
flash failures.

### Dashboard shows nothing
`server.py` is not running or the API base URL in `dashboard/index.html` does not
point at the lab PC. Start the server (`python scripts/ingestion/server.py`) and
set the URL field to `http://<lab-pc-ip>:8765`.

## Design decisions worth knowing

The lab stage is **skipped, not failed**, when no runner is online — your PRs and
main-branch CI stay green on the cloud side. Firmware changes are only tested after
a *verified* flash; test-only changes can skip flashing via the `run_flash: false`
workflow input for fast re-runs. Native CANoe/vTESTstudio reports are always kept as
GitHub Actions artifacts (90-day retention) and linked from each dashboard run, so
nothing is lost even if the SQLite store is rebuilt.
