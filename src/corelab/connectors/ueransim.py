"""UERANSIM control connector — drive the simulated RAN/UEs, and inject faults.

UERANSIM has no REST API; control happens through its ``nr-cli`` binary (UNIX-socket CLI inside
the gNB/UE container). This connector wraps ``nr-cli`` behind an injectable ``runner`` callable:

- default runner: ``docker exec <container> ./nr-cli <node> -e '<command>'``
- tests inject a fake runner; a live testbed can also inject e.g. an SSH runner.

This doubles as the **fault-injection primitive** for Stages 4–5 (TeleAgentBench scenarios and
trajectory generation): ``deregister`` ≈ connectivity loss, ``ps-release`` ≈ session drop.

Command set targets UERANSIM v3.2.x (``status``, ``info``, ``deregister <mode>``,
``ps-establish``, ``ps-release``, ``ps-list``; gNB: ``amf-list``, ``ue-list``, ``ue-count``).
Validated against a live UERANSIM at testbed bring-up — until then, mock-tested only.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

# runner(argv) -> (exit_code, stdout, stderr)
Runner = Callable[[List[str]], "RunResult"]


@dataclass
class RunResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def docker_exec_runner(timeout: int = 15) -> Runner:
    """Default runner: executes argv via subprocess (used as ``docker exec ...``)."""

    def run(argv: List[str]) -> RunResult:
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
            return RunResult(proc.returncode, proc.stdout, proc.stderr)
        except FileNotFoundError as exc:
            return RunResult(127, "", f"not found: {exc}")
        except subprocess.TimeoutExpired:
            return RunResult(124, "", f"timeout after {timeout}s")

    return run


class UERANSIMController:
    def __init__(
        self,
        container: str = "ueransim",
        nr_cli: str = "/ueransim/build/nr-cli",
        runner: Optional[Runner] = None,
        use_docker: bool = True,
    ) -> None:
        self.container = container
        self.nr_cli = nr_cli
        self.runner = runner or docker_exec_runner()
        self.use_docker = use_docker

    # ---- plumbing ---------------------------------------------------------

    def _argv(self, args: List[str]) -> List[str]:
        base = ["docker", "exec", self.container] if self.use_docker else []
        return base + [self.nr_cli] + args

    def _exec(self, node: str, command: str) -> Dict[str, Any]:
        result = self.runner(self._argv([node, "-e", command]))
        return {
            "node": node,
            "command": command,
            "ok": result.ok,
            "output": (result.stdout or result.stderr).strip(),
        }

    def is_available(self) -> bool:
        try:
            return self.runner(self._argv(["-d"])).ok
        except Exception:
            return False

    # ---- observe -----------------------------------------------------------

    def list_nodes(self) -> List[str]:
        """All UE/gNB nodes visible to nr-cli (``nr-cli -d``)."""
        result = self.runner(self._argv(["-d"]))
        if not result.ok:
            return []
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def ue_status(self, ue_node: str) -> Dict[str, Any]:
        return self._exec(ue_node, "status")

    def gnb_status(self, gnb_node: str) -> Dict[str, Any]:
        return self._exec(gnb_node, "status")

    def gnb_ue_list(self, gnb_node: str) -> Dict[str, Any]:
        return self._exec(gnb_node, "ue-list")

    def ps_list(self, ue_node: str) -> Dict[str, Any]:
        return self._exec(ue_node, "ps-list")

    # ---- act (fault injection / control) -------------------------------------

    def deregister(self, ue_node: str, mode: str = "normal") -> Dict[str, Any]:
        """Deregister a UE (``normal`` | ``disable-5g`` | ``switch-off`` | ``remove-sim``).
        The Stage-4/5 'connectivity loss' fault primitive."""
        allowed = {"normal", "disable-5g", "switch-off", "remove-sim"}
        if mode not in allowed:
            raise ValueError(f"mode must be one of {sorted(allowed)}")
        return self._exec(ue_node, f"deregister {mode}")

    def ps_establish(self, ue_node: str, session_type: str = "IPv4", sst: int = 1) -> Dict[str, Any]:
        return self._exec(ue_node, f"ps-establish {session_type} --sst {sst}")

    def ps_release(self, ue_node: str, ps_id: int = 1) -> Dict[str, Any]:
        return self._exec(ue_node, f"ps-release {ps_id}")
