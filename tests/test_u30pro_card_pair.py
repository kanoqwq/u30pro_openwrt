"""Actual ucode orchestration and existing physical owner, on private mock hardware."""
import json
import os
from pathlib import Path
import subprocess
import time
import unittest
from helpers import TOP, ucode
from test_u30pro_cards import U30ProCards

ENTRY=TOP/'devices/u30pro/overlay/opt/mu300/bin/u30pro-card-pair'
TOOL=TOP/'devices/u30pro/overlay/usr/share/ucode/mu300/u30pro-card-pair.uc'

@unittest.skipUnless(ucode(),'requires actual target ucode')
class Pair(unittest.TestCase):
    def setUp(self):
        self.f=U30ProCards();self.f.setUp();self.addCleanup(self.f.tearDown)
        self.extra=dict(self.f.extra,MU300_U30PRO_PAIR_TOOL=TOOL)

    def call(self,first,second,operation='apply',**extra):
        return self.f.script(['/bin/sh'],ENTRY,operation,first,second,**dict(self.extra,**extra))

    def reset(self,**state):
        f=self.f
        for name in ('chip_select','psim_select'):(f.hw/name).write_text('0\n')
        f.state.write_text(json.dumps(dict(f.initial,**state)))
        (f.run/'mu300-data-sim-actual').write_text(str(state.get('data_sim',0))+'\n')
        for name in ('commands','failed-once','mode-failed-once'):(f.tmp/name).unlink(missing_ok=True)
        (f.run/'mu300/u30pro-switch-incomplete').unlink(missing_ok=True)

    def test_current_data_source_changes_and_both_routes_survive_pre_cp_boot(self):
        f=self.f;self.reset()
        if os.environ.get('PAIR_TEST_TRACE'):
            f.controller.write_text(f.controller.read_text().replace('set -eu','set -eux',1))
        result=self.call(3,2,REQUIRE_MODE_INIT='1')
        self.assertEqual(result.returncode,0,result.stderr+f.state.read_text()+(f.tmp/'commands').read_text())
        state=json.loads(f.state.read_text())
        self.assertEqual([state['u30pro_route0'],state['u30pro_route1'],state['u30pro_card']],[3,2,3])
        self.assertEqual(state['data_sim'],0);self.assertEqual(state['radio'],[1,1]);self.assertTrue(state['up'])
        commands=(f.tmp/'commands').read_text()
        self.assertIn('ifdown',commands);self.assertIn('ifup',commands)
        self.assertNotIn('logical ',commands)
        self.assertIn('AT+SPACTCARD=0;+SPTESTMODEM=',commands)
        self.assertIn('AT+SPACTCARD=1;+SPTESTMODEM=',commands)
        before=f.state.read_bytes();(f.tmp/'commands').unlink()
        for name in ('chip_select','psim_select'):(f.hw/name).write_text('0\n')
        result=f.preinit(['/bin/sh']);self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual((f.hw/'psim_select').read_text().strip(),'1')
        self.assertEqual((f.hw/'chip_select').read_text().strip(),'1')
        self.assertEqual(f.state.read_bytes(),before);self.assertFalse((f.tmp/'commands').exists())
        result=f.sh(['/bin/sh'],'"$MU300_BIN/mobile-data" radio-locked "$MU300_BIN/mu300-u30pro-sim" boot',**f.extra)
        self.assertEqual(result.returncode,0,result.stderr);self.assertFalse((f.tmp/'commands').exists())

    def test_peer_only_keeps_network_and_disabled_radio_unchanged(self):
        f=self.f;self.reset(radio=[1,0],cfun=[1,0])
        result=self.call(0,2);self.assertEqual(result.returncode,0,result.stderr)
        state=json.loads(f.state.read_text());self.assertEqual(state['radio'],[1,0])
        commands=(f.tmp/'commands').read_text()
        for forbidden in ('ifdown','ifup','logical ','AT+SPACTCARD=0;','+SFUN=4','+SPTESTMODE','+CPIN?'):
            self.assertNotIn(forbidden,commands)

    def test_failed_mode_restores_both_routes_and_manual_wan_off(self):
        f=self.f;self.reset(autostart=False,up=False,u30pro_route0=0,u30pro_route1=1)
        result=self.call(3,2,FAIL_MODE_INIT='1')
        self.assertNotEqual(result.returncode,0);self.assertIn('sim_switch_failed_restored',result.stderr)
        state=json.loads(f.state.read_text())
        self.assertEqual([state['u30pro_route0'],state['u30pro_route1'],state['u30pro_card']],[0,1,0])
        self.assertEqual(state['data_sim'],0);self.assertFalse(state['up'])
        self.assertEqual([ (f.hw/n).read_text().strip() for n in ('psim_select','chip_select')],['0','0'])
        self.assertFalse((f.run/'mu300/u30pro-switch-incomplete').exists())
        self.assertNotIn('ifup',(f.tmp/'commands').read_text())

    def test_all_board_shapes_reject_unfitted_or_wrong_stack_before_mutation(self):
        f=self.f
        for board,first,second in [(0,3,2),(1,0,2),(2,0,1),(3,3,1),(4,3,2),(6,0,2)]:
            f.args.write_bytes(f'zteboot.zte_boardid={board}\0'.encode())
            self.assertEqual(self.call(first,second,'validate').returncode,0)
            self.assertNotEqual(self.call(second,first,'validate').returncode,0)
        f.args.write_bytes(b'zteboot.zte_boardid=5\0')
        self.assertNotEqual(self.call(3,1).returncode,0)
        self.assertFalse((f.tmp/'commands').exists())

    def test_busy_gate_refuses_without_touching_modem(self):
        f=self.f;gate=f.run/'unisoc-data-sim-switch';gate.mkdir();(gate/'pid').write_text(str(os.getpid()))
        result=self.call(3,2);self.assertNotEqual(result.returncode,0);self.assertIn('modem_busy',result.stderr)
        self.assertFalse((f.tmp/'commands').exists())
        self.assertTrue(gate.exists(),'must not remove another owner gate')

    def test_cancelled_transaction_restores_network_and_releases_both_locks(self):
        f=self.f;self.reset()
        owner=f.stubs/'mobile-data'
        owner.write_text('''#!/usr/bin/python3
import os,sys,time
from pathlib import Path
p=Path(os.environ['STUBLOG']);mark=p/'paused-once'
if not mark.exists():
 mark.touch();time.sleep(30)
os.execv(sys.executable,[sys.executable,str(p/'driver.py'),'mobile-data',*sys.argv[1:]])
''');owner.chmod(0o755)
        process=subprocess.Popen(['/bin/sh',str(ENTRY),'apply','3','2'],env=f.env(**self.extra),
                                 stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            deadline=time.monotonic()+30
            while not (f.tmp/'paused-once').exists() and process.poll() is None and time.monotonic()<deadline:time.sleep(.05)
            self.assertTrue((f.tmp/'paused-once').exists())
            process.terminate();out,err=process.communicate(timeout=30)
            self.assertNotEqual(process.returncode,0,out+err)
            self.assertIn('sim_switch_failed_restored',err)
            self.assertFalse((f.run/'unisoc-data-sim-switch').exists())
            self.assertFalse((f.run/'mu300/u30pro-switch-incomplete').exists())
            self.assertTrue(json.loads(f.state.read_text())['up'])
            self.assertEqual(self.call(0,1).returncode,0,'native flock must also be released')
        finally:
            if process.poll() is None:process.kill();process.communicate()

    def test_list_switch_updates_saved_routes_after_pair_was_explicitly_configured(self):
        f=self.f;self.reset(u30pro_route0=0,u30pro_route1=1)
        result=f.call(['/bin/sh'],'apply','2');self.assertEqual(result.returncode,0,result.stderr+f.state.read_text()+(f.tmp/'commands').read_text())
        state=json.loads(f.state.read_text())
        self.assertEqual([state['u30pro_route0'],state['u30pro_route1']],[0,2])

def load_tests(loader,tests,pattern):return loader.loadTestsFromTestCase(Pair)

if __name__=='__main__':unittest.main(verbosity=2)
