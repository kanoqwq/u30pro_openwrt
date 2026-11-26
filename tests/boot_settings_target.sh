#!/bin/sh
# The retained prepared root is read-only; /mnt and /dev are private tmpfs mounts.
set -eu
# These tests only redirect output here; a regular scratch sink needs no devices.
: > /target/dev/null
chmod 666 /target/dev/null
if [ "${MU300_TEST_PROC:-0}" = 1 ]; then
    # Card transactions use uptime for transient cache generations. Tests mount
    # a private /proc directory, never edit the retained runtime or real procfs.
    printf '12345.67 10000.00\n' > /target/proc/uptime
fi
exec chroot "$@"
