#!/bin/sh
# Host-only integration checks. All modem bytes go to synthetic PTYs.
set -eu
[ "${U30PRO_BUILD_LOCKED:-}" = 1 ] || { echo 'Use tools/build-release.py run' >&2; exit 2; }
top=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
native=$top/devices/u30pro/native
testdir=$(mktemp -d "${TMPDIR:?runner supplies owned temporary storage}/u30pro-native.XXXXXX")
trap 'rm -rf -- "$testdir"' EXIT HUP INT TERM
python3 "$top/tools/u30pro-build.py" check --sources-only
python3 "$top/tests/u30pro_port.py"
python3 "$top/tests/u30pro_sdio_clock.py"
python3 "$top/tests/u30pro_sdio_pipeline.py"
python3 "$top/tests/u30pro_sdio_recovery.py"
python3 "$top/tests/u30pro_sipa_flow.py"
python3 "$top/tests/u30pro_restart.py"
python3 "$top/openwrt/tests/ra-renew.py"
python3 "$top/openwrt/tests/ttl.py"
python3 -m unittest discover -s "$top/tests" -p test_u30pro_package_state.py
python3 -m unittest discover -s "$top/tests" -p test_u30pro_public_build.py
python3 "$top/tests/u30pro_navigation.py"
python3 "$top/tests/u30pro_sim_status.py"
python3 "$top/tests/u30pro_screen_sms.py"
python3 "$top/tests/u30pro_power_events.py"
python3 "$top/tests/u30pro_screen_charge.py"
python3 "$top/tests/u30pro_wallpaper_scenes.py"
python3 "$top/tests/u30pro_wallpaper_tiles.py"
python3 "$top/tests/u30pro_high_refresh.py"
python3 "$top/tests/u30pro_glass_colour.py"
python3 "$top/tests/u30pro_uninstall_storage.py"
test_busybox=$(python3 -c 'import runpy,sys; print(runpy.run_path(sys.argv[1])["settings"]()[2]["busybox"])' "$top/tools/build-settings.py")
OPENWRT_TEST_BUSYBOX="$test_busybox" python3 -m unittest discover -s "$top/installer/tests" -p test_native_worker.py
python3 "$top/tests/u30pro_battery_history.py"
python3 "$top/tests/u30pro_charge_sources.py"
python3 "$top/tests/u30pro_usb_roles.py"
python3 "$top/tests/test_usb_link.py"
python3 -m unittest discover -s "$top/tests" -p test_u30pro_nfc.py
python3 -m unittest discover -s "$top/tests" -p test_nfc_dashboard.py
python3 -m unittest discover -s "$top/tests" -p test_v50_sim.py
python3 -m unittest discover -s "$top/tests" -p test_u30pro_cards.py
python3 -m unittest discover -s "$top/tests" -p test_f50pro_cards.py
PYTHONPATH="$top/tests" python3 -m unittest test_sim_radio test_u30_dsds test_data_sim test_dual_radio
# The production native tools use Zig/Clang, not GCC-specific diagnostics.
cc=${CC:-clang}
"$cc" -std=gnu11 -O2 -Wall -Wextra -Werror -DATD_TEST "$native/tools/u30pro_atd.c" -o "$testdir/atd"
"$cc" -std=gnu11 -O2 -Wall -Wextra -Werror "$native/tools/u30pro_atc.c" -o "$testdir/atc"
"$cc" -std=gnu11 -O2 -Wall -Wextra -Werror -DCELL_TEST "$native/tools/u30pro_celld.c" -o "$testdir/celld"
python3 "$native/tests/test_atd.py" "$testdir/atd" "$testdir/atc"
python3 "$native/tests/test_cellular_native.py" "$testdir/celld"
python3 "$native/tests/test_charger.py"
