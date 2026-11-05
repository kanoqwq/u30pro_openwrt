#!/usr/bin/env python3
"""Target-root offline checks in an isolated container. No hardware mounts."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import shutil
import runpy

TOP=Path(__file__).resolve().parents[1]
_, WORK, LAYOUT=runpy.run_path(str(TOP/'tools/build-settings.py'))['settings']()
ROOT=WORK/'package-work/u30pro-release/root'
MODEL=runpy.run_path(str(TOP/'tools/ums9632-profile.py'))['selected']()


def run(command, platform_fixture=None):
    # A chroot is not booted: expose only entropy/null, not host hardware.
    uptime=ROOT/'proc/uptime'
    created_uptime=not uptime.exists()
    if created_uptime:uptime.touch()
    mounts=['--mount','type=bind,source=/dev/urandom,target=/target/dev/urandom,readonly',
            '--mount','type=bind,source=/dev/null,target=/target/dev/null',
            '--mount','type=bind,source=/proc/uptime,target=/target/proc/uptime,readonly']
    if platform_fixture:
        mounts+=['--mount','type=bind,source='+str(platform_fixture)+',target=/target/etc/mu300/platform,readonly']
    try:
        return subprocess.check_output(['docker','run','--rm','--platform','linux/arm64',
            '-v',str(ROOT)+':/target',*mounts,'--entrypoint','/bin/sh',LAYOUT['rootfs_image'],
            '-ec',command],text=True)
    finally:
        if created_uptime:uptime.unlink(missing_ok=True)



def modem_checks(include_dashboard=True):
    if os.environ.get('U30PRO_BUILD_LOCKED')!='1':raise ValueError('Use build-release.py run')
    assert (ROOT/'etc/mu300/model').read_text().strip()==MODEL['id']
    assert not (ROOT/'usr/sbin/f50pro-sim-preinit').exists(), 'Retired duplicate pre-CP helper remains'
    run('chroot /target /bin/sh -n /usr/sbin/u30pro-sim-preinit')
    for target,source in {
        'opt/mu300/bin/mu300-modemd':'rootfs/overlay/opt/mu300/bin/mu300-modemd',
        'opt/mu300/lib/data-events.sh':'rootfs/overlay/opt/mu300/lib/data-events.sh',
        'opt/mu300/lib/sms-events.sh':'rootfs/overlay/opt/mu300/lib/sms-events.sh',
        'opt/mu300/lib/modemd-service.sh':'rootfs/overlay/opt/mu300/lib/modemd-service.sh',
        'lib/netifd/proto/mu300cell-v6.sh':'openwrt/overlay/lib/netifd/proto/mu300cell-v6.sh',
    }.items():
        assert (ROOT/target).read_bytes()==(TOP/source).read_bytes(), 'Stale modem input: '+target
    # Native dashboard on target Python/ucode, with private sysfs/netlink/ubus
    # fixtures. Copy only the small sources this fixture actually exercises.
    snapshot=ROOT/'tmp/u30pro-snapshot-test'
    snapshot.mkdir(exist_ok=False)
    try:
        names=['tests/helpers.py','tests/native_dashboard_fixture.py','tests/test_native_dashboard.py','tests/test_modemd.py',
               'rootfs/overlay/opt/mu300/bin/mu300-modemd',
               'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/cell',
               'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/dashboard-network.sh',
               'openwrt/luci-app-mu300/root/usr/share/ucode/mu300/dash.uc',
               'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/hotspot.uc',
               'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/apn.uc',
               'openwrt/luci-app-mu300/root/usr/share/rpcd/acl.d/luci-app-mu300.json']
        names += ['tests/test_cellular_mobility.py','tests/test_data_events.py',
                  'tests/test_sms_events.py','tests/test_registration_scope.py',
                  'rootfs/overlay/opt/mu300/bin/mobile-data',
                  'rootfs/overlay/opt/mu300/bin/mu300-smsd',
                  'rootfs/overlay/opt/mu300/bin/mu300-sim-env',
                  'rootfs/overlay/opt/mu300/lib/data-events.sh',
                  'rootfs/overlay/opt/mu300/lib/sms-events.sh',
                  'rootfs/overlay/opt/mu300/lib/sms-pool.sh',
                  'rootfs/overlay/opt/mu300/lib/modemd-service.sh',
                  'openwrt/overlay/lib/netifd/proto/mu300cell-v6.sh',
                  'openwrt/overlay/lib/netifd/proto/mu300cell.sh']
        for name in names:
            dest=snapshot/name;dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes((TOP/name).read_bytes())
        if include_dashboard:
            print(run('chroot /target /bin/sh -ec "cd /tmp/u30pro-snapshot-test/tests; '
                      'python3 -m unittest test_native_dashboard.NativeSnapshot"'),end='')
        platform_fixture=snapshot/'platform.fixture'
        platform_fixture.write_text('mu300\n')
        print(run('chroot /target /bin/sh -ec "mkdir -p /var/run/ubus; cd /tmp/u30pro-snapshot-test/tests; '
                  'MU300_TEST_SHELLS=sh MU300_TEST_UBUSD=/sbin/ubusd MU300_TEST_UBUS=/bin/ubus python3 -m unittest -v '
                  'test_modemd.ModemdUbus.test_scoped_collect_writes_only_the_requested_sim_cache_and_channel '
                  'test_modemd.ModemdUbus.test_full_round_publishes_serving_and_neighbors_while_identity_is_pending '
                  'test_modemd.ModemdUbus.test_unanswered_core_publishes_error_without_identity_or_number_reads '
                  'test_modemd.ModemdUbus.test_at_status_and_events '
                  'test_cellular_mobility test_data_events test_sms_events test_registration_scope"',platform_fixture),end='')
        print(run('chroot /target /bin/sh -ec "mkdir -p /var/run/ubus; cd /tmp/u30pro-snapshot-test/tests; '
                  'MU300_TEST_SHELLS=sh MU300_TEST_UBUSD=/sbin/ubusd MU300_TEST_UBUS=/bin/ubus python3 -m unittest -v '
                  'test_modemd.ModemdUbus.test_pro_shared_pool_publishes_the_requested_card '
                  'test_modemd.ModemdUbus.test_pro_bearer_events_during_commands_and_idle"'),end='')
    finally:
        shutil.rmtree(snapshot)
        # These unbooted-test directories are empty; never remove live files.
        for path in (ROOT/'tmp/run/ubus',ROOT/'tmp/run'):
            try:path.rmdir()
            except OSError:pass

def main():
    if os.environ.get('U30PRO_BUILD_LOCKED')!='1':raise ValueError('Use build-release.py run')
    flow=runpy.run_path(str(TOP/'tools/stage-flow-offload.py'))
    assert flow['FIXED'] in (ROOT/'usr/share/ucode/fw4.uc').read_text(), 'Stale fw4 topology discovery in prepared root'
    # These are production inputs, never files recovered from a hotfixed device.
    # Compare the assembled root too: source-only syntax tests miss stale staging.
    inputs={
        'opt/mu300/bin/led-status':'rootfs/overlay/opt/mu300/bin/led-status',
        'opt/mu300/bin/mu300-led':'rootfs/overlay/opt/mu300/bin/mu300-led',
        'opt/mu300/bin/mu300-sysd':'rootfs/overlay/opt/mu300/bin/mu300-sysd',
        'opt/mu300/bin/mu300-wifi-band':'rootfs/overlay/opt/mu300/bin/mu300-wifi-band',
        'usr/libexec/unisoc-modem/buttons':'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/buttons',
        'www/luci-static/resources/mu300/buttons.js':'openwrt/luci-app-mu300/htdocs/luci-static/resources/mu300/buttons.js',
        'www/luci-static/resources/view/system/leds.js':'openwrt/overlay/www/luci-static/resources/view/system/leds.js',
        'usr/share/u30pro/battery-log.uc':'devices/u30pro/native/ui/native-control/overlay/usr/share/u30pro/battery-log.uc',
        'usr/sbin/u30pro-battlog':'devices/u30pro/native/ui/native-control/overlay/usr/sbin/u30pro-battlog',
        'etc/init.d/u30pro-battlog':'devices/u30pro/native/ui/native-control/overlay/etc/init.d/u30pro-battlog',
        'www/luci-static/resources/view/mu300/battery.js':'openwrt/luci-app-mu300/htdocs/luci-static/resources/view/mu300/battery.js',

        'opt/mu300/bin/mu300-modemd':'rootfs/overlay/opt/mu300/bin/mu300-modemd',
        'opt/mu300/lib/modemd-service.sh':'rootfs/overlay/opt/mu300/lib/modemd-service.sh',
        'opt/mu300/bin/mu300-at':'rootfs/overlay/opt/mu300/bin/mu300-at',
        'opt/mu300/bin/mu300-dual-radio':'rootfs/overlay/opt/mu300/bin/mu300-dual-radio',
        'opt/mu300/bin/mu300-sim-env':'rootfs/overlay/opt/mu300/bin/mu300-sim-env',
        'opt/mu300/bin/mu300-smsd':'rootfs/overlay/opt/mu300/bin/mu300-smsd',
        'opt/mu300/bin/mu300-usb':'rootfs/overlay/opt/mu300/bin/mu300-usb',
        'opt/mu300/bin/mu300-physical-sim':'rootfs/overlay/opt/mu300/bin/mu300-physical-sim',
        'opt/mu300/bin/mu300-v50-sim':'rootfs/overlay/opt/mu300/bin/mu300-v50-sim',
        'opt/mu300/bin/mu300-data-sim':'rootfs/overlay/opt/mu300/bin/mu300-data-sim',
        'opt/mu300/bin/mobile-data':'rootfs/overlay/opt/mu300/bin/mobile-data',
        'opt/mu300/bin/mu300-sim-radio':'rootfs/overlay/opt/mu300/bin/mu300-sim-radio',
        'opt/mu300/bin/mu300-radio-allowed':'rootfs/overlay/opt/mu300/bin/mu300-radio-allowed',
        'usr/libexec/unisoc-modem/data-sim':'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/data-sim',
        'usr/libexec/unisoc-modem/traffic':'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/traffic',
        'usr/libexec/unisoc-modem/traffic-core.uc':'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/traffic-core.uc',
        'usr/libexec/unisoc-modem/cell':'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/cell',
        'usr/libexec/rpcd/mu300dash':'openwrt/luci-app-mu300/root/usr/libexec/rpcd/mu300dash',
        'www/luci-static/resources/view/mu300/sim.js':'openwrt/luci-app-mu300/htdocs/luci-static/resources/view/mu300/sim.js',
        'www/luci-static/resources/view/mu300/apn.js':'openwrt/luci-app-mu300/htdocs/luci-static/resources/view/mu300/apn.js',
        'usr/libexec/unisoc-modem/device-usb':'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/device-usb',
        'usr/libexec/unisoc-modem/usb-link.uc':'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/usb-link.uc',
        'www/luci-static/resources/mu300/common.js':'openwrt/luci-app-mu300/htdocs/luci-static/resources/mu300/common.js',
        'www/luci-static/resources/mu300/sim-radio.js':'openwrt/luci-app-mu300/htdocs/luci-static/resources/mu300/sim-radio.js',
        'www/luci-static/resources/view/mu300/home.js':'openwrt/luci-app-mu300/htdocs/luci-static/resources/view/mu300/home.js',
        'www/luci-static/resources/view/mu300/device.js':'openwrt/luci-app-mu300/htdocs/luci-static/resources/view/mu300/device.js',
        'www/luci-static/resources/mu300/nfc.js':'openwrt/luci-app-mu300/htdocs/luci-static/resources/mu300/nfc.js',
        'www/luci-static/resources/mu300/roaming.js':'openwrt/luci-app-mu300/htdocs/luci-static/resources/mu300/roaming.js',
        'www/luci-static/resources/view/mu300/locks.js':'openwrt/luci-app-mu300/htdocs/luci-static/resources/view/mu300/locks.js',
        'opt/mu300/lib/roaming.uc':'rootfs/overlay/opt/mu300/lib/roaming.uc',
        'opt/mu300/lib/registration.sh':'rootfs/overlay/opt/mu300/lib/registration.sh',
        'usr/share/ucode/mu300/registration.uc':'rootfs/overlay/usr/share/ucode/mu300/registration.uc',
        'usr/share/ucode/mu300/signal-queue.uc':'rootfs/overlay/usr/share/ucode/mu300/signal-queue.uc',
        'opt/mu300/lib/network-recovery.uc':'openwrt/overlay/opt/mu300/lib/network-recovery.uc',
        'opt/mu300/bin/mu300-network-recovery':'openwrt/overlay/opt/mu300/bin/mu300-network-recovery',
        'usr/libexec/unisoc-modem/roaming':'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/roaming',
        'usr/libexec/rpcd/unisoc-roaming':'openwrt/luci-app-mu300/root/usr/libexec/rpcd/unisoc-roaming',
        'usr/libexec/unisoc-modem/nfc':'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/nfc',
        'usr/libexec/rpcd/unisoc-nfc':'openwrt/luci-app-mu300/root/usr/libexec/rpcd/unisoc-nfc',
        'usr/share/rpcd/acl.d/luci-app-mu300.json':'openwrt/luci-app-mu300/root/usr/share/rpcd/acl.d/luci-app-mu300.json',
        'opt/mu300/bin/mu300-nfc':'rootfs/overlay/opt/mu300/bin/mu300-nfc',
        'opt/mu300/bin/openwrt-wifi-config':'rootfs/overlay/opt/mu300/bin/openwrt-wifi-config',
        'usr/share/ucode/mu300/native-channel.uc':'rootfs/overlay/usr/share/ucode/mu300/native-channel.uc',
        'usr/share/ucode/mu300/carrier.uc':'rootfs/overlay/usr/share/ucode/mu300/carrier.uc',
        'lib/netifd/proto/mu300cell.sh':'openwrt/overlay/lib/netifd/proto/mu300cell.sh',
        'lib/netifd/proto/mu300cell-v6.sh':'openwrt/overlay/lib/netifd/proto/mu300cell-v6.sh',
        'usr/share/u30pro/wallpaper.uc':'devices/u30pro/native/ui/native-control/overlay/usr/share/u30pro/wallpaper.uc',
        'www/luci-static/resources/view/system/u30pro-wallpaper.js':'devices/u30pro/native/ui/native-control/overlay/www/luci-static/resources/view/system/u30pro-wallpaper.js',
        'usr/libexec/unisoc-modem/cpu-voltage.uc':'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/cpu-voltage.uc',
        'usr/libexec/unisoc-modem/cpu-cores.uc':'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/cpu-cores.uc',
        'www/luci-static/resources/mu300/cpu-cores.js':'openwrt/luci-app-mu300/htdocs/luci-static/resources/mu300/cpu-cores.js',
        'usr/libexec/unisoc-modem/action':'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/action',
        'usr/share/ucode/mu300/dash.uc':'openwrt/luci-app-mu300/root/usr/share/ucode/mu300/dash.uc',
        'www/luci-static/resources/view/mu300/cpu.js':'openwrt/luci-app-mu300/htdocs/luci-static/resources/view/mu300/cpu.js',
    }
    # Every native adapter and its menu/catalog files must reach the root too.
    overlay=TOP/'devices/u30pro/overlay'
    for path in overlay.rglob('*'):
        if path.is_file() and not path.is_symlink():
            inputs[str(path.relative_to(overlay))]=str(path.relative_to(TOP))
    for path in (TOP/'devices/f50pro/overlay').rglob('*'):
        if path.is_file():
            inputs[str(path.relative_to(TOP/'devices/f50pro/overlay'))]=str(path.relative_to(TOP))
    if not MODEL['screen']:
        inputs.pop('usr/share/luci/menu.d/u30pro-wallpaper.json',None)
        assert not (ROOT/'usr/share/luci/menu.d/u30pro-wallpaper.json').exists()
    if MODEL['id']!='f50pro':
        inputs.pop('etc/modules.d/61-f50pro-leds',None)
        assert not (ROOT/'etc/modules.d/61-f50pro-leds').exists()
    assert (ROOT/'etc/mu300/model').read_text().strip()==MODEL['id']
    for target,source in inputs.items():
        expected=(TOP/source).read_bytes()
        if expected.startswith(b'#!'):expected=expected.replace(b'\r\n',b'\n')
        assert (ROOT/target).read_bytes()==expected,'Prepared root missed current source: '+source
    print('Current hotfix sources/native adapters/catalogs match prepared root: '+str(len(inputs)))
    scripts=['/opt/mu300/bin/mu300-modemd','/usr/sbin/u30pro-ui-feed','/opt/mu300/bin/mu300-sysd',
        '/usr/sbin/f50pro-leds',
        '/usr/libexec/unisoc-modem/roaming','/opt/mu300/bin/mu300-network-recovery',
        '/usr/share/ucode/mu300/dash.uc','/usr/libexec/unisoc-modem/charge.uc',
        '/opt/mu300/bin/wifi-client','/usr/share/ucode/mu300/wifi-native.uc',
        '/usr/share/u30pro/wallpaper.uc',
        '/usr/libexec/unisoc-modem/cpu-voltage.uc']
    for script in scripts:
        first=(ROOT/script.lstrip('/')).read_bytes().split(b'\n',1)[0]
        if first.startswith(b'#!'):assert b'\r' not in first,script+' has a Windows shebang'
        module = {'/usr/share/ucode/mu300/dash.uc': 'mu300.dash',
                  '/usr/share/ucode/mu300/wifi-native.uc': 'mu300.wifi-native'}.get(script)
        source = "-e \"import * as checked from '"+module+"';\"" if module else script
        run('chroot /target /usr/bin/ucode -c -o /tmp/u30pro-syntax '+source+'; rm -f /target/tmp/u30pro-syntax')
    # No-argument entry exits with usage before any DRM/input access. This
    # checks actual ELF relocation/library resolution, including non-PIE ELF.
    key_source=(TOP/'rootfs/overlay/opt/mu300/bin/mu300-sysd').read_text()
    dispatch=key_source[key_source.index('function on_line(line) {'):key_source.index('\nfunction helper_close()',key_source.index('function on_line(line) {'))]
    key_fixture=ROOT/'tmp/f50pro-key-dispatch.uc'
    try:
        for f50 in (True,False):
            key_fixture.write_text('const F50PRO_KEYS='+('true' if f50 else 'false')+';const KEY_POWER=116;const KEY_WIFI='+('102' if f50 else '138')+';let parts={keys:true,led:false};let seen=[];function press(code,kind){push(seen,[code,kind]);}\n'+dispatch+'\nfor(let line in ["102 short","102 long","116 long","138 short","115 short"])on_line(line);printf("%J",seen);')
            actual=json.loads(run('chroot /target /usr/bin/ucode /tmp/f50pro-key-dispatch.uc'))
            expected=[[102,'short'],[102,'long']] if f50 else [[116,'long'],[138,'short']]
            assert actual==expected,(f50,actual)
    finally:key_fixture.unlink(missing_ok=True)
    print('PASS actual key dispatch: MU3356 KEY_HOME only; other models retain original power/Wi-Fi keys')
    run('set +e; output=$(chroot /target /opt/u30pro/bin/u30pro-panel 2>&1); rc=$?; '
        'set -e; [ "$rc" = 2 ]; case "$output" in *"Usage: u30pro-panel"*) ;; *) printf "%s\\n" "$output"; exit 1;; esac')
    for service in ('mu300-vendor','mu300-hw','mu300-atd','mu300-charge','u30pro-panel','u30pro-watchdog','u30pro-factory','mu300-cpu-driver','u30pro-nfc'):
        run('chroot /target /bin/sh -n /etc/init.d/'+service)
    assert 'iproute2' in run('chroot /target /sbin/ip -V')
    for script in ('/usr/sbin/u30pro-usb-role', '/usr/libexec/unisoc-modem/device-usb', '/opt/mu300/bin/mu300-usb',
                   '/opt/mu300/bin/mu300-physical-sim','/opt/mu300/bin/mu300-u30pro-sim',
                   '/usr/sbin/u30pro-sim-preinit',
                   '/usr/sbin/u30pro-nfc-control','/etc/hotplug.d/net/95-u30pro-nfc',
                   '/usr/libexec/rpcd/unisoc-nfc','/usr/libexec/unisoc-modem/nfc','/opt/mu300/bin/mu300-nfc'):
        assert os.access(ROOT/script.lstrip('/'), os.X_OK), script+' is not executable'
        run('chroot /target /bin/sh -n '+script)
    run('chroot /target /bin/sh -n /opt/mu300/bin/cpu-voltage-platform')
    run('chroot /target /bin/sh -n /opt/mu300/bin/f50pro-card-pair')
    assert (ROOT/'etc/rc.d/S14u30pro-panel').is_symlink()==MODEL['screen']
    assert (ROOT/'etc/rc.d/S11f50pro-leds').is_symlink()==(MODEL['id']=='f50pro')
    assert (ROOT/'etc/rc.d/S99f50pro-led-ready').is_symlink()==(MODEL['id']=='f50pro')
    assert (ROOT/'etc/rc.d/S95f50pro-buttons').is_symlink()==(MODEL['id']=='f50pro')
    assert not (ROOT/'etc/hotplug.d/net/96-f50pro-leds').exists(), 'Retired early Wi-Fi hotplug refresh remains'
    assert not (ROOT/'etc/rc.d/S96f50pro-leds').exists()
    for name in ('mu300-charge','u30pro-battlog'):
        active=any((ROOT/'etc/rc.d').glob('S[0-9][0-9]'+name))
        assert active==MODEL['battery'], 'Wrong battery service policy: '+name
    assert not (ROOT/'etc/rc.d/S95u30pro-panel').is_symlink()
    assert (ROOT/'etc/rc.d/S08mu300-cpu-driver').is_symlink()
    assert (ROOT/'etc/rc.d/S95u30pro-nfc').is_symlink()
    assert (ROOT/'usr/share/u30pro/ui-plugins/nfc.plugin').is_file()
    import hashlib
    runtime=json.loads((WORK/'artifacts/u30pro-runtime/runtime.json').read_text())
    panel=ROOT/'opt/u30pro/bin/u30pro-panel'
    assert hashlib.sha256(panel.read_bytes()).hexdigest()==runtime['files']['u30pro-panel']['sha256']
    nfc=ROOT/'usr/sbin/u30pro-nfc'
    assert hashlib.sha256(nfc.read_bytes()).hexdigest()==runtime['files']['u30pro-nfc']['sha256']
    keys=ROOT/'usr/sbin/mu300-keys'
    assert os.access(keys,os.X_OK), 'Button service input-event helper is missing'
    assert hashlib.sha256(keys.read_bytes()).hexdigest()==runtime['files']['mu300-keys']['sha256']
    run('set +e; output=$(chroot /target /usr/sbin/mu300-keys -Z 2>&1); rc=$?; '
        'set -e; [ "$rc" = 2 ]; case "$output" in *"usage: mu300-keys"*) ;; *) exit 1;; esac')
    encoded=bytes.fromhex(run('chroot /target /usr/sbin/u30pro-nfc encode OpenWrt open').strip())
    assert encoded[0]==3 and encoded[1]==len(encoded)-3
    assert b'application/vnd.wfa.wsc' in encoded and b'OpenWrt' in encoded
    schema=json.loads(run('chroot /target /usr/libexec/rpcd/unisoc-nfc list'))
    assert schema=={'get':{},'set':{'enabled':'String'}}
    # /run is created during real boot. This chroot has not booted; use an
    # owned temporary lock, not the host's runtime directory.
    try:
        reply=json.loads(run('chroot /target /usr/bin/env UNISOC_NFC_LOCK=/tmp/u30pro-nfc-rpc-test.lock /usr/libexec/unisoc-modem/nfc get'))
        expected={'ok':0,'error':'nfc_unavailable'} if MODEL['id']=='f50pro' else {'ok':1,'supported':1,'enabled':1}
        assert reply==expected,reply
    finally:
        (ROOT/'tmp/u30pro-nfc-rpc-test.lock').unlink(missing_ok=True)
    assert 'title=NFC\n' in (ROOT/'usr/share/u30pro/ui-plugins/nfc.plugin').read_text()
    version=(ROOT/'lib/modules').iterdir()
    modules=next(version)
    if MODEL['id']=='f50pro':
        for entry in (ROOT/'etc/modules.d/61-f50pro-leds').read_text().splitlines():
            driver=entry.split()[0]
            assert (modules/(driver+'.ko')).is_file(), 'Missing F50 indicator driver: '+driver
            assert driver+'.ko:' in (modules/'modules.dep').read_text()
        handoff=modules/'f50pro-led-handoff.ko'
        assert 'enabled:bool' in subprocess.check_output(['modinfo','-F','parmtype',str(handoff)],text=True)
        assert not subprocess.check_output(['modinfo','-F','alias',str(handoff)],text=True).strip(), 'F50 handoff must not autoload on U30 Pro'
    # OpenWrt does not load arbitrary USB modaliases in this native root.
    # Validate the profile's boot-loaded OTG drivers and depmod metadata.
    for driver in (ROOT/'etc/modules.d/60-u30pro-host').read_text().splitlines():
        assert (modules/(driver+'.ko')).is_file(), 'Missing host driver: '+driver
        assert driver+'.ko:' in (modules/'modules.dep').read_text(), 'Missing module dependencies: '+driver
    assert (modules/'sprd-cpufreq-v2.ko').is_file()
    assert (modules/'u30pro-sprd-scufreq.ko').is_file()
    assert 'voltage_offset_uv:array of int' in subprocess.check_output(['modinfo','-F','parmtype',str(modules/'sprd-cpufreq-v2.ko')],text=True)
    for fixture in ('cpu_voltage_fixture.sh','u30pro_cpu_voltage.sh'):
        path=ROOT/'tmp'/fixture
        try:
            path.write_bytes((TOP/'tests'/fixture).read_bytes())
            print(run('chroot /target /bin/sh /tmp/'+fixture+' /usr/libexec/unisoc-modem/cpu-voltage.uc'),end='')
        finally:path.unlink(missing_ok=True)
    paths=(ROOT/'opt/mu300/vendor/u30pro/modem/map.tsv').read_text().splitlines()
    assert paths and all(row.split()[1]=='/dev/block/by-name/'+row.split()[0] for row in paths)
    assert not (ROOT/'etc/rc.d/S19u30pro-atd').exists()
    assert not (ROOT/'etc/rc.d/S09mu300-vendor').exists()
    assert not (ROOT/'etc/rc.d/S15mu300-wifi-client').exists()
    assert (ROOT/'etc/rc.d/S08u30pro-factory').is_symlink()
    assert (ROOT/'etc/rc.d/S13mu300-vendor').is_symlink()
    for link in ('S98unisoc-ra-renew','K10unisoc-ra-renew'):
        assert os.readlink(ROOT/'etc/rc.d'/link)=='../init.d/unisoc-ra-renew'
    run('chroot /target /bin/sh -n /etc/init.d/unisoc-ra-renew')
    run('chroot /target /usr/bin/python3 -c "import os,time; fd=os.timerfd_create(time.CLOCK_BOOTTIME, flags=os.TFD_NONBLOCK); os.close(fd)"')
    assert 'mu300cellv6' not in (ROOT/'etc/config/network').read_text()
    assert '/dev/stty_nr0' in (ROOT/'opt/mu300/lib/modemd-service.sh').read_text()
    modem_checks()
    # Repeated snapshots must not exhaust ubusd in the persistent screen feed.
    subprocess.run([sys.executable,str(TOP/'tests/u30pro_bus_lifetime.py')],check=True)
    subprocess.run([sys.executable,str(TOP/'tests/u30pro_display_handoff.py')],check=True)
    subprocess.run([sys.executable,str(TOP/'tests/u30pro_screen_bandwidth.py')],check=True)
    subprocess.run([sys.executable,str(TOP/'tests/u30pro_sim_status.py')],check=True)
    subprocess.run([sys.executable,str(TOP/'tests/u30pro_power_menu.py')],check=True)
    subprocess.run([sys.executable,str(TOP/'tests/u30pro_screen_charge.py')],check=True)
    subprocess.run([sys.executable,str(TOP/'tests/u30pro_wallpaper_scenes.py')],check=True)
    subprocess.run([sys.executable,str(TOP/'tests/u30pro_wallpaper_tiles.py')],check=True)
    subprocess.run([sys.executable,'-m','unittest','discover','-s',str(TOP/'tests'),
                    '-p','test_u30pro_nfc.py'],check=True)
    # Execute the real target ucode/UCI module with an isolated configuration
    # and mocked ubus, never attach a physical wireless interface.
    for source in ('u30pro_wifi_native.uc','u30pro_channels.uc','u30pro_carrier.uc','roaming.uc','signal_queue.uc','f50pro_led.uc'):
        testfile=ROOT/'tmp'/source
        try:
            content=(TOP/'tests'/source).read_bytes()
            for original,target in {
                b'../rootfs/overlay/opt/mu300/lib/roaming.uc':b'/opt/mu300/lib/roaming.uc',
                b'../openwrt/overlay/opt/mu300/lib/network-recovery.uc':b'/opt/mu300/lib/network-recovery.uc',
                b'../rootfs/overlay/usr/share/ucode/mu300/signal-queue.uc':b'/usr/share/ucode/mu300/signal-queue.uc',
            }.items():content=content.replace(original,target)
            testfile.write_bytes(content)
            print(run('chroot /target /usr/bin/ucode /tmp/'+source),end='')
        finally:
            testfile.unlink(missing_ok=True)
            shutil.rmtree(ROOT/'tmp/u30pro-wifi-native-fixture',ignore_errors=True)
    lifecycle=ROOT/'tmp/f50pro-led-lifecycle.uc'
    try:
        daemon=(TOP/'devices/f50pro/overlay/usr/sbin/f50pro-leds').read_text()
        daemon='\n'.join(line for line in daemon.splitlines() if not line.startswith(('#!','import ')))
        lifecycle.write_text("import { colours,output,boot_colours } from 'mu300.f50pro-led';\n"+
                             (TOP/'tests/f50pro_led_lifecycle.uc').read_text()+'\n'+daemon+'\n')
        for case in ('boot','ready','disabled','race','wireless'):
            print(run('chroot /target /usr/bin/ucode /tmp/f50pro-led-lifecycle.uc '+case),end='')
    finally:
        lifecycle.unlink(missing_ok=True)
    # Charge policy uses a synthetic battery/charger, never host /sys.
    test=ROOT/'tmp/u30pro-charge-test';test.mkdir(exist_ok=False)
    try:
        (test/'config').mkdir();(test/'battery/u30pro-battery').mkdir(parents=True)
        (test/'battery/u30pro-charger-master').mkdir()
        for name,value in {'present':'1','capacity':'85','status':'Charging'}.items():
            (test/'battery/u30pro-battery'/name).write_text(value)
        (test/'battery/u30pro-charger-master/charge_behaviour').write_text('auto')
        (test/'config/mu300-charge').write_text("config policy 'main'\noption enabled '1'\noption start '70'\noption stop '80'\n")
        env='MU300_CHARGE_DEVICE=u30pro MU300_CHARGE_MODEL=u30pro MU300_CHARGE_SYS=/tmp/u30pro-charge-test/battery MU300_CHARGE_CONFIG=/tmp/u30pro-charge-test/config MU300_CHARGE_STATE=/tmp/u30pro-charge-test/state.json '
        reply=run('chroot /target /usr/bin/env '+env+' /usr/bin/ucode /usr/libexec/unisoc-modem/charge.uc apply')
        value=json.loads(reply)
        assert value['ok'] and value['supported'],value
        assert (test/'battery/u30pro-charger-master/charge_behaviour').read_text()=='inhibit-charge'
        (test/'battery/u30pro-battery/capacity').write_text('65')
        run('chroot /target /usr/bin/env '+env+' /usr/bin/ucode /usr/libexec/unisoc-modem/charge.uc apply')
        assert (test/'battery/u30pro-charger-master/charge_behaviour').read_text()=='auto'
        fake=run('chroot /target /usr/bin/env '+env.replace('MU300_CHARGE_MODEL=u30pro','MU300_CHARGE_MODEL=f50pro')+' /usr/bin/ucode /usr/libexec/unisoc-modem/charge.uc get')
        assert not json.loads(fake)['supported'],'A no-battery product must not offer charging controls'
    finally:
        shutil.rmtree(test)
    print('Target ucode compile, panel libraries, services, logical NV map and native charge hysteresis: PASS; no hardware access')


if __name__=='__main__':
    if sys.argv[1:]==['--modem-only']:modem_checks(include_dashboard=False)
    elif len(sys.argv)==1:main()
    else:raise SystemExit('Usage: test-u30pro-root.py [--modem-only]')
