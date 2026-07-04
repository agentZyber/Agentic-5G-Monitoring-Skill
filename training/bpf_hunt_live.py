#!/usr/bin/env python
"""Live eBPF-backdoor hunt on a REAL host — the war-game blue side, off simulation.

Real read-only baseline → plant a benign, reversible eBPF hook on getdents64 (the file-hiding
rootkit signature) → the `bpf-hunt` agent detects it by diffing real `bpftool` state → clean up.
Credentials come from the environment, never from the file.

    HOSTSENSOR_PASS=... python training/bpf_hunt_live.py [host] [user]
"""
import os
import subprocess
import sys
import time

from corelab.connectors.hostsensor import HostSensor, remote_runner
from corelab.packs.bpf_hunt import build_registry

HOST = sys.argv[1] if len(sys.argv) > 1 else "10.160.101.159"
USER = sys.argv[2] if len(sys.argv) > 2 else "localadmin"
_OPTS = ["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
         "-o", "ConnectTimeout=12", "-o", "PreferredAuthentications=password",
         "-o", "PubkeyAuthentication=no"]


def ssh(remote_cmd: str) -> str:
    return subprocess.run(["sshpass", "-e", "ssh", *_OPTS, f"{USER}@{HOST}", remote_cmd],
                          capture_output=True, text=True, timeout=45,
                          env={**os.environ, "SSHPASS": os.getenv("HOSTSENSOR_PASS", "")}).stdout


sensor = HostSensor(runner=remote_runner(HOST, USER, "HOSTSENSOR_PASS"))

print(f"[1] BASELINE — read-only forensics on {HOST}")
baseline = sensor.snapshot()
print(f"    eBPF programs={len(baseline['ebpf_programs'])} · pinned_bpf={len(baseline['pinned_bpf'])} "
      f"· ld.so.preload={baseline['ld_preload'] or 'absent'} · sockets={len(baseline['listening_sockets'])}")

print("[2] RED plants a real eBPF hook on getdents64 (benign empty action; reversible)")
# a transient systemd unit keeps bpftrace alive across the separate detection SSHs; stop = clean removal
ssh("sudo systemd-run --unit=corelab-bpfhook --quiet "
    "bpftrace -e 'tracepoint:syscalls:sys_enter_getdents64 { }'")
time.sleep(6)

print("[3] BLUE — the bpf-hunt agent detects it by diffing real bpftool state")
reg = build_registry(sensor=sensor, baseline=baseline)
report = reg.get("hunt_report").invoke()
print(f"    threat_detected={report['threat_detected']} · ebpf={report['ebpf_verdict']}")
for p in report["suspicious_programs"]:
    print(f"    ->  SUSPICIOUS: {p['name']} (type={p['type']}) hooks {p['suspicious_hooks']}")

print("[4] CLEANUP — remove the planted hook (reversible)")
ssh("sudo systemctl stop corelab-bpfhook; sudo systemctl reset-failed corelab-bpfhook 2>/dev/null")
time.sleep(2)
after = sensor.ebpf_programs()
print(f"    eBPF programs now={len(after)} (baseline {len(baseline['ebpf_programs'])}) -> "
      f"restored={'YES' if len(after) <= len(baseline['ebpf_programs']) else 'NO'}")
