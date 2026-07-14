"""Launch War-Game Mission Control — a local web panel to run every war-game test/demo, live.

    python training/wargame_control.py            # -> http://127.0.0.1:8800
    CONTROL_PORT=9000 python training/wargame_control.py

Hardware tests light up when their credential is exported before launch:
    SSHPASS=…          the GPU box (sovereign LLM defender)
    HOSTSENSOR_PASS=…  the isolated red VM (eBPF hunt)
    AMARISOFT_WS_URL=… the Amarisoft 5G testbed (live RF)
"""
import os
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # make `corelab` importable

import uvicorn

from corelab.wargame.control import build_control_app


def _listen_socket(port: int) -> socket.socket:
    """A dual-stack listener so `localhost` reaches us whether it resolves to ::1 or 127.0.0.1.

    Preview/health-checkers hit `localhost`; binding IPv4-only makes an IPv6 `localhost` refuse the
    connection and the server gets torn down. Bind IPv6 with V6ONLY off (accepts IPv4-mapped too);
    fall back to plain IPv4 if the platform won't do dual-stack.
    """
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except OSError:
            pass
        s.bind(("::", port))
    except OSError:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", port))
    s.listen(128)
    s.set_inheritable(True)
    return s


if __name__ == "__main__":
    port = int(os.getenv("PORT") or os.getenv("CONTROL_PORT", "8800"))   # honour a harness-assigned PORT
    print(f"War-Game Mission Control  →  http://localhost:{port}", flush=True)
    sock = _listen_socket(port)
    uvicorn.Server(uvicorn.Config(build_control_app(), log_level="warning")).run(sockets=[sock])
