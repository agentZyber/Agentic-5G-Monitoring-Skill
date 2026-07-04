"""bpf-hunt: eBPF-backdoor detection over a HostSensor with an injected (fake) command runner."""

import json

from corelab.connectors.hostsensor import HostSensor
from corelab.packs.bpf_hunt import PACK, build_registry

_BASELINE_PROGS = [{"id": 2, "type": "tracing", "name": "hid_tail_call", "tag": "7cc47bbf07148bfe"}]
_GETDENTS_HOOK = {"id": 90, "type": "tracepoint",
                  "name": "tracepoint_syscalls_sys_enter_getdents64", "tag": "57cd311f2e27366b"}


def _runner(progs, preload="", modules="Module Size\nkvm 1000\n",
            sockets="tcp LISTEN 0 0 0.0.0.0:22 0.0.0.0:*"):
    def run(cmd):
        c = " ".join(cmd)
        if "prog list" in c:
            return json.dumps(progs)
        if "/sys/fs/bpf" in c:
            return ""
        if "ld.so.preload" in c:
            return preload
        if cmd[:1] == ["lsmod"]:
            return modules
        if cmd[:1] == ["ss"]:
            return sockets
        return ""
    return run


def _baseline():
    return HostSensor(runner=_runner(_BASELINE_PROGS), sudo=False).snapshot()


def test_detects_ebpf_getdents_backdoor():
    infected = HostSensor(runner=_runner(_BASELINE_PROGS + [_GETDENTS_HOOK]), sudo=False)
    reg = build_registry(sensor=infected, baseline=_baseline())

    scan = reg.get("scan_ebpf_anomalies").invoke()
    assert scan["new_count"] == 1 and scan["verdict"] == "EBPF BACKDOOR SUSPECTED"
    assert scan["suspicious"][0]["name"].endswith("getdents64")
    assert "getdents" in scan["suspicious"][0]["suspicious_hooks"]

    report = reg.get("hunt_report").invoke()
    assert report["threat_detected"] is True and report["ebpf_verdict"] == "EBPF BACKDOOR SUSPECTED"


def test_clean_host_is_clean():
    clean = HostSensor(runner=_runner(_BASELINE_PROGS), sudo=False)
    reg = build_registry(sensor=clean, baseline=_baseline())
    assert reg.get("scan_ebpf_anomalies").invoke()["verdict"] == "clean"
    assert reg.get("hunt_report").invoke()["threat_detected"] is False


def test_persistence_and_network_flags():
    sensor = HostSensor(runner=_runner(_BASELINE_PROGS, preload="/tmp/evil.so",
                                       sockets="tcp LISTEN 0 0 0.0.0.0:4444 0.0.0.0:*"), sudo=False)
    reg = build_registry(sensor=sensor, baseline=_baseline())
    pers = reg.get("check_persistence").invoke()
    assert pers["verdict"] == "PERSISTENCE FOUND"
    assert pers["findings"][0]["type"] == "ld.so.preload"
    net = reg.get("network_exposure").invoke()
    assert any(":4444" in s["local"] for s in net["new_since_baseline"])


def test_pack_metadata():
    assert PACK["name"] == "bpf-hunt" and "hostsensor" in PACK["connectors"]
