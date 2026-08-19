# Lab Runner Setup (Windows, one page)

This guide turns your Windows lab PC (with CANoe and vTESTstudio installed) into the
self-hosted runner that physically flashes the ECU, executes tests on the HIL bench,
and stores the results. Total setup time: ~30 minutes.

## 1. Prerequisites

| Item | Requirement |
|---|---|
| OS | Windows 10/11, 64-bit |
| Tools | CANoe (with command-line tools on `PATH`), vTESTstudio (optional, CANoe fallback works) |
| Python | Python 3.11+ with `python-can` and Vector CAN drivers (`python -m pip install python-can`) |
| Network | The PC must stay on and connected (GitHub Actions polls it) |

Verify command-line tools are reachable:

```powershell
where.exe CANoeCmd        # should print a path
where.exe CANAStudios     # should print a path
python -c "import can; print(can.__version__)"
```

## 2. Install the GitHub Actions runner

```powershell
# Create a folder and download the runner zip from:
#   https://github.com/actions/runner/releases (latest win-x64 actions-runner)
mkdir C:\actions-runner && cd C:\actions-runner
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory("$env:USERPROFILE\Downloads\actions-runner-win-x64-*.zip", ".")

# Configure with the registration token from your repo:
#   Repo -> Settings -> Actions -> Runners -> New self-hosted runner -> Windows
.\config.cmd --url https://github.com/<YOUR_ORG>/ecu-hil-testing-pipeline --token <TOKEN>

# Register as a Windows service so it survives reboots
.\svc install
.\svc start
```

When registering, the runner asks for **labels** — enter `hil-bench` (this is what
`lab.yml` targets).

## 3. Repository secrets

The CI workflow triggers the lab run automatically via `workflow_dispatch`, which
requires a personal access token (PAT) with `repo` scope:

1. GitHub -> Settings -> Developer settings -> Personal access tokens -> Fine-grained
   (or classic) PAT, `repo` scope.
2. Repo -> Settings -> Secrets and variables -> Actions -> **New repository secret**:
   - Name: `LAB_TRIGGER_TOKEN` — the PAT.

## 4. Bench-specific configuration

Adapt these three files to your hardware before the first run:

| File | What to change |
|---|---|
| `config/bench_profile.json` | PSU addresses/SCPI endpoints, bus-probe message ID, CANoe requirement |
| `config/flash_config.json` | ECU CAN addresses (`ecu_tx_id`/`ecu_rx_id`), bitrate, security level, and the `compute_key()` Seed&Key algorithm in `scripts/lab/flash_ecu.py` |
| `config/canoe_config.cfg` | Replace the placeholder with your real CANoe configuration saved from the GUI |

Also put a **golden firmware** binary at `firmware/golden/firmware.bin` so the
post-run teardown can always restore a known-good state.

## 5. First run

Push a change to `main` (or click Actions -> *HIL Lab Run* -> *Run workflow*). The
pipeline on the lab PC will: pre-flight check -> flash & verify -> DBC check-in ->
CAPL build -> vTESTstudio run -> ingest results -> teardown. The native HTML/XML
reports are uploaded as GitHub Actions artifacts, and the normalized results appear
on the dashboard once `server.py` is running:

```powershell
python scripts/ingestion/server.py --db out/results.db --port 8765
# Open dashboard/index.html in a browser, set API base URL to http://<lab-pc>:8765
```

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Lab job stays `queued` forever | Runner offline / not registered with `hil-bench` label | `.\svc status`; re-register if needed |
| Flash fails with negative response | Wrong address, session, or Seed&Key | Check `config/flash_config.json` + `compute_key()`; view CANoe trace |
| `vTESTstudioCmd not found` | vTESTstudio not on PATH | Add its install dir to `PATH` or use CANoe fallback (auto) |
| Runner job skipped, CI still green | By design — CI never blocks on lab availability | Register the runner to enable it |
