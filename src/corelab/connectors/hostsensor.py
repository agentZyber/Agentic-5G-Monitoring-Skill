"""Live Linux host forensics — REAL eBPF / persistence / network telemetry for the blue side.

Turns the war-game's defender from simulation into detection over an actual host: enumerates loaded
eBPF programs (``bpftool``), pinned bpf objects (``/sys/fs/bpf``), userland persistence
(``/etc/ld.so.preload``), kernel modules, and listening sockets. Strictly READ-ONLY.

The command runner is injectable — :func:`local_runner` (subprocess on this host), :func:`remote_runner`
(sudo over SSH to a testbed host; credentials come from the environment, never hard-coded), or a fake
for tests. That is how the same detectors run against a real box (`.159`) or in CI unchanged.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Callable, Dict, List, Optional

Runner = Callable[[List[str]], str]


def local_runner(cmd: List[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return ""


def remote_runner(host: str, user: str, password_env: str = "HOSTSENSOR_PASS") -> Runner:
    """Run commands as ``sudo`` over SSH. Password is read from ``password_env`` (kept out of code/files)."""
    password = os.getenv(password_env, "")

    def _run(cmd: List[str]) -> str:
        remote = "sudo " + " ".join(cmd)
        ssh = ["sshpass", "-e", "ssh", "-o", "StrictHostKeyChecking=no",
               "-o", "UserKnownHostsFile=/dev/null", "-o", "ConnectTimeout=12",
               "-o", "PreferredAuthentications=password", "-o", "PubkeyAuthentication=no",
               f"{user}@{host}", remote]
        try:
            return subprocess.run(ssh, capture_output=True, text=True, timeout=30,
                                  env={**os.environ, "SSHPASS": password}).stdout
        except Exception:
            return ""

    return _run


# syscalls whose eBPF hooks are classic rootkit/backdoor signatures (file/proc/network hiding, C2)
SUSPICIOUS_HOOKS = ("getdents", "read", "write", "openat", "bpf", "kill", "tcp", "udp",
                    "execve", "recvmsg", "sendmsg")


class HostSensor:
    """Read-only forensic view of a Linux host (local or remote via an injected runner)."""

    def __init__(self, runner: Runner = local_runner, sudo: bool = True) -> None:
        self.runner = runner
        self.sudo = sudo

    def _run(self, *cmd: str) -> str:
        prefix = ["sudo"] if (self.sudo and self.runner is local_runner) else []
        return self.runner(prefix + list(cmd))

    def ebpf_programs(self) -> List[Dict[str, Any]]:
        raw = self._run("bpftool", "-j", "prog", "list")
        try:
            progs = json.loads(raw) if raw.strip() else []
        except json.JSONDecodeError:
            progs = []
        out = []
        for p in progs:
            out.append({"id": p.get("id"), "type": p.get("type"), "name": p.get("name"),
                        "tag": p.get("tag"), "attach": p.get("attach_type") or p.get("attach")})
        return out

    def pinned_bpf(self) -> List[str]:
        raw = self._run("find", "/sys/fs/bpf", "-mindepth", "1")
        return [line for line in raw.splitlines() if line.strip()]

    def ld_preload(self) -> List[str]:
        raw = self._run("cat", "/etc/ld.so.preload")
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def kernel_modules(self) -> List[str]:
        raw = self._run("lsmod")
        return [line.split()[0] for line in raw.splitlines()[1:] if line.split()]

    def listening_sockets(self) -> List[Dict[str, str]]:
        raw = self._run("ss", "-H", "-tulpn")
        out = []
        for line in raw.splitlines():
            parts = line.split()
            if len(parts) >= 5:
                out.append({"proto": parts[0], "local": parts[4]})
        return out

    def snapshot(self) -> Dict[str, Any]:
        return {
            "ebpf_programs": self.ebpf_programs(),
            "pinned_bpf": self.pinned_bpf(),
            "ld_preload": self.ld_preload(),
            "kernel_modules": self.kernel_modules(),
            "listening_sockets": self.listening_sockets(),
        }
