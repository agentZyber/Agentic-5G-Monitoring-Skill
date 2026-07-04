# CORE Lab · NCSRD — Adversarial War‑Game: Setup & Run Tutorial

A hands‑on guide to setting up and running the red/blue adversarial‑simulation framework — in
**simulation** (no hardware) and against the **real testbed** (live 5G RF, and a real eBPF‑backdoor
hunt on an isolated VM). Every command is copy‑paste. Everything is sovereign (local models),
human‑in‑the‑loop, reversible, and non‑kinetic.

> **Safety first.** The real red side runs **only** on a dedicated, isolated VM you provision for it.
> Artifacts are contained, benign‑payload signatures and are torn down by a single `clean`. Never run
> the red harness on a production host. Credentials are passed via environment variables — never
> written into files or committed.

---

## 0. What you're running

| Layer | What it is | Hardware needed |
|---|---|---|
| **Simulated war‑game** | Red vs Blue over an auditable event‑log world; programmatic judge; leaderboard; doctrine (human‑approval) gate | none |
| **Interactive console** | Slick ops‑console dashboard (battlespace graph, turn playback, leaderboard) | none |
| **Real RF red/blue** | Red degrades the **live 5G network** (Amarisoft `cell_gain`); Blue diagnoses | Amarisoft testbed + a GPU/Ollama host |
| **Real host cyber red/blue** | Red deploys **real eBPF backdoors** on an isolated VM; Blue (`bpf-hunt` agent) detects them | one isolated Linux VM |

Package: **`corelab`** (in `src/corelab`). Scripts live in `training/`. Docs: this file +
[`WARGAME_POC.md`](WARGAME_POC.md) (design) + [`SIX_G_USE_CASES.md`](SIX_G_USE_CASES.md).

---

## 1. Prerequisites

**Controller machine** (your laptop / the box you drive demos from):
- Python 3.11+ and the repo's virtualenv (`.venv`).
- `sshpass`, `ssh`, `rsync` (for the remote/real parts). macOS: `brew install sshpass hudochenkov/sshpass/sshpass`.
- `python3 -m http.server` (built‑in) to serve the dashboard.

