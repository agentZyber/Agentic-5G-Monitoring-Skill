"""War-Game Mission Control — a local web panel to run every war-game test/demo with one click.

Each registered test is a subprocess; the browser streams its stdout live over Server-Sent Events.
Hardware-free tests (unit suite, simulated scenarios, mock-defender proof, evidence pack) run as-is;
tests that need a host (the GPU box, the red VM, the Amarisoft testbed) are shown with a requirement
badge and run only when the matching credential/URL is in the environment. Localhost tool — it executes
whitelisted commands from a fixed registry, never arbitrary input.

    PYTHONPATH=src python training/wargame_control.py     # -> http://127.0.0.1:8800
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from corelab.wargame.campaign import build_theater, iter_campaign, wave_windows

ROOT = Path(__file__).resolve().parents[3]           # repo root (…/src/corelab/wargame/control.py)
PYEXE = sys.executable                                # the venv python running the server
_ANSI = re.compile(r"\x1b\[[0-9;]*m")

# --- host config (defaults known; secrets come from the environment, never hard-coded) ---
GPU_HOST = os.getenv("CORELAB_GPU_HOST", "localadmin@10.160.101.159")
GPU_DIR = os.getenv("CORELAB_GPU_DIR", "/home/localadmin/zt")
GPU_PY = os.getenv("CORELAB_GPU_PY", "/home/localadmin/zortenet-train/bin/python")
VM_HOST = os.getenv("CORELAB_VM_HOST", "10.160.101.128")
VM_USER = os.getenv("CORELAB_VM_USER", "localadmin")
_SSH = ["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=15", "-o", "PreferredAuthentications=password",
        "-o", "PubkeyAuthentication=no"]


def _ssh_argv(remote_script: str) -> List[str]:
    cmd = (f"cd {shlex.quote(GPU_DIR)} && PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True "
           f"{shlex.quote(GPU_PY)} -u {remote_script}")
    return ["sshpass", "-e", "ssh", *_SSH, GPU_HOST, cmd]


@dataclass
class ControlTest:
    id: str
    title: str
    group: str
    blurb: str
    argv: List[str]
    est: str = "~seconds"
    requires: Optional[str] = None          # None | "gpu" | "vm" | "amarisoft"
    # filled in by the registry builder:
    enabled: bool = True
    lock_hint: str = ""
    cmd: str = ""

    def public(self) -> Dict:
        d = asdict(self)
        d.pop("argv")
        return d


def _requirement(requires: Optional[str]) -> tuple[bool, str]:
    if requires is None:
        return True, ""
    if requires == "gpu":
        ok = bool(os.getenv("SSHPASS"))
        return ok, f"needs the GPU box {GPU_HOST} — set SSHPASS to enable (has 4-bit qwen3:8b)"
    if requires == "vm":
        ok = bool(os.getenv("HOSTSENSOR_PASS"))
        return ok, f"needs the isolated red VM {VM_HOST} — set HOSTSENSOR_PASS to enable"
    if requires == "amarisoft":
        ok = bool(os.getenv("AMARISOFT_WS_URL"))
        return ok, "needs the Amarisoft 5G testbed + a UE — set AMARISOFT_WS_URL to enable"
    return True, ""


def build_registry() -> List[ControlTest]:
    g = "training/wargame_guided.py"
    tests = [
        # ---- unit test suite (local) ----
        ControlTest("pytest-wargame", "War-game unit tests", "Test suite",
                    "pytest over the war-game engine, judge, guardrails, doctrine gate, integrations, "
                    "RF and bpf-hunt — the green safety net.",
                    [PYEXE, "-m", "pytest", "tests/test_wargame.py", "tests/test_wargame_integrations.py",
                     "tests/test_rf.py", "tests/test_bpf_hunt.py", "-q"], est="~2 s"),
        # ---- simulated war-game (local, no hardware) ----
        ControlTest("scenario-tactical", "Scenario · contested tactical network", "Simulated war-game",
                    "Red degrades a mission slice (jam / flood / intrude); Blue detects and applies an "
                    "approved countermeasure. Turn-by-turn, with the doctrine gate.",
                    [PYEXE, g, "--auto", "contested-tactical-network"], est="~1 s"),
        ControlTest("scenario-isr", "Scenario · ISR sensor contested", "Simulated war-game",
                    "An ISR sensor feed under contested backhaul — keep it available and trustworthy.",
                    [PYEXE, g, "--auto", "isr-sensor-contested"], est="~1 s"),
        ControlTest("scenario-logistics", "Scenario · logistics under disruption", "Simulated war-game",
                    "A logistics coordination network under jamming / flooding / spoofing.",
                    [PYEXE, g, "--auto", "logistics-under-disruption"], est="~1 s"),
        ControlTest("campaign-all", "Campaign · all scenarios", "Simulated war-game",
                    "Runs all three scenarios back-to-back and prints a campaign summary.",
                    [PYEXE, g, "--auto"], est="~3 s"),
        ControlTest("campaign-adaptive", "Campaign · CAM adaptive adversary", "Simulated war-game",
                    "Same scenarios but Red is the Context-Agility-Manager adversary that escalates when "
                    "the defender copes and holds when it hurts.",
                    [PYEXE, g, "--auto", "--adaptive"], est="~3 s"),
        ControlTest("mock-9of9", "Harness proof · stateless defender 9/9", "Simulated war-game",
                    "A single-step, model-free policy plays every scenario × adversary through the real "
                    "engine. Proves the fixed harness is winnable (incl. multi-vector) with no GPU.",
                    [PYEXE, "training/wargame_mock_defender.py"], est="~2 s"),
        ControlTest("evidence-pack", "Evidence pack + leaderboard", "Simulated war-game",
                    "Runs the scripted matchups, ranks defenders on the leaderboard, and writes "
                    "wargame_evidence/{dashboard.html, run_report.md, results.json}.",
                    [PYEXE, "training/wargame_demo.py"], est="~2 s"),
        ControlTest("theater-campaign", "Theater campaign · 28 nodes, 80 turns", "Simulated war-game",
                    "Large-scale, paced console run (~30 s): a 28-node battlespace under sustained "
                    "multi-wave assault (215 threats). The live map view is the visual version ↗.",
                    [PYEXE, "training/wargame_campaign.py"], est="~30 s"),
        # ---- sovereign LLM defender (GPU box) ----
        ControlTest("llm-base", "Sovereign base defender · 9/9", "Sovereign LLM defender",
                    "Base qwen3:8b (no adapter) plays all 9 games under the crisp doctrine prompt — the "
                    "corrected result: it wins the benchmark without fine-tuning.",
                    _ssh_argv("base_prompt_test.py"), est="~3 min", requires="gpu"),
        ControlTest("llm-adapter", "Fine-tuned adapter · base vs FT eval", "Sovereign LLM defender",
                    "Loads Qwen3-8B + the LoRA adapter and scores base vs fine-tuned across all 9 games "
                    "(rewrites g2_wargame.json).",
                    _ssh_argv("g2_wargame_eval.py"), est="~8 min", requires="gpu"),
        ControlTest("llm-trace", "Fine-tuned adapter · per-turn trace", "Sovereign LLM defender",
                    "Attaches the adapter and traces one multi-vector game turn-by-turn (observation → "
                    "raw output → parsed tool call) — the diagnostic view.",
                    _ssh_argv("trace_v2.py"), est="~3 min", requires="gpu"),
        # ---- real testbed ----
        ControlTest("bpf-hunt-vm", "Real host-cyber · eBPF backdoor hunt", "Real testbed",
                    "Red plants contained eBPF-backdoor signatures on the isolated VM; the Blue bpf-hunt "
                    "agent detects them over SSH vs a trusted baseline, then cleans up.",
                    [PYEXE, "training/bpf_hunt_vm.py", VM_HOST, VM_USER], est="~1-2 min", requires="vm"),
        ControlTest("rf-live", "Real RF · red/blue vs Amarisoft 5G", "Real testbed",
                    "Red gently cuts real cell power (cell_gain); Blue reads live CQI degradation and the "
                    "cell is auto-restored. Safety-gated; needs a UE attached.",
                    [PYEXE, "training/rf_live.py"], est="~1 min", requires="amarisoft"),
    ]
    for t in tests:
        t.enabled, t.lock_hint = _requirement(t.requires)
        t.cmd = shlex.join(t.argv)
    return tests


# --- one active run at a time (simple, predictable for a demo console) ---
_STATE: Dict[str, object] = {"proc": None, "id": None}
_LOCK = threading.Lock()


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _run_stream(test: ControlTest):
    env = dict(os.environ)
    env["PYTHONPATH"] = "src" + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONUNBUFFERED"] = "1"
    with _LOCK:
        if _STATE["proc"] is not None and _STATE["proc"].poll() is None:
            yield _sse("error", {"message": "another test is already running"})
            yield _sse("done", {"code": -1})
            return
        try:
            proc = subprocess.Popen(test.argv, cwd=str(ROOT), env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, bufsize=1)
        except FileNotFoundError as exc:
            yield _sse("error", {"message": f"cannot launch: {exc}"})
            yield _sse("done", {"code": -1})
            return
        _STATE["proc"], _STATE["id"] = proc, test.id
    start = time.monotonic()
    yield _sse("start", {"id": test.id, "title": test.title, "cmd": test.cmd})
    try:
        for line in proc.stdout:                          # blocking read (runs in threadpool)
            yield _sse("line", {"text": _ANSI.sub("", line.rstrip("\n"))})
        code = proc.wait()
        yield _sse("done", {"code": code, "secs": round(time.monotonic() - start, 1)})
    finally:
        if proc.poll() is None:                            # client disconnected → don't orphan it
            proc.terminate()
        with _LOCK:
            if _STATE["proc"] is proc:
                _STATE["proc"], _STATE["id"] = None, None


def build_control_app() -> FastAPI:
    app = FastAPI(title="CORE Lab · NCSRD — War-Game Mission Control")
    registry = {t.id: t for t in build_registry()}

    @app.get("/", response_class=HTMLResponse)
    def index():
        tests = [t.public() for t in registry.values()]
        return HTMLResponse(_page(tests))

    @app.get("/api/tests")
    def api_tests():
        return JSONResponse([t.public() for t in registry.values()])

    @app.get("/api/run/{test_id}")
    def api_run(test_id: str):
        test = registry.get(test_id)
        if test is None:
            return JSONResponse({"error": f"unknown test '{test_id}'"}, status_code=404)
        if not test.enabled:
            return JSONResponse({"error": f"locked: {test.lock_hint}"}, status_code=409)
        return StreamingResponse(_run_stream(test), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/map", response_class=HTMLResponse)
    def battlespace_map():
        nodes, edges = build_theater()
        return HTMLResponse(_map_page(nodes, edges))

    @app.get("/api/campaign/stream")
    def api_campaign(turns: int = 80, pace: float = 0.34, seed: int = 11):
        turns = max(20, min(160, turns))
        pace = max(0.0, min(1.5, pace))

        def gen():
            yield _sse("meta", {"turns": turns, "pace": pace})
            for frame in iter_campaign(turns, seed):
                yield _sse("turn", frame)
                if pace:
                    time.sleep(pace)
            yield _sse("end", {"turns": turns})

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/api/stop")
    def api_stop():
        with _LOCK:
            proc, tid = _STATE.get("proc"), _STATE.get("id")
            if proc is not None and proc.poll() is None:
                proc.terminate()
                return {"stopped": tid}
        return {"stopped": None}

    return app


# ---------------------------------------------------------------------------------------------------
_PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CORE Lab · NCSRD — War-Game Mission Control</title>
<style>
:root{--am:#ffb020;--bg:#070b12;--bl:#4aa8ff;--cy:#3ad0d8;--dim:#3f5169;--gn:#35d69f;
--ink:#dbe6f2;--line:#182335;--mut:#6d829e;--panel:#0d131e;--rd:#ff4d5e;
--mono:ui-monospace,'SFMono-Regular','JetBrains Mono',Menlo,Consolas,monospace}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(1200px 700px at 70% -10%,#0d1830 0,var(--bg) 55%);
color:var(--ink);font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{display:flex;align-items:center;gap:14px;padding:16px 22px;border-bottom:1px solid var(--line);
position:sticky;top:0;background:rgba(7,11,18,.86);backdrop-filter:blur(8px);z-index:5}
.brand{font-weight:800;letter-spacing:.5px}.brand .am{color:var(--am)}
.brand .dot{color:var(--dim);margin:0 6px}
.sub{color:var(--mut);font-size:12px}
.spacer{flex:1}
.legend{display:flex;gap:12px;font-size:11px;color:var(--mut)}
.legend b{font-weight:600}
main{padding:20px 22px 340px;max-width:1180px;margin:0 auto}
h2{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--mut);
margin:26px 0 12px;font-weight:700}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}
.card{background:linear-gradient(180deg,var(--panel),#0a101a);border:1px solid var(--line);
border-radius:12px;padding:15px 16px;display:flex;flex-direction:column;gap:9px;position:relative}
.card.run{border-color:var(--am);box-shadow:0 0 0 1px var(--am),0 8px 30px -12px var(--am)}
.card.pass{border-color:var(--gn)}.card.fail{border-color:var(--rd)}
.card.locked{opacity:.72}
.ct{display:flex;align-items:center;gap:8px}
.dot{width:9px;height:9px;border-radius:50%;background:var(--dim);flex:none}
.card.run .dot{background:var(--am);animation:pulse 1s infinite}
.card.pass .dot{background:var(--gn)}.card.fail .dot{background:var(--rd)}
@keyframes pulse{50%{opacity:.35}}
.title{font-weight:650}
.blurb{color:var(--mut);font-size:12.5px;min-height:34px}
.foot{display:flex;align-items:center;gap:10px;margin-top:2px}
.est{color:var(--dim);font-size:11px;font-family:var(--mono)}
.spc{flex:1}
button{font:inherit;cursor:pointer;border-radius:8px;border:1px solid var(--line);
background:#12203a;color:var(--ink);padding:6px 14px;font-size:13px;font-weight:600}
button:hover:not(:disabled){border-color:var(--bl)}
button:disabled{opacity:.4;cursor:not-allowed}
.run-btn{background:var(--am);color:#06101f;border-color:var(--am)}
.badge{font-size:10.5px;font-family:var(--mono);padding:2px 7px;border-radius:20px;
border:1px solid var(--line);color:var(--mut)}
.badge.hw{color:var(--am);border-color:#3a3116}
.lock{font-size:11px;color:var(--mut);font-family:var(--mono)}
.copy{background:transparent;border:1px dashed var(--line);color:var(--mut);padding:5px 10px;font-size:11px}
/* console */
#console{position:fixed;left:0;right:0;bottom:0;height:300px;background:#05090f;
border-top:1px solid var(--line);display:flex;flex-direction:column;z-index:6}
.cbar{display:flex;align-items:center;gap:12px;padding:8px 16px;border-bottom:1px solid var(--line)}
.cbar .ctitle{font-weight:650}.cbar .cstat{font-family:var(--mono);font-size:12px}
.cstat.run{color:var(--am)}.cstat.pass{color:var(--gn)}.cstat.fail{color:var(--rd)}
.cbar .cmd{font-family:var(--mono);font-size:11px;color:var(--dim);overflow:hidden;
white-space:nowrap;text-overflow:ellipsis;flex:1}
#log{flex:1;overflow:auto;margin:0;padding:10px 16px;font-family:var(--mono);font-size:12px;
line-height:1.55;white-space:pre-wrap;word-break:break-word}
#log .gn{color:var(--gn)}#log .rd{color:var(--rd)}#log .am{color:var(--am)}
#log .cy{color:var(--cy)}#log .mut{color:var(--mut)}#log .bl{color:var(--bl)}
.empty{color:var(--dim);padding:20px 16px;font-family:var(--mono)}
.hero{display:flex;align-items:center;gap:16px;margin:20px 22px 0;max-width:1180px;
text-decoration:none;color:inherit;border:1px solid #2a3a24;border-radius:14px;padding:16px 20px;
background:linear-gradient(110deg,rgba(53,214,159,.10),rgba(255,176,32,.06) 60%,transparent),var(--panel)}
.hero:hover{border-color:var(--gn);box-shadow:0 10px 40px -18px var(--gn)}
.hero .hk{font-weight:800;letter-spacing:.06em;color:var(--gn)}
.hero .hd{color:var(--mut);font-size:12.5px;margin-top:3px}
.hero .go{margin-left:auto;font-weight:700;color:var(--am);white-space:nowrap}
.hero .pl{font-family:var(--mono);font-size:11px;color:var(--dim);margin-top:2px}
@media(min-width:640px){main{margin-left:auto;margin-right:auto}}
</style></head><body>
<header>
  <div class="brand">CORE&nbsp;LAB<span class="dot">·</span><span class="am">NCSRD</span></div>
  <div class="sub">War-Game Mission Control — run every test / demo, live</div>
  <div class="spacer"></div>
  <div class="legend"><span><b style="color:var(--gn)">●</b> pass</span>
    <span><b style="color:var(--rd)">●</b> fail</span>
    <span><b style="color:var(--am)">●</b> running</span>
    <span><b style="color:var(--am)">HW</b> needs host</span></div>
</header>
<a class="hero" href="/map" target="_blank">
  <div><div class="hk">◉ THEATER BATTLESPACE — LIVE MAP</div>
    <div class="hd">28-node battlespace under sustained multi-vector assault — watch it evolve over ~30 s</div>
    <div class="pl">215 threats · 80 turns · availability dips & recovers · interactive timeline</div></div>
  <div class="go">Open the map ↗</div>
</a>
<main id="main"></main>
<div id="console">
  <div class="cbar"><span class="ctitle" id="cTitle">Output console</span>
    <span class="cstat" id="cStat">idle</span>
    <span class="cmd" id="cCmd"></span>
    <button id="stopBtn" disabled>■ Stop</button>
    <button id="clearBtn">Clear</button></div>
  <pre id="log"><div class="empty">Select a test above and press Run — output streams here live.</div></pre>
</div>
<script>
const TESTS = __TESTS__;
const main = document.getElementById('main'), logEl = document.getElementById('log');
const cTitle = document.getElementById('cTitle'), cStat = document.getElementById('cStat');
const cCmd = document.getElementById('cCmd'), stopBtn = document.getElementById('stopBtn');
let es = null, activeCard = null;

const groups = [...new Set(TESTS.map(t => t.group))];
for (const grp of groups) {
  const h = document.createElement('h2'); h.textContent = grp; main.appendChild(h);
  const g = document.createElement('div'); g.className = 'grid';
  for (const t of TESTS.filter(x => x.group === grp)) g.appendChild(card(t));
  main.appendChild(g);
}

function card(t){
  const el = document.createElement('div'); el.className = 'card' + (t.enabled ? '' : ' locked');
  el.id = 'card-' + t.id;
  const hw = t.requires ? `<span class="badge hw">HW · ${t.requires}</span>` : '';
  el.innerHTML = `<div class="ct"><span class="dot"></span><span class="title">${t.title}</span></div>
    <div class="blurb">${t.blurb}</div>
    <div class="foot"><span class="est">${t.est}</span>${hw}<span class="spc"></span></div>`;
  const foot = el.querySelector('.foot');
  if (t.enabled) {
    const b = document.createElement('button'); b.className = 'run-btn'; b.textContent = '▶ Run';
    b.onclick = () => run(t, el); foot.appendChild(b);
  } else {
    const lock = document.createElement('div'); lock.className = 'lock'; lock.textContent = '🔒 ' + t.lock_hint;
    el.querySelector('.blurb').after(lock);
    const c = document.createElement('button'); c.className = 'copy'; c.textContent = '⧉ copy command';
    c.onclick = () => navigator.clipboard.writeText(t.cmd).then(()=>{c.textContent='copied';setTimeout(()=>c.textContent='⧉ copy command',1200)});
    foot.appendChild(c);
  }
  return el;
}

function classify(line){
  if (/MISSION HELD|HELD ✔| held|✔|passed|PASSED|APPROVED|HEALTHY|RESULT — \d+\/\d+ held|9\/9|win=100%/.test(line)) return 'gn';
  if (/MISSION LOST|LOST ✘|✘|FAILED|failed| error|Error|Traceback|DENIED|DEGRADED|ABORT/.test(line)) return 'rd';
  if (/DOCTRINE|GATE|⚠|WARN/.test(line)) return 'am';
  if (/SCENARIO|VERDICT|TURN \d|====|██|LEADERBOARD/.test(line)) return 'cy';
  if (/^\s*\[/.test(line)) return 'mut';
  return '';
}
function append(text){
  const div = document.createElement('div'); const cls = classify(text);
  if (cls) div.className = cls; div.textContent = text || ' ';
  logEl.appendChild(div); logEl.scrollTop = logEl.scrollHeight;
}
function setBusy(busy){ document.querySelectorAll('.run-btn').forEach(b => b.disabled = busy); stopBtn.disabled = !busy; }
function setStat(s, cls){ cStat.textContent = s; cStat.className = 'cstat ' + (cls||''); }

function run(t, el){
  if (es) es.close();
  if (activeCard) activeCard.classList.remove('run','pass','fail');
  activeCard = el; el.classList.remove('pass','fail'); el.classList.add('run');
  logEl.innerHTML = ''; cTitle.textContent = t.title; cCmd.textContent = t.cmd;
  setStat('running…','run'); setBusy(true);
  es = new EventSource('/api/run/' + t.id);
  es.addEventListener('start', e => append('$ ' + JSON.parse(e.data).cmd + '\n'));
  es.addEventListener('line', e => append(JSON.parse(e.data).text));
  es.addEventListener('error', e => { try{append('‼ ' + JSON.parse(e.data).message)}catch(_){} });
  es.addEventListener('done', e => {
    const d = JSON.parse(e.data); const ok = d.code === 0;
    append('\n— exit ' + d.code + (d.secs!=null ? ' · ' + d.secs + 's' : '') + ' —');
    setStat(ok ? 'passed' : 'failed (exit '+d.code+')', ok ? 'pass' : 'fail');
    el.classList.remove('run'); el.classList.add(ok ? 'pass' : 'fail');
    setBusy(false); es.close(); es = null;
  });
  es.onerror = () => { setStat('stream closed','fail'); setBusy(false); if(es){es.close();es=null;} el.classList.remove('run'); };
}
stopBtn.onclick = () => { fetch('/api/stop', {method:'POST'}); append('\n■ stop requested'); };
document.getElementById('clearBtn').onclick = () => { logEl.innerHTML=''; };
</script></body></html>"""


