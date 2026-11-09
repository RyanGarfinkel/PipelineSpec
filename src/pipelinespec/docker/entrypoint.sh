#!/bin/sh
mount -t tracefs none /sys/kernel/tracing 2>/dev/null

export BPFTRACE_PERF_RB_PAGES=16384
export BPFTRACE_MAX_STRLEN=4096
export BPFTRACE_MAX_MAP_KEYS=8192
export BPFTRACE_MAX_BPF_PROGS=1024
export BPFTRACE_MAX_PROBES=1024

script=/pspec/trace.bt

if [ -d /sys/kernel/tracing/events/syscalls/sys_enter_open ]; then
    cat /pspec/trace.bt /pspec/legacy.bt > /tmp/trace.bt
    script=/tmp/trace.bt
fi

bpftrace -B full -o /tmp/ebpf.txt "$script" &
tracer=$!

mitmdump --listen-port 8080 --set confdir=/pspec/mitm --set connection_strategy=lazy -q -s /pspec/addon.py >/tmp/mitm.log 2>&1 &
proxy=$!

trap 'kill -TERM "$tracer" "$proxy" 2>/dev/null' TERM INT

until nc -z 127.0.0.1 8080 2>/dev/null; do
    if ! kill -0 "$proxy" 2>/dev/null; then
        echo "ERROR: mitmdump exited during startup"
        cat /tmp/mitm.log
        exit 1
    fi

    sleep 0.2
done

echo "Proxy ready"

wait "$tracer"
wait "$tracer"
wait "$proxy"
