FROM alpine:3.23

RUN apk add --no-cache bpftrace mitmproxy

COPY trace.bt legacy.bt entrypoint.sh addon.py /pspec/
RUN chmod +x /pspec/entrypoint.sh && mkdir -p /pspec/run /pspec/mitm

ENTRYPOINT ["/pspec/entrypoint.sh"]