**For a sovereign LLM defender/attacker** (optional): [Ollama](https://ollama.com) running locally or on a
GPU host, with a tool‑calling model (e.g. `qwen2.5:14b`, `qwen3:8b`).

**For the real host‑cyber red side:** one **isolated** Ubuntu 22.04/24.04 VM (kernel ≥ 5.15) with
`bpftool`, `bpftrace`, and passwordless `sudo`. (Install: `sudo apt install linux-tools-$(uname -r) bpftrace`.)

**For the real RF red/blue:** the Amarisoft callbox + a host running Ollama (see §7).

---

## 2. Install & verify

```bash
cd Agentic-5G-Monitoring-Skill
python3 -m venv .venv && .venv/bin/pip install -U pip
.venv/bin/pip install pytest requests websockets          # + torch/trl/peft only if you train

# run the test suite — should be all green
.venv/bin/python -m pytest tests/ -q                       # -> 274 passed

# 30-second smoke test (fully simulated, no hardware, no LLM):
PYTHONPATH=src .venv/bin/python training/wargame_guided.py --auto
```

`tests/conftest.py` puts `src/` on the path for pytest; **scripts** need `PYTHONPATH=src` (shown in
every command below).

---

## 3. The simulated war‑game (no hardware)

### 3.1 Guided, step‑by‑step walkthrough — for the live audit
```bash
PYTHONPATH=src .venv/bin/python training/wargame_guided.py            # all scenarios, Enter to advance
PYTHONPATH=src .venv/bin/python training/wargame_guided.py --auto     # no pauses (quick/CI)
PYTHONPATH=src .venv/bin/python training/wargame_guided.py --live-approval   # YOU approve/deny each countermeasure
PYTHONPATH=src .venv/bin/python training/wargame_guided.py --adaptive        # CAM-style adversary that escalates
PYTHONPATH=src .venv/bin/python training/wargame_guided.py contested-tactical-network   # one scenario
```
Each turn shows **RED move → BLUE move → mission status**; then a **verdict + scorecard**
(availability · time‑to‑detect · threats neutralised · unauthorized actions) and the **doctrine
decision log**. `--live-approval` makes *you* the human‑in‑the‑loop.

### 3.2 The scenarios
| id | what it models |
|---|---|
| `contested-tactical-network` | mission slice under jamming / signaling flood / node intrusion |
| `isr-sensor-contested` | ISR sensor feed on a backhaul the adversary disrupts/spoofs |
| `logistics-under-disruption` | convoy‑C2 / supply‑tracking network under disruption |

### 3.3 The interactive console (Palantir‑style dashboard)
```bash
# 1) generate the evidence (all scenarios; add OLLAMA_MODEL to include an LLM defender — see 3.4)
PYTHONPATH=src WARGAME_SCENARIO=all WARGAME_OUT=wargame_evidence \
  .venv/bin/python training/wargame_demo.py

# 2) render the slick console from the results
PYTHONPATH=src WARGAME_RESULTS=wargame_evidence/results.json \
  WARGAME_HTML=wargame_evidence/console.html \
  .venv/bin/python training/wargame_dashboard.py

# 3) serve it locally, then open http://127.0.0.1:8799/console.html
python3 -m http.server 8799 --directory wargame_evidence
```
The console has a **run selector** (every scenario × adversary × defender), a **▶ PLAY** button that
auto‑advances turns and animates the **battlespace node‑graph**, a **turn scrubber**, the **defender
leaderboard**, and the **human‑control decision log**. `wargame_evidence/` also gets `run_report.md`
and `results.json` (reproducible, state‑judged).

**RF red/blue is visualised too.** `WARGAME_SCENARIO=all` also emits the RF episode
(`rf-contested-cell`) — select it in the run selector to get a **radio battlespace**: a CELL node that
reddens when Red cuts DL power, and UE nodes coloured by **CQI**. Press **▶ PLAY** to watch the
weak‑link UE degrade first (the real *differential‑degradation* finding), Blue detect and attribute the
cause, and the CQIs recover on the approved power restore. Seeded from real testbed captures; pass a
live `sampler` to `rf_episode()` to drive it from the actual Amarisoft gNB.

### 3.4 Add a sovereign LLM defender
On a host with Ollama, set the model — the demo adds a `blue:agent` row to the leaderboard:
```bash
OLLAMA_MODEL=qwen2.5:14b OLLAMA_HOST=http://localhost:11434 \
  WARGAME_SCENARIO=all PYTHONPATH=src .venv/bin/python training/wargame_demo.py
```

---

## 4. REAL host‑cyber red/blue — the eBPF‑backdoor hunt

This is **not** simulated: Red loads real eBPF programs into a live kernel; Blue detects them with
real `bpftool`/`ss` telemetry. Runs on an **isolated VM only**.

### 4.1 Set up the RED side on the isolated VM (one time)
```bash
# copy the red harness to the VM (replace host/user)
export SSHPASS='<VM_PASSWORD>'
sshpass -e scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  -o PreferredAuthentications=password -o PubkeyAuthentication=no \
  training/red_harness.sh localadmin@10.160.101.128:/home/localadmin/red_harness.sh

sshpass -e ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  localadmin@10.160.101.128 'chmod +x red_harness.sh; ./red_harness.sh status'
```
Red console (run **on the VM**, or remotely):
```bash
./red_harness.sh deploy all       # stand up all techniques
./red_harness.sh deploy hide       # just the getdents64 file-hiding eBPF hook
./red_harness.sh deploy net        # just the tcp_sendmsg network-C2 eBPF hook
./red_harness.sh deploy port       # just the :4444 backdoor listener
./red_harness.sh status            # what's live
./red_harness.sh clean             # tear it ALL down (reversible)
```

### 4.2 Run the BLUE agent (one command, full cycle) — from the controller
```bash
HOSTSENSOR_PASS='<VM_PASSWORD>' PYTHONPATH=src \
  .venv/bin/python training/bpf_hunt_vm.py 10.160.101.128 localadmin
```
This: cleans the VM → takes a **clean baseline** → RED deploys all → the **`bpf-hunt` agent detects**
them over SSH (getdents hook, tcp hook, :4444 port) → **cleans up** → confirms restore. Expected:
```
[3] BLUE — the bpf-hunt agent detects them
    threat_detected=True · ebpf=EBPF BACKDOOR SUSPECTED
    ->  SUSPICIOUS eBPF: ...sys_enter_getdents64 (tracepoint) hooks ['getdents']
    ->  SUSPICIOUS eBPF: tcp_sendmsg (kprobe) hooks ['tcp','sendmsg']
    ->  NEW LISTENER:    tcp 0.0.0.0:4444
```

### 4.3 Self‑contained variant (Blue plants + detects + cleans, no red harness)
```bash
HOSTSENSOR_PASS='<VM_PASSWORD>' PYTHONPATH=src \
  .venv/bin/python training/bpf_hunt_live.py 10.160.101.128 localadmin
```

### 4.4 Manual walkthrough (understand each stage)
```bash
export SSHPASS='<VM_PASSWORD>'
SSH="sshpass -e ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o PreferredAuthentications=password -o PubkeyAuthentication=no localadmin@10.160.101.128"
$SSH 'sudo bpftool prog list | grep -cE "^[0-9]+:"'         # baseline count
$SSH './red_harness.sh deploy hide'                          # plant a real getdents64 hook
$SSH 'sudo bpftool prog list | grep getdents'               # blue sees it
$SSH './red_harness.sh clean'                                # remove it
```

### 4.5 Fuller functional backdoor (optional, consent‑gated)
For an actual file‑hiding rootkit (not just the signature), install a toolchain on the VM and build a
**known public** research tool:
```bash
$SSH 'sudo apt-get update && sudo apt-get install -y clang llvm libbpf-dev make linux-headers-$(uname -r)'
# then clone + build e.g. bad-bpf / boopkit on the VM (public detection-research tools)
```
This deploys real malware in the sandbox — do it only on the isolated VM, and clean up after.

---

## 5. REAL RF red/blue (Amarisoft 5G) — brief

Red degrades the **live** radio; Blue (an LLM agent) diagnoses whether it's UE‑specific or cell‑wide.
Runs on the GPU/Ollama host with access to the callbox. Three independent restore paths protect the
live network; the fault is a few‑dB `cell_gain` cut, auto‑restored.
```bash
AMARISOFT_WS_URL=ws://<callbox>:9001/ OLLAMA_MODEL=qwen2.5:14b \
  PYTHONPATH=src python training/degrade_capture.py     # gentle fault → capture → restore
PYTHONPATH=src python training/batch_capture.py         # read-only over a naturally-degraded net
```

---

## 6. Extending the framework

**Add a war‑game scenario** — edit `src/corelab/wargame/scenario.py`: add a `_my_scenario()` returning
a `WarGameScenario` and include it in `SCENARIOS`. It auto‑appears in the guided demo, console and tests.

**Add a red technique** — add a `deploy` case in `training/red_harness.sh` (a systemd‑run unit or file)
plus its `clean`.

**Add a blue detector** — add a `@reg.tool` in `src/corelab/packs/bpf_hunt/__init__.py` that reads the
`HostSensor` and returns findings.

**Plug in NCSRD assets (P4)** — `corelab.wargame.integrations`:
- `ExternalBenchController(decide_fn)` — drop NCSRD's real HW red/blue bench in as a `Controller`.
- `AdaptiveRedController(tactics)` — the Context Agility Manager (sense→compare→adapt) as an adversary.
- `HashChainAudit` — tamper‑evident, hash‑chained audit of doctrine decisions (Besu/PQC stand‑in).

---

## 7. Safety, containment & audit evidence

- **Isolation** — the real red side runs only on the dedicated VM; the RF fault is bounded + auto‑restored.
- **Reversibility** — `./red_harness.sh clean` and the runners restore baseline; verified each run.
- **Human‑in‑the‑loop** — every consequential blue action passes the doctrine (approval) gate and is logged.
- **Sovereign & provenanced** — local models, seeded reproducibility, programmatic (state‑based) judging.
- **Evidence pack** — `wargame_evidence/{console.html, run_report.md, results.json}` + the live
  detection transcripts are the artefacts the audit reviews.

---

## 8. Cheat‑sheet

```bash
# simulated
PYTHONPATH=src python training/wargame_guided.py [--auto|--live-approval|--adaptive] [scenario]
PYTHONPATH=src WARGAME_SCENARIO=all python training/wargame_demo.py            # -> wargame_evidence/
PYTHONPATH=src python training/wargame_dashboard.py                             # -> console.html
python3 -m http.server 8799 --directory wargame_evidence                        # open :8799/console.html

# real host-cyber (isolated VM)
sshpass -e scp ... training/red_harness.sh user@vm:~/                           # install red side
./red_harness.sh {deploy [hide|net|port|all]|clean|status}                      # on the VM
HOSTSENSOR_PASS=... PYTHONPATH=src python training/bpf_hunt_vm.py <vm> <user>    # blue vs red, full cycle

# real RF (Amarisoft + Ollama host)
AMARISOFT_WS_URL=ws://<box>:9001/ OLLAMA_MODEL=... PYTHONPATH=src python training/degrade_capture.py

# tests
.venv/bin/python -m pytest tests/ -q
```

## 9. Troubleshooting
- **`sshpass: ... askpass`** — use `export SSHPASS=...; sshpass -e ssh ...` (env form), not `-p`.
- **`bpftool ... Operation not permitted`** — needs root; the connector uses `sudo` (passwordless sudo required on the target).
- **Blue says `clean` when red is up** — the planted process died before detection; the harness uses
  `systemd-run` so it survives across SSH sessions (don't background bpftrace by hand).
- **`ModuleNotFoundError: corelab`** — prefix scripts with `PYTHONPATH=src`.
- **Ollama not used** — the demo falls back to scripted baselines and prints why; check `OLLAMA_HOST`.
