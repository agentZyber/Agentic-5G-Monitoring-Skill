"""Launch War-Game Mission Control — a local web panel to run every war-game test/demo, live.

    python training/wargame_control.py            # -> http://127.0.0.1:8800
    CONTROL_PORT=9000 python training/wargame_control.py

Hardware tests light up when their credential is exported before launch:
    SSHPASS=…          the GPU box (sovereign LLM defender)
    HOSTSENSOR_PASS=…  the isolated red VM (eBPF hunt)
    AMARISOFT_WS_URL=… the Amarisoft 5G testbed (live RF)
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # make `corelab` importable

import uvicorn

from corelab.wargame.control import build_control_app

if __name__ == "__main__":
    host = os.getenv("CONTROL_HOST", "127.0.0.1")
    port = int(os.getenv("CONTROL_PORT", "8800"))
    print(f"War-Game Mission Control  →  http://{host}:{port}", flush=True)
    uvicorn.run(build_control_app(), host=host, port=port, log_level="warning")
