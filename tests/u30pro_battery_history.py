"""Real ucode battery history against synthetic sysfs; no hardware access."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

TOP = Path(__file__).resolve().parents[1]
NATIVE = TOP/'devices/u30pro/native'
LIB = NATIVE/'ui/native-control/overlay/usr/share/u30pro/battery-log.uc'


@unittest.skipUnless(os.name == 'posix', 'target ucode runs in the existing build container')
class BatteryHistory(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bat = self.root/'sys/class/power_supply/u30pro-battery'
        self.chg = self.root/'sys/class/power_supply/u30pro-charger-master'
        self.bat.mkdir(parents=True); self.chg.mkdir()
        (self.root/'etc/mu300/battery').mkdir(parents=True)
        (self.root/'run').mkdir()
        (self.root/'mounted').write_text('1')
        self.write(self.bat, type='Battery', present=1, capacity=75, current_now=-500000,
                   voltage_now=4000000, temp=300)
        self.write(self.chg, online=0, status='Discharging')
        self.minute = int(time.time())//60*60

    def write(self, directory, **values):
        for key, value in values.items(): (directory/key).write_text(str(value))

    def records(self, entries):
        (self.root/'etc/mu300/battery/battery.csv').write_text(''.join(
            f'{t},{p},{ma},{ma*4},4000,{s},300\n' for t,p,ma,s in entries))

    def run_ucode(self, script):
        command = ['docker','run','--rm','--platform','linux/arm64',
            '-v',str(LIB)+':/usr/share/u30pro/battery-log.uc:ro',
            '-v',str(self.root)+':/fixture','-e','U30PRO_BATTLOG_ROOT=/fixture',
            '--entrypoint','/usr/bin/ucode',os.environ.get('U30PRO_ROOTFS_IMAGE','u30pro-rootfs:25.12.5'),'-e',
            "import * as b from '/usr/share/u30pro/battery-log.uc'; b.init(); "+script]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        return json.loads(result.stdout)

    def history(self, key='24h'):
        return self.run_ucode(f'printf("%J", b.history("{key}", 120));')

    def test_live_state_and_units_do_not_wait_for_history(self):
        data = self.history()
        self.assertTrue(data['present']); self.assertIsNone(data['first'])
        self.assertEqual(data['current']['pct'],75)
        self.assertEqual(data['current']['ma'],-500)
        self.assertEqual(data['current']['mw'],-2000)
        self.assertEqual(data['current']['mv'],4000)
        self.assertIsNone(data['estimate_s'])

    def test_absent_battery_is_not_exposed(self):
        self.write(self.bat,present=0)
        self.assertFalse(self.history()['present'])
        (self.bat/'present').unlink(); (self.bat/'type').unlink()
        self.assertFalse(self.history()['present'])

    def test_continuous_discharge_has_an_estimate(self):
        self.records([(self.minute-1200+i*60,80-i//4,-500,'D') for i in range(21)])
        data=self.history('full')
        self.assertEqual(data['estimate_s'],18000)
        self.assertGreater(data['stats']['on_battery_s'],1000)
        self.assertEqual(len((self.root/'run/u30pro-battery/screen').read_text().splitlines()),16)
        self.assertFalse((self.root/'mnt/data').exists())

    def test_charging_flat_gauge_and_short_runs_have_no_estimate(self):
        self.records([(self.minute-1200+i*60,75,-500,'D') for i in range(21)])
        self.assertIsNone(self.history()['estimate_s'])
        self.records([(self.minute-300+i*60,80-i,-500,'D') for i in range(6)])
        self.assertIsNone(self.history()['estimate_s'])
        self.write(self.chg,online=1,status='Charging')
        self.write(self.bat,current_now=1000000)
        data=self.history()
        self.assertIsNone(data['estimate_s']); self.assertEqual(data['current']['st'],'C')
        self.assertEqual(data['current']['mw'],4000)

    def test_shutdown_gap_is_blank_and_not_used_for_estimate(self):
        self.records([(self.minute-1200+i*60,80-i//4,-500,'D') for i in range(11)]+
                     [(self.minute-60,76,-500,'D'),(self.minute,75,-500,'D')])
        data=self.history('full')
        self.assertIsNone(data['estimate_s'])
        self.assertIn(None,data['pct'])
        self.assertEqual(data['stats']['on_battery_s'],13*60)

    def test_retention_reload_and_invalid_range(self):
        self.records([(self.minute-11*86400,100,-500,'D'),(self.minute-60,75,-500,'D')])
        data=self.history()
        self.assertEqual(data['first'],self.minute-60)
        self.assertEqual(len((self.root/'etc/mu300/battery/battery.csv').read_text().splitlines()),1)
        self.assertEqual(self.history()['first'],data['first'])
        self.assertIn('error',self.history('1y'))

    def test_native_ranges_energy_screen_and_pending_store(self):
        test = NATIVE/'tests/test_battery_log.uc'
        result = subprocess.run(['docker','run','--rm','--platform','linux/arm64',
            '-v',str(LIB)+':/usr/share/u30pro/battery-log.uc:ro',
            '-v',str(test)+':/native-test.uc:ro','-v',str(self.root)+':/fixture',
            '-e','U30PRO_BATTLOG_ROOT=/fixture','--entrypoint','/usr/bin/ucode',
            os.environ.get('U30PRO_ROOTFS_IMAGE','u30pro-rootfs:25.12.5'),'/native-test.uc'],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('passed',result.stdout)

    def test_luci_reads_the_menu_with_its_actual_stream_parser(self):
        menu=TOP/'openwrt/luci-app-mu300/root/usr/share/luci/menu.d/luci-app-mu300.json'
        script='import { open } from "fs"; let m=json(open("/menu.json","r")); printf("%J",m["admin/modem/battery"]);'
        result=subprocess.run(['docker','run','--rm','--platform','linux/arm64','-v',str(menu)+':/menu.json:ro',
            '--entrypoint','/usr/bin/ucode',os.environ.get('U30PRO_ROOTFS_IMAGE','u30pro-rootfs:25.12.5'),'-e',script],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        entry=json.loads(result.stdout)
        self.assertEqual(entry['action']['path'],'mu300/battery')
        self.assertEqual(entry['depends']['fs'],{'/run/u30pro-battery/present':'file'})

    def test_native_screen_consumer_reads_the_production_output(self):
        self.records([(self.minute-1200+i*60,80-i//4,-500,'D') for i in range(21)])
        self.history()
        (self.root/'battery-screen').write_bytes((self.root/'run/u30pro-battery/screen').read_bytes())
        source=self.root/'screen.c'
        source.write_text('#define UI_HOST\n#define UI_RUN '+json.dumps(str(self.root))+'\n'
            '#define main unused_screen_main\n#include "u30pro_ui.c"\n#undef main\n#include <assert.h>\n'
            'int main(void){ batlog_load(); assert(bh_ok); '
            'assert(bh[BH_FULL].pct_now==75); assert(bh[BH_DAY].n>0); '
            'assert(bh[BH_FULL].onbat_s==1260); return 0;}\n')
        binary=self.root/'screen-test'
        subprocess.run(['gcc','-std=gnu11','-O1','-I',str(NATIVE/'tools'),str(source),'-lm','-o',str(binary)],
                       check=True,capture_output=True,timeout=60)
        subprocess.run([str(binary)],check=True,capture_output=True,timeout=10)


if __name__ == '__main__': unittest.main()
