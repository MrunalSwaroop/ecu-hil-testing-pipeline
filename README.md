# ECU HIL CI/CD/CT Pipeline

End-to-end pipeline for testing a physical ECU on a HIL bench: from **git commit** to **flash** to **test execution** to **report**.

```
Developer commit (GitHub)
        │
        ▼
 GitHub Actions CI (cloud, free)
   DBC validate ─ CAPL lint ─ pytest (mocked CAN)
        │
        ▼  workflow_dispatch (auto-triggered when CI passes)
 Lab runner (self-hosted Windows, CANoe + vTESTstudio)
   pull repo ─ bench pre-flight ─ FLASH ECU (UDS + version read-back)
   ─ DBC check-in ─ CAPL build ─ vTESTstudio execution ─ export reports
        │
        ▼
 Report ingestion (normalize CANoe/vTESTstudio output → results DB)
        │
        ▼
 Dashboard (run history, trends, regressions, drill-down, native report links)
```

## Repository layout

| Path | Purpose |
|---|---|
| `.github/workflows/` | `ci.yml` (cloud CI) and `lab.yml` (lab runner dispatch) |
| `dbc/` | DBC source definitions (JSON) + build/validate scripts |
| `capl/` | CANoe test CAPL modules (compiled on the lab runner) |
| `scripts/capl/` | CAPL utilities: UDS flash script, bench pre-flight, version read-back |
| `vtest/` | vTESTstudio test modules, test lists and test configurations |
| `config/` | CANoe `.cfg` configurations and bench profile files |
| `firmware/` | ECU firmware binaries + flash descriptions (`.hex`/`.s19` + `.cdd`/`.odx`) |
| `python/` | pytest unit tests + mocked-CAN tests (run in cloud CI, no hardware) |
| `scripts/lab/` | Windows lab runner entrypoint and helper utilities |
| `scripts/ingestion/` | Report parser + REST API server (results store) |
| `dashboard/` | Test-report dashboard web application |
| `docs/` | Setup guide, flash procedure notes, troubleshooting |

## Pipeline stages

### Stage 1 — Cloud CI (every push/PR)
- DBC validation (`dbc/validate_dbc.py`): catches `BA_` ordering errors, protected Vector attributes, and syntax errors before they reach CANoe.
- Python linting + `pytest` on mocked-CAN tests (no hardware needed).
- On green, automatically triggers `lab.yml`.

### Stage 2 — Lab runner (self-hosted Windows runner)
1. **Bench pre-flight**: verifies HIL bench readiness (powers, no active DTCs, CAN bus alive).
2. **Flash ECU** (`scripts/capl/FlashEcu.can`): UDS flash via `0x10/0x27/0x34/0x36/0x37/0x11`, then reads back software version (`0xF195`) and compares against the expected version derived from the commit. Aborts if the ECU did not take the new software.
3. **DBC check-in**: rebuilds the DBC, loads it into CANoe, verifies signals against known (raw, physical) pairs.
4. **CAPL build**: compiles test CAPL via `CANAStudios` command line.
5. **vTESTstudio execution**: runs the test list against the HIL bench via `vTESTstudioCmd`, exporting native HTML/XML results.
6. **Post-run teardown**: restores the baseline firmware (golden image) and powers down the bench so it is never left in a failed state.

### Stage 3 — Report ingestion
`scripts/ingestion/` parses vTESTstudio XML results and CANoe reports into a normalized JSON schema (test case, verdict, duration, firmware version, commit SHA, runner ID, timestamp) and stores them in a local SQLite database served by a lightweight REST API.

### Stage 4 — Dashboard
`dashboard/` is a web app showing build history, pass-rate trends, regression flags, per-case drill-down and links to the native CANoe/vTESTstudio report artifacts.

## Quick start (lab PC)

See [`docs/lab-runner-setup.md`](docs/lab-runner-setup.md) — one-page install guide for the Windows self-hosted runner.

## Cost
GitHub free tier + your existing lab PC = effectively zero incremental cost for this POC.
