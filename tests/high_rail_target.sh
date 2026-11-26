#!/bin/sh
# Read-only retained root. /tmp and /dev are disposable container tmpfs mounts.
set -eu
mkdir -p /target/tmp/run
: > /target/dev/null
chmod 666 /target/dev/null
exec chroot "$@"
