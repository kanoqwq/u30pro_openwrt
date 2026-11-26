"""U30 Pro uses the same verified stock RF-on preparation as F50 Pro."""
import json
import unittest
from test_u30pro_cards import U30ProCards


class U30ProMode(unittest.TestCase):
    def setUp(self):
        self.f=U30ProCards();self.f.setUp()

    def tearDown(self):self.f.tearDown()

    def reset(self,target,flags=(1,1),modes='3,152,1,19,3,1'):
        f=self.f
        for name in ('commands','mode-failed-once'):(f.tmp/name).unlink(missing_ok=True)
        for name in ('chip_select','psim_select'):(f.hw/name).write_text('0\n')
        f.state.write_text(json.dumps(dict(f.initial,radio=list(flags),cfun=list(flags),work_modes=modes)))
        (f.run/'mu300-data-sim-actual').write_text('0\n')
        (f.run/'mu300/u30pro-switch-incomplete').unlink(missing_ok=True)

    def test_internal_and_external_switch_prepare_current_modes_before_rf(self):
        f=self.f
        for shell in f.each_shell():
            for target,stack,modes in ((2,1,'3,152,1,19,3,1'),(3,0,'152,3,0')):
                self.reset(target,modes=modes)
                result=f.call(shell,'apply',str(target),REQUIRE_MODE_INIT='1')
                self.assertEqual(result.returncode,0,result.stderr)
                calls=(f.tmp/'commands').read_text();pair=','.join(modes.split(',')[:2])
                order=[f'AT+SPACTCARD={stack};+SFUN=2',f'AT+SPACTCARD={stack};+SPTESTMODE?',
                       f'AT+SPACTCARD={stack};+SPTESTMODEM={pair}',f'replay {stack} replay early',f'AT+SPACTCARD={stack};+SFUN=4']
                positions=[calls.index(n) for n in order]
                self.assertEqual(positions,sorted(positions))
                self.assertNotIn(f'AT+SPACTCARD={1-stack};+SPTESTMODEM=',calls)
                state=json.loads(f.state.read_text())
                self.assertEqual(state['radio'],[1,1]);self.assertEqual(state['u30pro_card'],target)

    def test_rejected_mode_restores_route_preference_and_network(self):
        f=self.f
        for shell in f.each_shell():
            self.reset(3)
            result=f.call(shell,'apply','3',FAIL_MODE_INIT='1')
            self.assertNotEqual(result.returncode,0)
            self.assertIn('sim_switch_failed_restored',result.stderr)
            state=json.loads(f.state.read_text())
            self.assertEqual(state['u30pro_card'],0);self.assertTrue(state['up'])
            self.assertEqual((f.hw/'psim_select').read_text().strip(),'0')
            self.assertFalse((f.run/'mu300/u30pro-switch-incomplete').exists())

    def test_unchanged_and_boot_paths_do_not_add_mode_initialization(self):
        f=self.f
        for shell in f.each_shell():
            self.reset(0)
            result=f.call(shell,'apply','0');self.assertEqual(result.returncode,0,result.stderr)
            self.assertNotIn('SPTESTMODE',(f.tmp/'commands').read_text())
            result=f.sh(shell,'"$MU300_BIN/mobile-data" radio-locked "$MU300_BIN/mu300-u30pro-sim" boot',**f.extra)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertNotIn('SPTESTMODE',(f.tmp/'commands').read_text())

    def test_bad_mode_readback_cannot_enable_rf(self):
        f=self.f
        for shell in f.each_shell():
            self.reset(3,modes='invalid')
            result=f.call(shell,'apply','3')
            self.assertNotEqual(result.returncode,0)
            self.assertNotIn('+SFUN=4',(f.tmp/'commands').read_text())

    def test_disabled_radio_source_change_does_not_prepare_or_enable_rf(self):
        f=self.f
        for shell in f.each_shell():
            self.reset(2,flags=(1,0))
            result=f.sh(shell,'"$MU300_BIN/mobile-data" radio-locked "$MU300_BIN/mu300-u30pro-sim" --route 2',**f.extra)
            self.assertEqual(result.returncode,0,result.stderr)
            calls=(f.tmp/'commands').read_text()
            self.assertNotIn('SPTESTMODE',calls);self.assertNotIn('+SFUN=4',calls)


def load_tests(loader,tests,pattern):return loader.loadTestsFromTestCase(U30ProMode)
