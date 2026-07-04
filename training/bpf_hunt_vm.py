#!/usr/bin/env python
"""Real red/blue on the isolated VM.

RED (the harness on the VM) deploys genuine, contained eBPF-backdoor artifacts; BLUE (the bpf-hunt
agent, here) detects them by diffing real host telemetry over SSH against a clean baseline. Fully
reversible. Credentials come from the environment.

    HOSTSENSOR_PASS=... python training/bpf_hunt_vm.py [host] [user]
"""
import os
import subprocess
import sys
import time

from corelab.connectors.hostsensor import HostSensor, remote_runner
from corelab.packs.bpf_hunt import build_registry

HOST = sys.argv[1] if len(sys.argv) > 1 else "10.160.101.128"
USER = sys.argv[2] if len(sys.argv) > 2 else "localadmin"
_OPTS = ["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
         "-o", "ConnectTimeout=12", "-o", "PreferredAuthentications=password",
         "-o", "PubkeyAuthentication=no"]


def red(cmd: str) -> str:
    return subprocess.run(["sshpass", "-e", "ssh", *_OPTS, f"{USER}@{HOST}", f"./red_harness.sh {cmd}"],
                          capture_output=True, text=True, timeout=45,
                          env={**os.environ, "SSHPASS": os.getenv("HOSTSENSOR_PASS", "")}).stdout.rstrip()


sensor = HostSensor(runner=remote_runner(HOST, USER, "HOSTSENSOR_PASS"))

print(f"[0] ensure the VM ({HOST}) is clean\n{red('clean')}")
print("[1] BLUE — clean baseline (real host forensics over SSH)")
baseline = sensor.snapshot()
print(f"    eBPF programs={len(baseline['ebpf_programs'])} · listening sockets={len(baseline['listening_sockets'])}")

print("[2] RED — deploy genuine eBPF-backdoor artifacts on the VM")
print(red("deploy all"))
time.sleep(6)

print("[3] BLUE — the bpf-hunt agent detects them")
reg = build_registry(sensor=sensor, baseline=baseline)
rep = reg.get("hunt_report").invoke()
net = reg.get("network_exposure").invoke()
print(f"    threat_detected={rep['threat_detected']} · ebpf={rep['ebpf_verdict']}")
for p in rep["suspicious_programs"]:
    print(f"    ->  SUSPICIOUS eBPF: {p['name']} (type={p['type']}) hooks {p['suspicious_hooks']}")
for s in net["new_since_baseline"]:
    print(f"    ->  NEW LISTENER: {s['proto']} {s['local']}  (possible C2/backdoor port)")

print("[4] CLEANUP — tear down the red side (reversible)")
print(red("clean"))
time.sleep(2)
after = sensor.ebpf_programs()
print(f"    eBPF programs now={len(after)} (baseline {len(baseline['ebpf_programs'])}) -> "
      f"restored={'YES' if len(after) <= len(baseline['ebpf_programs']) else 'NO'}")