def _page(tests: List[Dict]) -> str:
    return _PAGE.replace("__TESTS__", json.dumps(tests))


# ---------------------------------------------------------------------------------------------------
_MAP_PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CORE Lab · NCSRD — Theater Battlespace</title>
<style>
:root{--am:#ffb020;--bg:#070b12;--bl:#4aa8ff;--cy:#3ad0d8;--dim:#3f5169;--gn:#35d69f;
--ink:#dbe6f2;--line:#182335;--mut:#6d829e;--panel:#0d131e;--rd:#ff4d5e;
--mono:ui-monospace,'SFMono-Regular','JetBrains Mono',Menlo,Consolas,monospace}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(1200px 700px at 72% -12%,#0d1830 0,var(--bg) 55%);
color:var(--ink);font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{display:flex;align-items:center;gap:14px;padding:12px 20px;border-bottom:1px solid var(--line);
flex-wrap:wrap}
.brand{font-weight:800;letter-spacing:.5px}.brand .am{color:var(--am)}.brand .dot{color:var(--dim);margin:0 5px}
.sub{color:var(--mut);font-size:12px}.spacer{flex:1}
.chip{font-family:var(--mono);font-size:12px;padding:4px 10px;border:1px solid var(--line);border-radius:20px;color:var(--mut)}
.chip.live{color:#06101f;background:var(--rd);border-color:var(--rd);font-weight:700}
.chip.live.hold{background:var(--gn)}
button{font:inherit;cursor:pointer;border-radius:8px;border:1px solid var(--line);background:#12203a;
color:var(--ink);padding:6px 12px;font-size:12.5px;font-weight:600}
button:hover{border-color:var(--bl)}button.on{background:var(--am);color:#06101f;border-color:var(--am)}
main{padding:14px 20px 20px;max-width:1280px;margin:0 auto}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:12px}
.kpi{background:linear-gradient(180deg,var(--panel),#0a101a);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.kpi .lab{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--mut)}
.kpi .val{font-size:30px;font-weight:800;font-variant-numeric:tabular-nums;line-height:1.15;margin-top:3px}
.kpi .val.gn{color:var(--gn)}.kpi .val.am{color:var(--am)}.kpi .val.rd{color:var(--rd)}
.kpi .sub2{font-size:11px;color:var(--dim);font-family:var(--mono)}
.wavebar{display:flex;align-items:center;gap:10px;margin-bottom:8px;font-family:var(--mono);font-size:12.5px}
.wavebar .w{color:var(--am)}.wavebar .mission{margin-left:auto;font-weight:700}
.mission.hold{color:var(--gn)}.mission.att{color:var(--rd)}
.mapwrap{position:relative;border:1px solid var(--line);border-radius:14px;overflow:hidden;background:#060a11}
svg#map{display:block;width:100%;height:auto}
#tip{position:absolute;pointer-events:none;background:#0a1220ee;border:1px solid var(--line);border-radius:8px;
padding:7px 10px;font-family:var(--mono);font-size:11.5px;color:var(--ink);opacity:0;transition:opacity .12s;z-index:9;max-width:220px}
#tip .k{color:var(--mut)}
.tl{margin-top:12px;position:relative;height:34px;border:1px solid var(--line);border-radius:8px;background:#0a111c;cursor:pointer;overflow:hidden}
.tl .band{position:absolute;top:0;bottom:0;opacity:.16}
.tl .bandlab{position:absolute;top:2px;font-size:9px;color:var(--mut);font-family:var(--mono);white-space:nowrap;padding-left:3px}
.tl .fill{position:absolute;top:0;bottom:0;left:0;background:linear-gradient(90deg,rgba(74,168,255,.18),rgba(58,208,216,.24));border-right:2px solid var(--cy)}
.tl .head{position:absolute;top:0;bottom:0;width:2px;background:var(--cy)}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:10px;font-size:11.5px;color:var(--mut);font-family:var(--mono)}
.legend b{font-weight:600;color:var(--ink)}
.sw{display:inline-block;width:10px;height:10px;border-radius:2px;vertical-align:-1px;margin-right:4px}
/* nodes */
.edge{stroke:#16233a;stroke-width:1}
.nd .shp{fill:#0d1a2b;stroke:var(--dim);stroke-width:1.6;transition:stroke .3s,fill .3s}
.nd.ok .shp{stroke:#2f6d55}
.nd.hit .shp{stroke:var(--rd);fill:#2a0f16;filter:url(#glow)}
.nd.hit{animation:thp 1.1s ease-in-out infinite}
@keyframes thp{50%{opacity:.5}}
.nd .lab{fill:var(--mut);font:9px var(--mono);text-anchor:middle}
.nd .badge{fill:var(--rd);font:bold 9px var(--mono);text-anchor:middle}
.arc{fill:none;stroke:var(--rd);stroke-width:1.7;stroke-dasharray:1500;opacity:.85;animation:arcfx 1.25s ease-out forwards}
@keyframes arcfx{0%{stroke-dashoffset:1500;opacity:.9}55%{stroke-dashoffset:0;opacity:.85}100%{stroke-dashoffset:0;opacity:0}}
.mitr{fill:none;stroke:var(--gn);stroke-width:2;animation:mitfx .85s ease-out forwards}
@keyframes mitfx{from{r:6;opacity:.9}to{r:30;opacity:0}}
.sectorlab{fill:#3a4a63;font:11px var(--mono);opacity:.5}
@media(max-width:760px){.kpis{grid-template-columns:repeat(2,1fr)}}
</style></head><body>
<header>
  <div class="brand">CORE&nbsp;LAB<span class="dot">·</span><span class="am">NCSRD</span></div>
  <div class="sub">Theater Battlespace — live adversarial engagement (simulated · non-kinetic)</div>
  <div class="spacer"></div>
  <span class="chip" id="turnChip">turn —</span>
  <span class="chip live hold" id="liveChip">● LIVE</span>
  <button id="pauseBtn">❚❚ Pause</button>
  <button data-pace="0.6">Slow</button>
  <button data-pace="0.34" class="on">Normal</button>
  <button data-pace="0.16">Fast</button>
  <a href="/" style="text-decoration:none"><button>← Panel</button></a>
</header>
<main>
  <div class="kpis">
    <div class="kpi"><div class="lab">Mission availability</div><div class="val gn" id="kAvail">—</div><div class="sub2" id="kAvail2">healthy nodes</div></div>
    <div class="kpi"><div class="lab">Active threats</div><div class="val rd" id="kActive">0</div><div class="sub2">on the battlespace</div></div>
    <div class="kpi"><div class="lab">Neutralised</div><div class="val gn" id="kMit">0</div><div class="sub2">by blue doctrine</div></div>
    <div class="kpi"><div class="lab">Injected</div><div class="val" id="kInj">0</div><div class="sub2">by red, cumulative</div></div>
    <div class="kpi"><div class="lab">Turn</div><div class="val am" id="kTurn">0</div><div class="sub2" id="kTurn2">/ 80</div></div>
  </div>
  <div class="wavebar"><span>◤ active:</span><span class="w" id="waveName">standing by</span>
    <span class="mission hold" id="mission">● THEATER HELD</span></div>
  <div class="mapwrap"><div id="tip"></div>
    <svg id="map" viewBox="0 0 1000 640" preserveAspectRatio="xMidYMid meet">
      <defs><filter id="glow" x="-60%" y="-60%" width="220%" height="220%">
        <feGaussianBlur stdDeviation="3.4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        <pattern id="hatch" width="8" height="8" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
          <line x1="0" y1="0" x2="0" y2="8" stroke="#ff4d5e" stroke-width="1.4" opacity=".5"/></pattern></defs>
      <g id="bg"></g><g id="edges"></g><g id="fx"></g><g id="nodes"></g>
    </svg>
  </div>
  <div class="tl" id="tl"><div class="fill" id="tlFill"></div><div class="head" id="tlHead"></div></div>
  <div class="legend" id="legend"></div>
</main>
<script>
const NODES = __NODES__, EDGES = __EDGES__, WAVES = __WAVES__, TURNS = 80;
const S = id => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';
const el = (n, a) => { const e = document.createElementNS(NS, n); for (const k in (a||{})) e.setAttribute(k, a[k]); return e; };
const byId = {}; NODES.forEach(n => byId[n.id] = n);

// ---- static map ----
const bg = S('bg'), edgesG = S('edges'), nodesG = S('nodes'), fxG = S('fx');
const SECT = [{n:'REAR',x0:0,x1:355,c:'#101a2e'},{n:'MAIN',x0:355,x1:690,c:'#0e1728'},{n:'FORWARD (FLOT)',x0:690,x1:975,c:'#141322'}];
for (const s of SECT){ bg.appendChild(el('rect',{x:s.x0,y:0,width:s.x1-s.x0,height:640,fill:s.c,opacity:.55}));
  const t=el('text',{x:s.x0+10,y:626,class:'sectorlab',fill:'#3a4a63'}); t.textContent=s.n; bg.appendChild(t); }
for (let gx=0;gx<=1000;gx+=50) bg.appendChild(el('line',{x1:gx,y1:0,x2:gx,y2:640,stroke:'#0e1728',['stroke-width']:1}));
for (let gy=0;gy<=640;gy+=50) bg.appendChild(el('line',{x1:0,y1:gy,x2:1000,y2:gy,stroke:'#0e1728',['stroke-width']:1}));
bg.appendChild(el('rect',{x:975,y:0,width:25,height:640,fill:'url(#hatch)'}));
const advT=el('text',{x:988,y:320,fill:'#ff4d5e',['font-size']:12,['font-family']:'var(--mono)','text-anchor':'middle',transform:'rotate(90 988 320)',opacity:.7}); advT.textContent='◄ ADVERSARY'; bg.appendChild(advT);
for (const [a,b] of EDGES) edgesG.appendChild(el('line',{class:'edge',x1:NODES[a].x,y1:NODES[a].y,x2:NODES[b].x,y2:NODES[b].y}));

function shape(kind,r){ // identity by silhouette
  if(kind==='hq')     return el('rect',{class:'shp',x:-r,y:-r,width:2*r,height:2*r,transform:'rotate(45)',rx:2});
  if(kind==='uplink') return el('polygon',{class:'shp',points:`0,${-r-2} ${r},${r} ${-r},${r}`});
  if(kind==='uav')    return el('polygon',{class:'shp',points:`0,${-r-1} ${r-1},${r} ${-r+1},${r}`});
  if(kind==='cell')   return el('rect',{class:'shp',x:-r,y:-r,width:2*r,height:2*r,rx:2});
  if(kind==='logi')   return el('rect',{class:'shp',x:-r+1,y:-r+1,width:2*r-2,height:2*r-2,rx:1});
  if(kind==='relay')  return el('circle',{class:'shp',r:r});
  return el('circle',{class:'shp',r:r-1}); // sensor
}
const ndEl={};
for (const n of NODES){
  const g=el('g',{class:'nd ok',transform:`translate(${n.x} ${n.y})`}); g.dataset.id=n.id;
  const r=5+n.crit*0.9; g.appendChild(shape(n.kind,r));
  const badge=el('text',{class:'badge',y:-r-4}); badge.textContent=''; g.appendChild(badge);
  if(n.crit>=5){ const l=el('text',{class:'lab',y:r+11}); l.textContent=n.label; g.appendChild(l); }
  g.addEventListener('mousemove',e=>showTip(e,n)); g.addEventListener('mouseleave',hideTip);
  nodesG.appendChild(g); ndEl[n.id]={g,badge};
}
const tip=S('tip');
function showTip(e,n){ const st=state[n.id]||{}; const box=S('map').getBoundingClientRect();
  tip.innerHTML=`<b>${n.label}</b> · ${n.kind.toUpperCase()}<br><span class="k">sector</span> ${n.sector}`+
    `<br><span class="k">status</span> ${st.hit?('<span style="color:var(--rd)">COMPROMISED ('+st.hit+' threat'+(st.hit>1?'s':'')+')</span>'):'<span style="color:var(--gn)">secure</span>'}`;
  tip.style.left=(e.clientX-box.left+14)+'px'; tip.style.top=(e.clientY-box.top+12)+'px'; tip.style.opacity=1; }
function hideTip(){ tip.style.opacity=0; }

// timeline wave bands
const tl=S('tl');
const WCOL=['#ffb020','#4aa8ff','#c07cff','#ff4d5e'];
WAVES.forEach((w,i)=>{ const b=document.createElement('div'); b.className='band';
  b.style.left=(w.s/TURNS*100)+'%'; b.style.width=((w.e-w.s)/TURNS*100)+'%'; b.style.background=WCOL[i%4];
  tl.appendChild(b); const lab=document.createElement('div'); lab.className='bandlab';
  lab.style.left=(w.s/TURNS*100)+'%'; lab.textContent='◤'+w.name.split('·')[1]; tl.appendChild(lab); });

// legend
S('legend').innerHTML =
  '<span><span class="sw" style="background:#2f6d55"></span><b>secure</b></span>'+
  '<span><span class="sw" style="background:var(--rd)"></span><b>compromised</b></span>'+
  '<span>◆ C2</span><span>▲ SATCOM/UAV</span><span>■ gNB/LOG</span><span>● ISR/relay</span>'+
  '<span style="color:var(--rd)">╱ threat launch</span><span style="color:var(--gn)">◌ mitigation</span>';

// ---- live state ----
let frames=[], cur=-1, live=true, paused=false, es=null, state={};
function color(av){ return av>=0.9?'gn':av>=0.75?'am':'rd'; }
function render(i){ const f=frames[i]; if(!f) return; cur=i;
  const comp={}; f.active.forEach(a=>{comp[a.node]=(comp[a.node]||0)+1;}); state={};
  for(const n of NODES){ const c=comp[n.id]||0; const o=ndEl[n.id]; state[n.id]={hit:c};
    o.g.setAttribute('class','nd '+(c?'hit':'ok')); o.badge.textContent=c>1?c:''; }
  const k=f.kpi; const av=Math.round(k.availability*100);
  S('kAvail').textContent=av+'%'; S('kAvail').className='val '+color(k.availability);
  S('kAvail2').textContent=k.healthy+'/'+k.total+' nodes';
  S('kActive').textContent=k.active; S('kMit').textContent=k.mitigated; S('kInj').textContent=k.injected;
  S('kTurn').textContent=f.turn; S('kTurn2').textContent='/ '+f.turns;
  S('turnChip').textContent='turn '+f.turn+' / '+f.turns;
  S('waveName').textContent=f.waves.join('  ·  ')||'consolidation — clearing residual';
  const m=S('mission'); if(k.active>0){m.className='mission att';m.textContent='● UNDER ATTACK';}else{m.className='mission hold';m.textContent='● THEATER HELD';}
  S('tlFill').style.width=(f.turn/f.turns*100)+'%'; S('tlHead').style.left=(f.turn/f.turns*100)+'%';
}
function spawnArc(nid){ const n=byId[nid]; if(!n)return; const oy=Math.max(20,Math.min(620,n.y+(Math.random()*80-40)));
  const p=el('path',{class:'arc',d:`M990 ${oy} Q ${(n.x+990)/2} ${(n.y+oy)/2-70} ${n.x} ${n.y}`}); fxG.appendChild(p);
  setTimeout(()=>p.remove(),1300); }
function spawnMit(nid){ const n=byId[nid]; if(!n)return; const c=el('circle',{class:'mitr',cx:n.x,cy:n.y,r:6}); fxG.appendChild(c); setTimeout(()=>c.remove(),900); }
function onTurn(f){ frames.push(f);
  if(live && !paused){ const i=frames.length-1;
    if(i>0){ f.injects.forEach(x=>spawnArc(x.node)); f.mitigations.forEach(x=>spawnMit(x.node)); }
    render(i); } }
function setLive(v){ live=v; const c=S('liveChip'); c.style.display='';
  c.className='chip live'+(v?'':' off'); if(!v){c.textContent='◀ REPLAY';c.classList.remove('live');c.style.background='#12203a';c.style.color='var(--mut)';}
  else{ c.textContent='● LIVE'; render(frames.length-1); } }

// timeline scrub
tl.addEventListener('click',e=>{ const r=tl.getBoundingClientRect(); const frac=(e.clientX-r.left)/r.width;
  const turn=Math.max(1,Math.min(TURNS,Math.round(frac*TURNS))); const idx=frames.findIndex(f=>f.turn>=turn);
  if(idx>=0){ live=false; S('liveChip').textContent='◀ REPLAY t'+turn; S('liveChip').style.background='#12203a'; S('liveChip').style.color='var(--mut)'; S('liveChip').classList.remove('hold'); render(idx); } });
S('liveChip').addEventListener('click',()=>{ if(frames.length){ live=true; S('liveChip').textContent='● LIVE'; S('liveChip').style.background=''; S('liveChip').style.color=''; render(frames.length-1);} });
S('pauseBtn').addEventListener('click',()=>{ paused=!paused; S('pauseBtn').textContent=paused?'▶ Resume':'❚❚ Pause'; S('pauseBtn').classList.toggle('on',paused); if(!paused){live=true;render(frames.length-1);} });
document.querySelectorAll('button[data-pace]').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('button[data-pace]').forEach(x=>x.classList.remove('on')); b.classList.add('on'); start(parseFloat(b.dataset.pace)); }));

function start(pace){ if(es) es.close(); frames=[]; cur=-1; live=true; paused=false; fxG.innerHTML='';
  S('pauseBtn').textContent='❚❚ Pause'; S('pauseBtn').classList.remove('on');
  S('liveChip').textContent='● LIVE'; S('liveChip').className='chip live hold';
  es=new EventSource('/api/campaign/stream?pace='+pace+'&turns='+TURNS);
  es.addEventListener('turn',e=>onTurn(JSON.parse(e.data)));
  es.addEventListener('end',()=>{ es.close(); es=null; const c=S('liveChip'); c.textContent='✔ COMPLETE'; c.className='chip live hold'; });
  es.onerror=()=>{ if(es){es.close();es=null;} };
}
start(0.34);
</script></body></html>"""


def _map_page(nodes: List[Dict], edges: List[List[int]]) -> str:
    return (_MAP_PAGE.replace("__NODES__", json.dumps(nodes))
            .replace("__EDGES__", json.dumps(edges))
            .replace("__WAVES__", json.dumps(wave_windows())))


app = build_control_app()
