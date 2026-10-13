FROM catthehacker/ubuntu:act-latest AS build

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*

COPY envhook.c /envhook.c
RUN gcc -shared -fPIC -O2 -o /envhook.so /envhook.c -ldl

FROM catthehacker/ubuntu:act-latest

COPY --from=build /envhook.so /pspec/envhook.so

RUN apt-get update \
    && apt-get install -y --no-install-recommends strace \
    && rm -rf /var/lib/apt/lists/*

COPY --chmod=755 wrapper.sh /usr/local/bin/pspec-wrapper

RUN for name in bash node; do \
        real="$(command -v $name)" \
        && mv "$real" "$real.real" \
        && cp /usr/local/bin/pspec-wrapper "$real"; \
    done
