"""Real ucode/uloop with process substitutes; no target devices or partitions."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

TOP = Path(__file__).resolve().parents[1]
OVERLAY = TOP/'devices/u30pro/overlay'
IMAGE = 'mu300-openwrt-ra-native:25.12.5'
GATE = '/source/devices/u30pro/overlay/usr/libexec/u30pro-charge-mode'


@unittest.skipUnless(os.name == 'posix' and shutil.which('docker'), 'Linux and existing OpenWrt test image')
class ChargeBoot(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pro-charge-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for directory in ('run/mu300', 'etc/config', 'etc/mu300', 'proc/device-tree/chosen', 'tmp', 'mnt/mu300-disk'):
            (self.root/directory).mkdir(parents=True)
        (self.root/'etc/mu300/model').write_text('u30pro\n')
        (self.root/'etc/config/mu300-charge').write_text("config charge 'main'\n option power_on '0'\n")
        (self.root/'proc/cmdline').write_text('console=ttyS1\n modem=shutdown sprdboot.mode=charger\n')
        (self.root/'proc/device-tree/chosen/bootargs').write_bytes(b'androidboot.mode=charger\0')
        self.sink=self.root/'sys/class/extcon/extcon7'
        (self.sink/'cable.3').mkdir(parents=True)
        (self.sink/'name').write_text('64600000.spi:pmic@1:typec@380\n')
        (self.sink/'cable.3/state').write_text('1\n')
        # These must survive all charging transitions byte for byte.
        self.saved = {
            'etc/config/unisoc_modem': b"radio_permissions='0 1'\ndata_sim=1\n",
            'etc/config/wireless': b'user ssid, passphrase, disabled=1, relay enabled',
            'etc/unisoc-bluetooth/config.json': b'{"autostart":true,"alias":"mine"}',
            'etc/mu300/default-boot': b'linux\n',
        }
        for name, value in self.saved.items():
            (self.root/name).parent.mkdir(parents=True,exist_ok=True)
            (self.root/name).write_bytes(value)
        self.stub('opt/mu300/bin/mu300-next-boot', 'echo "rearm $*" >> "$U30PRO_CHARGE_ROOT/run/log"')
        self.stub('usr/libexec/unisoc-modem/charge', 'echo \'{"ok":true,"enabled":false,"paused":false}\'')
        self.stub('opt/u30pro/bin/u30pro-panel', '''
echo "display $*" >> "$U30PRO_CHARGE_ROOT/run/log"
trap 'echo display-stopped >> "$U30PRO_CHARGE_ROOT/run/log"; exit' TERM
while :; do sleep 1; done
''')
        self.stub('usr/sbin/mu300-keys', '''
echo "keys $*" >> "$U30PRO_CHARGE_ROOT/run/log"
sleep 1
exit 0
''')
        self.stub('bin/kill', 'echo "signal $1" >> "$U30PRO_CHARGE_ROOT/run/log"; exec /bin/kill "$@"')
        for name in ('sync', 'mount'):
            self.stub('bin/'+name, 'echo "'+name+' $*" >> "$U30PRO_CHARGE_ROOT/run/log"')
        # Killing the ucode process represents the kernel not returning.
        self.stub('sbin/poweroff', 'echo "poweroff $*" >> "$U30PRO_CHARGE_ROOT/run/log"; kill -KILL "$PPID"')

    def stub(self, name, body):
        path = self.root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('#!/bin/sh\n'+body+'\n'); path.chmod(0o755)

    def call(self, timeout=None):
        container = 'pro-charge-' + self.root.name
        command = ['docker', 'run', '--rm', '--init', '--name', container, '-v', str(TOP)+':/source:ro',
                   '-v', str(self.root)+':/fixture', '-v',
                   str(OVERLAY/'usr/share/ucode/mu300/charger-boot.uc')+':/usr/share/ucode/mu300/charger-boot.uc:ro',
                   '-e', 'U30PRO_CHARGE_ROOT=/fixture', IMAGE]
        command += ['ucode', GATE]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout or 15)
        except subprocess.TimeoutExpired as error:
            subprocess.run(['docker','rm','-f',container],check=True,capture_output=True)
            if not timeout: raise
            result = subprocess.CompletedProcess(command,-9,
                (error.stdout or b'').decode(),(error.stderr or b'').decode())
        for name, value in self.saved.items(): self.assertEqual((self.root/name).read_bytes(), value, name)
        return result

    def events(self):
        path = self.root/'run/log'
        return path.read_text().splitlines() if path.exists() else []

    def test_normal_other_product_automatic_and_failsafe_never_start_gate(self):
        for kind in ('normal', 'f50pro', 'automatic', 'failsafe', 'already-booted'):
            with self.subTest(kind=kind):
                (self.root/'proc/cmdline').write_text('sprdboot.mode=normal' if kind == 'normal' else 'sprdboot.mode=charger')
                (self.root/'proc/device-tree/chosen/bootargs').write_text('')
                (self.root/'etc/mu300/model').write_text('f50pro' if kind == 'f50pro' else 'u30pro')
                (self.root/'etc/config/mu300-charge').write_text("config charge 'main'\n option power_on '"+('1' if kind == 'automatic' else '0')+"'\n")
                (self.root/'tmp/.failsafe').unlink(missing_ok=True)
                if kind == 'failsafe': (self.root/'tmp/.failsafe').touch()
                (self.root/'run/u30pro-cp-started').unlink(missing_ok=True)
                if kind == 'already-booted': (self.root/'run/u30pro-cp-started').touch()
                p = self.call(); self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(self.events(), [])

    def test_hold_exits_renderer_before_normal_services_and_keeps_settings(self):
        p = self.call(); self.assertEqual(p.returncode, 0, p.stderr)
        rows = self.events()
        self.assertIn('display charger', rows)
        self.assertIn('keys -c -p /fixture/sys/class/power_supply/u30pro-charger-master/online -a /fixture/sys/class/extcon/extcon7/cable.3/state -l 2000', rows)
        self.assertIn('display-stopped', rows)
        self.assertFalse((self.root/'run/mu300/charging-boot').exists())
        self.assertEqual(json.loads((self.root/'run/mu300/charging-boot.json').read_text())['reason'],'boot')
        self.assertEqual(rows[0], 'rearm --rearm')
        self.assertFalse(any('poweroff' in row for row in rows))

    def test_unplug_stops_children_flushes_root_then_backing_and_powers_off(self):
        self.stub('usr/sbin/mu300-keys', 'sleep 1; exit 3')
        p = self.call(); self.assertNotEqual(p.returncode, 0)
        rows = self.events()
        self.assertLess(rows.index('display-stopped'), rows.index('sync '))
        self.assertEqual(rows[-5:], ['sync ', 'mount -o remount,ro /',
                                    'mount -o remount,ro /mnt/mu300-disk', 'sync ', 'poweroff -f'])

    def test_missing_typec_is_explicit_and_does_not_use_old_unplug_logic(self):
        (self.sink/'cable.3/state').unlink()
        p=self.call()
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('Type-C sink signal unavailable',p.stderr)
        self.assertEqual(self.events(),[])
        self.assertFalse((self.root/'run/mu300/charging-boot').exists())

    def test_missing_key_interface_continues_boot_without_reboot_loop(self):
        self.stub('usr/sbin/mu300-keys', 'sleep 1; exit 1')
        p = self.call(); self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('input unavailable', p.stderr)
        self.assertIn('display-stopped', self.events())
        self.assertFalse(any('poweroff' in row for row in self.events()))

    def test_renderer_failure_does_not_disable_power_key(self):
        self.stub('opt/u30pro/bin/u30pro-panel', 'exit 1')
        p = self.call(); self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('display ended', p.stderr)
        self.assertFalse((self.root/'run/mu300/charging-boot').exists())

    def test_slow_renderer_is_reaped_before_rcs_continues(self):
        self.stub('opt/u30pro/bin/u30pro-panel', "trap '' TERM; while :; do sleep 1; done")
        p = self.call(); self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('signal -KILL', self.events())

    def test_limit_worker_is_stopped_on_handoff_and_default_has_none(self):
        self.stub('usr/libexec/unisoc-modem/charge', 'echo \'{"ok":true,"enabled":true,"paused":false}\'')
        self.stub('usr/bin/ucode', '''
echo limits >> "$U30PRO_CHARGE_ROOT/run/log"
trap 'echo limits-stopped >> "$U30PRO_CHARGE_ROOT/run/log"; exit' TERM
while :; do sleep 1; done
''')
        p = self.call(); self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('limits-stopped', self.events())

    def test_late_battery_keeps_requested_limit_or_pause_watcher(self):
        self.stub('usr/libexec/unisoc-modem/charge','echo \'{"ok":false,"error":"charge_unavailable"}\'')
        self.stub('usr/bin/ucode','echo limits >> "$U30PRO_CHARGE_ROOT/run/log"; sleep 1')
        for option in ('enabled','paused','full_once'):
            with self.subTest(option=option):
                (self.root/'etc/config/mu300-charge').write_text("config charge 'main'\n option power_on '0'\n option "+option+" '1'\n")
                (self.root/'run/log').unlink(missing_ok=True)
                p=self.call();self.assertEqual(p.returncode,0,p.stderr)
                self.assertIn('limits',self.events())

    def test_power_supply_hotplug_handles_pro_limits_and_skips_batteryless_models(self):
        source=(TOP/'openwrt/luci-app-mu300/root/etc/hotplug.d/power_supply/75-mu300-charge').read_text()
        for name in ('run/mu300/device','etc/mu300/model'):
            source=source.replace('/'+name,str(self.root/name))
        source=source.replace('/run/mu300-charge.json',str(self.root/'run/mu300-charge.json'))
        source=source.replace('/usr/libexec/unisoc-modem/charge',str(self.root/'bin/charge'))
        self.stub('bin/charge','echo apply >> "$HOTPLUG_LOG"')
        self.stub('bin/ubus','echo event >> "$HOTPLUG_LOG"')
        self.stub('bin/uci', '''case "$*" in
*.enabled) echo "${POLICY_ENABLED:-0}";;
*.paused) echo "${POLICY_PAUSED:-0}";;
*.full_once) echo "${POLICY_FULL_ONCE:-0}";;
esac''')
        for board,model in (('u30pro','u30pro'),('u30air','u30air'),('u30pro','f50pro'),('f50','f50'),('v50','v50')):
            (self.root/'run/mu300/device').write_text(board)
            (self.root/'etc/mu300/model').write_text(model)
            for option in ('none','enabled','paused','full_once'):
                for action in ('add','change','remove'):
                    log=self.root/'run/hotplug.log';log.unlink(missing_ok=True)
                    env=dict(os.environ,PATH=str(self.root/'bin')+':'+os.environ['PATH'],
                             HOTPLUG_LOG=str(log),ACTION=action)
                    if option!='none':env['POLICY_'+option.upper()]='1'
                    p=subprocess.run(['sh','-c',source],env=env,capture_output=True,text=True,timeout=3)
                    self.assertEqual(p.returncode,0,p.stderr)
                    wanted=model in ('u30pro','u30air') and option!='none' and action!='remove'
                    self.assertEqual(log.read_text().splitlines() if log.exists() else [],['apply','event'] if wanted else [],(board,model,option,action))

    def test_failed_poweroff_never_falls_through_to_radio_startup(self):
        self.stub('usr/sbin/mu300-keys', 'sleep 1; exit 3')
        self.stub('sbin/poweroff', 'echo "poweroff $*" >> "$U30PRO_CHARGE_ROOT/run/log"')
        p = self.call(timeout=6); self.assertNotEqual(p.returncode, 0)
        self.assertGreaterEqual(self.events().count('poweroff -f'), 2, p.stderr+p.stdout+repr(self.events()))
        self.assertNotIn('continuing normal', p.stderr)

    def test_waiting_gate_is_idle_and_leaves_all_saved_service_states_alone(self):
        self.stub('usr/sbin/mu300-keys', 'sleep 30; exit 0')
        self.stub('opt/u30pro/bin/u30pro-panel', 'sleep 30')
        container='pro-charge-idle-'+self.root.name
        command=['docker','run','--rm','--init','--name',container,'-d',
                 '-v',str(TOP)+':/source:ro','-v',str(self.root)+':/fixture',
                 '-v',str(OVERLAY/'usr/share/ucode/mu300/charger-boot.uc')+':/usr/share/ucode/mu300/charger-boot.uc:ro',
                 '-e','U30PRO_CHARGE_ROOT=/fixture',IMAGE,'ucode',GATE]
        subprocess.run(command,check=True,capture_output=True)
        try:
            time.sleep(2)
            pid=subprocess.check_output(['docker','exec',container,'pidof','ucode'],text=True).strip()
            def ticks():
                raw=subprocess.check_output(['docker','exec',container,'cat','/proc/'+pid+'/stat'],text=True)
                fields=raw[raw.rfind(')')+2:].split()
                return int(fields[11])+int(fields[12])
            before=ticks();time.sleep(4);after=ticks()
            self.assertLessEqual(after-before,1)
            self.assertTrue((self.root/'run/mu300/charging-boot').exists())
            self.assertEqual(self.events().count('rearm --rearm'),1)
            for name,value in self.saved.items():self.assertEqual((self.root/name).read_bytes(),value)
        finally:
            subprocess.run(['docker','rm','-f',container],check=True,capture_output=True)


if __name__ == '__main__': unittest.main()
