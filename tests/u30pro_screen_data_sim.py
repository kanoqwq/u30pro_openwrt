"""Screen data-card actions use the existing owner; all commands are synthetic."""
import json,os,subprocess,tempfile,unittest
from pathlib import Path
TOP=Path(__file__).resolve().parents[1]
NATIVE=TOP/'devices/u30pro/native/tools'
CONTROL=TOP/'devices/u30pro/overlay/usr/sbin/u30pro-panel-control'
@unittest.skipUnless(os.name=='posix','POSIX native/shell fixtures')
class DataSIM(unittest.TestCase):
 def test_card_choices_busy_errors_and_late_completions(self):
  with tempfile.TemporaryDirectory() as folder:
   base=Path(folder)
   source=r'''#define UI_HOST
#define UI_RUN "TEST_RUN"
#define UI_SYSFS "TEST_RUN"
#define main simulator_main
#include "u30pro_ui.c"
#undef main
#include <assert.h>
int main(void) {
 ui_init_canvases();g_ms=vclock=10000;
 assert(gx_has_all(FN14,"切换上网卡内置外置使用中网络将短暂中断基带尚未就绪目标卡失败"));
 feed_set("data_card_mask","3");feed_set("data_card_current","0");feed_set("data_card_ready","1");
 fn_build();assert(fn_entries[FN_DATA_SIM].fn==FN_DATA_SIM);
 nhits=0;g_reg=1;page_data_sim(&scr);g_reg=0;
 int seen=0;for(int i=0;i<nhits;i++)if(hits[i].id>=H_DATA_SIM0 && hits[i].id<=H_DATA_SIM3)seen|=1<<(hits[i].id-H_DATA_SIM0);
 assert(seen==3);
 do_action(H_DATA_SIM2);assert(!data_sim_busy_until); // absent hardware card
 do_action(H_DATA_SIM0);assert(!data_sim_busy_until); // already selected
 do_action(H_DATA_SIM1);assert(data_sim_busy_until && D.data_card_current==0);
 unsigned old=data_sim_request;
 do_action(H_DATA_SIM0);assert(data_sim_request==old);
 data_sim_complete(old+1,1,1,"");assert(data_sim_busy_until);
 data_sim_complete(old,0,1,"");assert(data_sim_busy_until);
 data_sim_complete(old,1,0,"sim_not_ready");assert(!data_sim_busy_until && D.data_card_current==0 && toast.col==C_BAD);
 do_action(H_DATA_SIM1);data_sim_complete(data_sim_request,1,1,"");
 assert(!data_sim_busy_until && D.data_card_current==0); // never optimistic
 feed_set("data_card_current","1");do_action(H_DATA_SIM1);assert(!data_sim_busy_until);
 feed_set("data_card_mask","15");feed_set("data_card_current","0");do_action(H_DATA_SIM3);
 g_ms=data_sim_busy_until;detect_events();assert(!data_sim_busy_until && toast.col==C_BAD);
 do_action(H_DATA_SIM1);data_sim_complete(old,1,1,"");assert(data_sim_busy_until);
 data_sim_complete(data_sim_request,1,0,"modem_busy");assert(!data_sim_busy_until && toast.col==C_BAD);
 return 0;
}
'''.replace('TEST_RUN',str(base))
   (base/'test.c').write_text(source)
   r=subprocess.run(['gcc','-std=gnu11','-O1','-I',str(NATIVE),str(base/'test.c'),'-lm','-o',str(base/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   r=subprocess.run([str(base/'test')],capture_output=True,text=True,timeout=15)
   self.assertEqual(r.returncode,0,r.stderr+r.stdout)
   self.assertEqual(r.stdout.count('panel-control data-sim'),4)
 def test_actual_feed_projection_matches_board_cards_not_logical_stack_numbers(self):
  from helpers import ucode
  command=ucode()
  if not command:self.skipTest('Target ucode runtime required')
  source=(TOP/'devices/u30pro/overlay/usr/sbin/u30pro-ui-feed').read_text()
  projection=source[source.index('function screen_data_cards('):source.index('function run()')]
  cases=[({'model':'u30pro','supported':True,'ready':True,'cards':[0,1],'active_card':1},3,1,1),
         ({'model':'u30pro','supported':True,'ready':True,'cards':[0,1,2,3],'active_card':3},15,3,1),
         ({'model':'u30pro','supported':True,'ready':True,'cards':[3],'active_card':3},8,3,1),
         ({'model':'u30pro','supported':True,'ready':False,'cards':[0,2],'active_card':2},5,2,0),
         ({'model':'u30pro','supported':True,'ready':True,'cards':[0,1],'active_card':3},3,-1,0),
         ({'model':'f50pro','supported':True,'ready':True,'cards':[3,4],'active_card':3},0,-1,0),
         ({'model':'u30pro','supported':False,'ready':True,'cards':[0,1],'active_card':0},0,-1,0),
         ({},0,-1,0)]
  program=projection+'\nfor(let row in '+json.dumps(cases)+') {let d=screen_data_cards(row[0]);if(d.data_card_mask!=row[1] || d.data_card_current!=row[2] || d.data_card_ready!=row[3])die(sprintf("bad cards %J",d));} print("PASS board cards\\n");'
  reply=subprocess.run(command+['-e',program],capture_output=True,text=True,timeout=30)
  self.assertEqual(reply.returncode,0,reply.stderr)
 def test_real_shell_action_reports_owner_result_without_polls_or_at(self):
  with tempfile.TemporaryDirectory() as folder:
   base=Path(folder)
   def program(name,text):
    p=base/name;p.write_text(text);p.chmod(0o755);return p
   owner=program('owner','#!/bin/sh\nprintf "%s\n" "$*" >> "$TEST_COMMANDS"\necho "${TEST_ERROR:-}" >&2\nexit "${TEST_EXIT:-0}"\n')
   program('ubus','#!/bin/sh\nprintf "%s\n" "$*" >> "$TEST_BUS"\n')
   action=program('control',CONTROL.read_text().replace('/usr/libexec/unisoc-modem/data-sim',str(owner)).replace('/run/u30pro-data-sim.',str(base/'action.')))
   env=dict(os.environ,PATH=str(base)+':'+os.environ['PATH'],TEST_COMMANDS=str(base/'commands'),TEST_BUS=str(base/'bus'))
   for rc,error in ((0,''),(1,'sim_not_ready'),(1,'modem_busy')):
    (base/'bus').write_text('')
    r=subprocess.run([str(action),'data-sim','1','12'],env=dict(env,TEST_EXIT=str(rc),TEST_ERROR=error),capture_output=True,text=True)
    self.assertEqual(r.returncode,rc,r.stderr)
    reply=(base/'bus').read_text().splitlines();data=json.loads(reply[0].split('data_sim_result ',1)[1])
    self.assertEqual(data['token'],'12');self.assertEqual(data['result']['target'],1)
    self.assertEqual(data['result']['ok'],rc==0);self.assertEqual(data['result']['error'],error)
    self.assertIn('send u30pro.panel.request',reply[1])
   self.assertEqual((base/'commands').read_text().splitlines(),['apply data u30pro-card-1']*3)
   count=len((base/'commands').read_text())
   for args in (('9','12'),('1','bad'),('1','12345678901')):
    self.assertEqual(subprocess.run([str(action),'data-sim',*args],env=env).returncode,2)
   self.assertEqual(len((base/'commands').read_text()),count)
if __name__=='__main__':unittest.main(verbosity=2)
