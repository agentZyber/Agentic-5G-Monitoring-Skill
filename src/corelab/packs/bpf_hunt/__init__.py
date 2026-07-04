"""bpf-hunt — agentic detection of eBPF backdoors + host persistence on a REAL Linux host.

The blue side made real: instead of a simulated world, these tools read live host state through a
:class:`~corelab.connectors.hostsensor.HostSensor` and diff it against a trusted baseline. The core
signal is an eBPF program that hooks a file/process/network syscall (``getdents``, ``read``,
``tcp``, ``bpf`` …) — the mechanism eBPF rootkits (boopkit, TripleCross, bad-bpf) use to hide files,
processes and connections. Read-only: it detects and reports; response stays human-gated.

Opt-in (needs a host sensor + baseline in the context). Enable via ``CORELAB_PACKS=...,bpf-hunt``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from corelab.agent.tools import ToolRegistry
from corelab.connectors.hostsensor import SUSPICIOUS_HOOKS, HostSensor

PACK: Dict[str, Any] = {
    "name": "bpf-hunt",
    "description": "Live eBPF-backdoor & host-persistence hunting over a real Linux host (read-only).",
    "connectors": ["hostsensor"],
    "datasets": [],
    "system_prompt": (
        "You are a host-defence agent hunting eBPF backdoors on a real Linux host. Method: take a "
        "snapshot, diff loaded eBPF programs against the trusted baseline, and FLAG any new program "
        "that hooks a file/process/network syscall (getdents, read, write, bpf, tcp…) — that is how "
        "eBPF rootkits hide. Also check userland persistence (/etc/ld.so.preload), pinned bpf objects, "
        "new kernel modules, and new listening ports. You only detect and report — response is human-gated."
    ),
}


def _suspicious_hooks(prog: Dict[str, Any]) -> List[str]:
    hay = f"{prog.get('name', '')} {prog.get('attach', '')} {prog.get('type', '')}".lower()
    return [h for h in SUSPICIOUS_HOOKS if h in hay]


def build_registry(sensor: Optional[HostSensor] = None,
                   baseline: Optional[Dict[str, Any]] = None) -> ToolRegistry:
    sensor = sensor if sensor is not None else HostSensor()
    base = baseline or {}
    reg = ToolRegistry()

    @reg.tool(name="host_snapshot",
              description="Summarise current host forensic state (eBPF programs, pinned bpf, ld.so.preload, modules, sockets).",
              tags=("bpf-hunt", "sense"))
    def host_snapshot() -> Dict[str, Any]:
        s = sensor.snapshot()
        return {"ebpf_programs": len(s["ebpf_programs"]), "pinned_bpf": len(s["pinned_bpf"]),
                "ld_preload": s["ld_preload"], "kernel_modules": len(s["kernel_modules"]),
                "listening_sockets": len(s["listening_sockets"])}

    @reg.tool(name="scan_ebpf_anomalies",
              description="Diff loaded eBPF programs against the trusted baseline; flag NEW programs, "
                          "especially any hooking file/process/network syscalls (eBPF-backdoor signature).",
              tags=("bpf-hunt", "ebpf", "detect"))
    def scan_ebpf_anomalies() -> Dict[str, Any]:
        current = sensor.ebpf_programs()
        base_keys = {(p.get("tag"), p.get("name")) for p in base.get("ebpf_programs", [])}
        new = [p for p in current if (p.get("tag"), p.get("name")) not in base_keys]
        flagged = [{**p, "suspicious_hooks": _suspicious_hooks(p)} for p in new if _suspicious_hooks(p)]
        verdict = ("EBPF BACKDOOR SUSPECTED" if flagged
                   else "new-but-unflagged programs" if new else "clean")
        return {"total_loaded": len(current), "baseline_count": len(base.get("ebpf_programs", [])),
                "new_count": len(new), "new_programs": new, "suspicious": flagged, "verdict": verdict}

    @reg.tool(name="check_persistence",
              description="Check host persistence vectors: /etc/ld.so.preload, pinned bpf objects, and new kernel modules vs baseline.",
              tags=("bpf-hunt", "persistence"))
    def check_persistence() -> Dict[str, Any]:
        s = sensor.snapshot()
        base_mods = set(base.get("kernel_modules", []))
        new_mods = [m for m in s["kernel_modules"] if m not in base_mods] if base_mods else []
        findings = []
        if s["ld_preload"]:
            findings.append({"type": "ld.so.preload", "detail": s["ld_preload"]})
        if s["pinned_bpf"]:
            findings.append({"type": "pinned_bpf", "detail": s["pinned_bpf"]})
        if new_mods:
            findings.append({"type": "new_kernel_modules", "detail": new_mods})
        return {"findings": findings, "verdict": "PERSISTENCE FOUND" if findings else "clean"}

    @reg.tool(name="network_exposure",
              description="List listening sockets and flag any that appeared since the baseline (possible C2/backdoor port).",
              tags=("bpf-hunt", "network"))
    def network_exposure() -> Dict[str, Any]:
        cur = sensor.listening_sockets()
        base_locals = {s["local"] for s in base.get("listening_sockets", [])}
        new = [s for s in cur if s["local"] not in base_locals] if base_locals else []
        return {"listening": len(cur), "new_since_baseline": new}

    @reg.tool(name="hunt_report",
              description="Full hunt: run the eBPF and persistence detectors and return an overall threat verdict.",
              tags=("bpf-hunt", "report"))
    def hunt_report() -> Dict[str, Any]:
        e = scan_ebpf_anomalies()
        p = check_persistence()
        threat = bool(e["suspicious"]) or p["verdict"] != "clean"
        return {"threat_detected": threat, "ebpf_verdict": e["verdict"],
                "persistence_verdict": p["verdict"], "suspicious_programs": e["suspicious"],
                "persistence_findings": p["findings"]}

    return reg
