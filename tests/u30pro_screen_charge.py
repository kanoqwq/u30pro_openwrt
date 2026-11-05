"""Screen manual-pause policy and real action script regression; no device access."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

TOP = Path(__file__).resolve().parents[1]
NATIVE = TOP/'devices/u30pro/native/tools'
CONTROL = TOP/'devices/u30pro/overlay/usr/sbin/u30pro-panel-control'

@unittest.skipUnless(os.name == 'posix', 'POSIX native screen and shell fixtures')
class ScreenCharge(unittest.TestCase):
    def test_actual_screen_limit_resume_errors_and_late_completions(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            charger = base/'sys/class/power_supply/u30pro-charger-master'
            charger.mkdir(parents=True)
            (charger/'online').write_text('1')
            (charger/'charge_behaviour').write_text('auto [inhibit-charge]')
            source = r'''#define UI_HOST
#define UI_RUN "TEST_RUN"
#define UI_SYSFS "TEST_RUN"
#define main simulator_main
#include "u30pro_ui.c"
#undef main
#include <assert.h>
int main(void) {
 ui_init_canvases();g_ms=vclock=10000;D.bat_ok=1;D.bat_pct=90;
 feed_set("chg_control_ok","1");feed_set("chg_bypass","0");feed_set("chg_limited","1");
 // Automatic limit inhibition must never become a manually enabled switch.
 collect_charger();assert(D.chg_online && !D.chg_bypass && D.chg_limited);
 page_power(&scr);
 assert(gx_has_all(FN14,"已按上限暂停充电等待恢复充电"));
 assert(gx_has_all(FN16,"直供电已开启关闭充电设置失败请重试忙稍后暂不可用保存服务应用正在"));
 do_action(H_BYPASS);assert(bypass_busy_until && !D.chg_bypass);
 unsigned token=bypass_request;do_action(H_BYPASS);assert(bypass_request==token);
 assert(!strcmp(toast.msg,"正在应用充电设置"));
 bypass_complete(token,1,1,1,0,0,"");assert(D.chg_bypass && !bypass_busy_until);
 collect_charger();assert(D.chg_bypass);
 // Resume at the limit changes manual policy only. Hardware remains inhibited.
 do_action(H_BYPASS);token=bypass_request;
 bypass_complete(token,1,1,0,1,0,"");
 collect_charger();assert(!D.chg_bypass && D.chg_limited && !bypass_busy_until);
 assert(!strcmp(toast.msg,"直供电已关闭"));
 for(int i=0;i<3;i++){collect_charger();assert(!D.chg_bypass);}
 // Busy/apply/reload errors never announce success or flip policy optimistically.
 const char *errors[]={"charge_busy","charge_apply_failed","charge_reload_failed"};
 for(int i=0;i<3;i++){
   do_action(H_BYPASS);bypass_complete(bypass_request,0,0,0,0,0,errors[i]);
   assert(!bypass_busy_until && !D.chg_bypass && toast.col==C_BAD);
 }
 do_action(H_BYPASS);unsigned old=bypass_request;
 g_ms=bypass_busy_until;detect_events();assert(!bypass_busy_until && toast.col==C_BAD);
 do_action(H_BYPASS);token=bypass_request;
 bypass_complete(old,1,1,1,0,0,"");assert(bypass_busy_until && !D.chg_bypass);
 bypass_complete(token,1,1,0,0,1,"");assert(!bypass_busy_until && !D.chg_bypass && D.chg_pending);
 // Web policy updates, including pause while unplugged, remain authoritative.
 feed_set("chg_bypass","1");collect_charger();assert(D.chg_bypass);
 feed_set("chg_bypass","0");collect_charger();assert(!D.chg_bypass);
 D.chg_control_ok=0;token=bypass_request;do_action(H_BYPASS);assert(token==bypass_request && !bypass_busy_until);
 D.chg_control_ok=1;D.chg_paused=1;do_action(H_BYPASS);assert(token==bypass_request && !bypass_busy_until);
 return 0;
}
'''.replace('TEST_RUN', str(base))
            (base/'test.c').write_text(source)
            compiled=subprocess.run(['gcc','-std=gnu11','-O1','-I',str(NATIVE),str(base/'test.c'),'-lm','-o',str(base/'test')],capture_output=True,text=True)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            result=subprocess.run([str(base/'test')],capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(result.stdout.count('charge-resume'),1)

    def test_real_controller_checks_json_even_when_backend_exit_is_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            def program(name,body):
                target=base/name;target.write_text(body);target.chmod(0o755);return target
            owner=program('owner', '#!/bin/sh\necho "$REPLY"\nexit "${OWNER_EXIT:-0}"\n')
            program('jsonfilter', '#!/usr/bin/env python3\nimport json,sys\ntry: print(str(json.load(sys.stdin)["ok"]).lower())\nexcept Exception: sys.exit(1)\n')
            program('ubus', '#!/usr/bin/env python3\nimport json,os,sys\njson.dump(sys.argv[1:],open(os.environ["CALLS"],"w"))\n')
            control=base/'control';control.write_text(CONTROL.read_text().replace('/usr/libexec/unisoc-modem/charge',str(owner)))
            env=dict(os.environ,PATH=str(base)+':'+os.environ['PATH'],CALLS=str(base/'calls'))
            success=dict(ok=True,available=True,paused=False,reason='limit',pending=False)
            for action in ('charge-pause','charge-resume'):
                for reply in (success,dict(ok=False,error='charge_busy'),dict(ok=False,saved=True,error='charge_reload_failed')):
                    with self.subTest(action=action,reply=reply):
                        result=subprocess.run(['sh',str(control),action,'17'],env=dict(env,REPLY=json.dumps(reply)),capture_output=True,text=True)
                        self.assertEqual(result.returncode,0 if reply['ok'] else 1,result.stderr)
                        args=json.loads((base/'calls').read_text())
                        self.assertEqual(args[:3],['call','u30pro.panel','charge_result'])
                        self.assertEqual(json.loads(args[3]),dict(token='17',result=reply))
            for reply,code in [('not-json','0'),(json.dumps(success),'1')]:
                result=subprocess.run(['sh',str(control),'charge-resume','18'],env=dict(env,REPLY=reply,OWNER_EXIT=code),capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0)
                args=json.loads((base/'calls').read_text())
                self.assertFalse(json.loads(args[3])['result']['ok'])
            result=subprocess.run(['sh',str(control),'charge-pause','1;reboot'],env=dict(env,REPLY=json.dumps(success)),capture_output=True,text=True)
            self.assertEqual(result.returncode,2)

if __name__ == '__main__':unittest.main(verbosity=2)
