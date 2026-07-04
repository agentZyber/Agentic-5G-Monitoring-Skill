#!/bin/bash
# CORE Lab NCSRD — war-game RED harness (isolated VM only).
# Deploys REAL, contained, reversible eBPF-backdoor SIGNATURES for detection testing (blue = bpf-hunt).
# Every technique loads a genuine kernel artifact an eBPF rootkit would create, with a benign/empty
# payload, as a transient systemd unit or file — all undone by `clean`. Detection engineering, not weaponry.
set +e
CMD="${1:-help}"; TECH="${2:-}"

deploy() {
  case "$1" in
    hide)  # eBPF program hooking getdents64 — the file/process-HIDING rootkit signature
      sudo systemd-run --unit=red-ebpf-hide --quiet \
        bpftrace -e 'tracepoint:syscalls:sys_enter_getdents64 { }' && \
        echo "  [+] hide: eBPF getdents64 hook (file-hiding signature)" ;;
    net)   # eBPF program hooking tcp — the network-backdoor / C2-trigger signature
      sudo systemd-run --unit=red-ebpf-net --quiet \
        bpftrace -e 'kprobe:tcp_sendmsg { }' && \
        echo "  [+] net: eBPF tcp_sendmsg hook (network-backdoor signature)" ;;
    port)  # a raw backdoor listener on :4444 (C2 port signature)
      sudo systemd-run --unit=red-backdoor-port --quiet python3 -c \
        'import socket,time; s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); s.bind(("0.0.0.0",4444)); s.listen(); time.sleep(999999)' && \
        echo "  [+] port: backdoor listener on 0.0.0.0:4444" ;;
    all) deploy hide; deploy net; deploy port ;;
    *) echo "  techniques: hide | net | port | all" ;;
  esac
}

case "$CMD" in
  deploy) deploy "${TECH:-all}" ;;
  clean)
    sudo systemctl stop red-ebpf-hide red-ebpf-net red-backdoor-port 2>/dev/null
    sudo systemctl reset-failed red-ebpf-hide red-ebpf-net red-backdoor-port 2>/dev/null
    echo "  [-] all red artifacts removed" ;;
  status)
    echo "  eBPF programs loaded : $(sudo bpftool prog list | grep -cE '^[0-9]+:')"
    echo "  suspicious hooks     : $(sudo bpftool prog list | grep -icE 'getdents|tcp_sendmsg')"
    echo "  backdoor :4444 open  : $(ss -H -tln 2>/dev/null | grep -c ':4444')"
    echo "  red units active     : $(systemctl list-units 'red-*' --state=active --no-legend 2>/dev/null | wc -l)" ;;
  *) echo "usage: red_harness.sh {deploy [hide|net|port|all] | clean | status}" ;;
esac
