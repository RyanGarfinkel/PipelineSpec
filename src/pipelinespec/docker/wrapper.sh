#!/bin/sh
real="$0.real"

if [ -n "$PSPEC_TRACING" ] || [ ! -d /trace ]; then
    exec "$real" "$@"
fi

export PSPEC_TRACING=1

exec strace -ff -qq -s 512 \
    -e trace=open,openat,openat2,creat,execve,execveat,mkdir,mkdirat,unlink,unlinkat,rmdir,rename,renameat,renameat2 \
    -o /trace/strace "$real" "$@"
