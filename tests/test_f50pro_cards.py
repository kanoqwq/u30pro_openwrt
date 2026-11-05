"""MU3356 physical wiring and shared broker transactions, with no real modem."""
import json
from pathlib import Path
from helpers import TOP
import test_v50_sim as fixtures

LIB=TOP/'devices/f50pro/overlay/opt/mu300/lib/f50pro-card.sh'


class F50ProCards(fixtures.PhysicalCardsFixture):
    def setUp(self):
        super().setUp()
        (self.root/'etc/mu300').mkdir(parents=True)
        (self.root/'etc/mu300/model').write_text('f50pro\n')
        self.args.write_bytes(b'zteboot.zte_boardid=4\0')
        self.initial.pop('v50_card')
        self.initial['f50pro_card']=0
        self.state.write_text(json.dumps(self.initial))
        (self.hw/'layout').write_text('mu3356\n')
        (self.hw/'psim_select').write_text('1\n')
        self.extra.update(TEST_MODEL='u30pro',MU300_F50PRO_CARD_LIB=LIB,
                          MU300_U30PRO_RUN=self.run,MU300_U30PRO_MUX=self.hw)
        self.stub('mu300-u30pro-sim',f'exec /bin/sh "{self.controller}" "$@"')

    def preinit(self,shell):
        return self.script(shell,TOP/'devices/u30pro/overlay/usr/sbin/u30pro-sim-preinit',**self.extra)

    def test_pre_cp_saved_pair_restores_gpio_without_at_or_uci_mutation(self):
        for shell in self.each_shell():
            state=dict(self.initial,f50pro_route0=3,f50pro_route1=4)
            self.state.write_text(json.dumps(state));before=self.state.read_bytes()
            (self.hw/'chip_select').write_text('1\n');(self.hw/'psim_select').write_text('1\n')
            (self.tmp/'commands').unlink(missing_ok=True)
            r=self.preinit(shell);self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual((self.hw/'chip_select').read_text().strip(),'0')
            self.assertEqual((self.hw/'psim_select').read_text().strip(),'0')
            self.assertEqual(self.state.read_bytes(),before)
            self.assertFalse((self.tmp/'commands').exists())
            (self.run/'u30pro-cp-started').touch()
            self.assertEqual(self.preinit(shell).returncode,0) # unchanged service restart
            (self.run/'u30pro-cp-started').unlink()

    def test_pre_cp_validates_entire_pair_before_writes_and_refuses_live_mux(self):
        for shell in self.each_shell():
            (self.hw/'chip_select').write_text('1\n');(self.hw/'psim_select').write_text('1\n')
            before={p.name:p.read_bytes() for p in self.hw.iterdir()}
            for state in (dict(self.initial,f50pro_route0=3,f50pro_route1=3),
                          dict(self.initial,f50pro_route0=3),
                          dict(self.initial,f50pro_route0=3,f50pro_route1=99)):
                self.state.write_text(json.dumps(state))
                self.assertNotEqual(self.preinit(shell).returncode,0)
                self.assertEqual(before,{p.name:p.read_bytes() for p in self.hw.iterdir()})
            self.state.write_text(json.dumps(dict(self.initial,f50pro_route0=3,f50pro_route1=4)))
            (self.run/'u30pro-cp-started').touch()
            self.assertIn('cp_already_started',self.preinit(shell).stderr)
            self.assertEqual(before,{p.name:p.read_bytes() for p in self.hw.iterdir()})
            (self.run/'u30pro-cp-started').unlink()

    def test_pre_cp_unsaved_and_other_product_preserve_stock_gpio(self):
        for shell in self.each_shell():
            self.state.write_text('{}');before={p.name:p.read_bytes() for p in self.hw.iterdir()}
            self.assertEqual(self.preinit(shell).returncode,0)
            self.assertEqual(before,{p.name:p.read_bytes() for p in self.hw.iterdir()})
            (self.root/'etc/mu300/model').write_text('mu300\n')
            self.state.write_text(json.dumps(dict(self.initial,f50pro_route0=3,f50pro_route1=4)))
            self.assertEqual(self.preinit(shell).returncode,0)
            self.assertEqual(before,{p.name:p.read_bytes() for p in self.hw.iterdir()})
            (self.root/'etc/mu300/model').write_text('f50pro\n')

    def test_pre_cp_detects_a_running_old_bridge_without_new_boot_marker(self):
        import socket
        self.state.write_text(json.dumps(dict(self.initial,f50pro_route0=3,f50pro_route1=4)))
        (self.hw/'psim_select').write_text('1\n')
        directory=self.run/'mu300-modem';directory.mkdir()
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as bridge:
            bridge.bind(str(directory/'io.sock'))
            before=(self.hw/'psim_select').read_bytes()
            for shell in self.each_shell():
                r=self.preinit(shell)
                self.assertNotEqual(r.returncode,0)
                self.assertIn('cp_already_started',r.stderr)
                self.assertEqual((self.hw/'psim_select').read_bytes(),before)

    def test_native_cp_start_restores_sources_before_loading_firmware(self):
        service=(TOP/'devices/u30pro/overlay/etc/init.d/mu300-vendor').read_text()
        self.assertLess(service.index('/usr/sbin/u30pro-sim-preinit'),service.index('procd_open_instance cp'))
        self.assertLess(service.index(': > /run/u30pro-cp-started'),service.index('procd_set_param command /usr/sbin/u30-modemd'))

    def test_all_production_layouts_and_no_operator_filter(self):
        expected={0:[0,1,2],1:[0,1],2:[0,2],3:[0,2,3,4],4:[0,1,3,4],5:[3,4]}
        for shell in self.each_shell():
            for board,cards in expected.items():
                self.args.write_bytes(f'zteboot.zte_boardid={board}\0'.encode())
                data=json.loads(self.call(shell,'status').stdout)
                self.assertEqual((data['model'],data['cards']),('f50pro',cards))
                for target in range(5):
                    self.assertEqual(self.call(shell,'validate',str(target)).returncode==0,target in cards)
        self.assertFalse((self.tmp/'commands').exists())

    def test_same_board_number_is_not_mu5358_routing(self):
        for shell in self.each_shell():
            for chip,psim,slot,card in [(1,1,0,0),(1,1,1,1),(0,1,1,4),(1,0,0,3)]:
                (self.hw/'chip_select').write_text(str(chip))
                (self.hw/'psim_select').write_text(str(psim))
                (self.run/'mu300-data-sim-actual').write_text(str(slot))
                status=json.loads(self.call(shell,'status').stdout)
                self.assertEqual(status['active_card'],card)
                self.assertEqual(status['logical_cards'][slot],card)

    def test_stock_inverse_mapping_for_every_production_board_and_mux_state(self):
        for shell in self.each_shell():
            for board in range(6):
                self.args.write_bytes(f'zteboot.zte_boardid={board}\0'.encode())
                for chip in (0,1):
                    for psim in (0,1):
                        (self.hw/'chip_select').write_text(str(chip))
                        (self.hw/'psim_select').write_text(str(psim))
                        expected={0:[0,1 if chip==0 else 2],1:[0,1],2:[0,2],
                                  3:[0 if psim else 3,2 if chip else 4],
                                  4:[0 if psim else 3,1 if chip else 4],5:[3,4]}[board]
                        for slot in (0,1):
                            (self.run/'mu300-data-sim-actual').write_text(str(slot))
                            status=json.loads(self.call(shell,'status').stdout)
                            self.assertEqual(status['logical_cards'],expected,(board,chip,psim))
                            self.assertEqual(status['active_card'],expected[slot])

    def test_second_external_card_uses_stack_one_and_shared_power_order(self):
        for shell in self.each_shell():
            self.state.write_text(json.dumps(self.initial))
            (self.hw/'chip_select').write_text('1\n')
            (self.tmp/'commands').unlink(missing_ok=True)
            r=self.call(shell,'apply','4')
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual((self.hw/'chip_select').read_text().strip(),'0')
            self.assertEqual(json.loads(self.state.read_text())['f50pro_card'],4)
            calls=(self.tmp/'commands').read_text()
            expected=['AT+SPACTCARD=1;+SFUN=5','AT+SPACTCARD=1;+SFUN=3',
                      'sleep 5','AT+SPACTCARD=1;+SFUN=2','replay 1 replay early',
                      'AT+SPACTCARD=1;+SFUN=4','logical 1']
            positions=[calls.index(v) for v in expected]
            self.assertEqual(positions,sorted(positions))
            self.assertNotIn('AT+SPACTCARD=4;',calls)
            self.assertNotIn('AT+SPACTCARD=0;+SFUN',calls)
            self.assertTrue((self.run/'mu300/f50pro-generation1').exists())
            self.assertFalse((self.run/'mu300/u30pro-generation1').exists())

    def test_unsaved_boot_preserves_stock_mux_without_at_or_delay(self):
        for shell in self.each_shell():
            state=dict(self.initial);state.pop('f50pro_card')
            self.state.write_text(json.dumps(state))
            (self.tmp/'commands').unlink(missing_ok=True)
            before={p.name:p.read_bytes() for p in self.hw.iterdir()}
            r=self.call(shell,'boot')
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(before,{p.name:p.read_bytes() for p in self.hw.iterdir()})
            self.assertFalse((self.tmp/'commands').exists())

    def test_two_external_only_layout_selects_data_without_gpio_cycle(self):
        for shell in self.each_shell():
            self.args.write_bytes(b'zteboot.zte_boardid=5\0')
            self.state.write_text(json.dumps(self.initial))
            (self.tmp/'commands').unlink(missing_ok=True)
            r=self.call(shell,'apply','4')
            self.assertEqual(r.returncode,0,r.stderr)
            calls=(self.tmp/'commands').read_text()
            self.assertIn('logical 1',calls)
            self.assertNotIn('SFUN',calls)
            self.assertNotIn('sleep',calls)

    def test_old_kernel_or_test_sku_does_not_permit_wrong_gpio_writes(self):
        for shell in self.each_shell():
            self.args.write_bytes(b'zteboot.zte_boardid=4\0')
            (self.hw/'layout').write_text('mu5358\n')
            r=self.call(shell,'apply','4')
            self.assertNotEqual(r.returncode,0)
            self.assertIn('physical_mux_unavailable',r.stderr)
            (self.hw/'layout').write_text('mu3356\n')
            self.args.write_bytes(b'zteboot.zte_boardid=1000\0')
            self.assertFalse(json.loads(self.call(shell,'status').stdout)['supported'])
            self.assertNotEqual(self.call(shell,'apply','3').returncode,0)
        self.assertFalse((self.tmp/'commands').exists())

    def test_failed_sim_power_restores_previous_physical_card_and_wan(self):
        for shell in self.each_shell():
            self.state.write_text(json.dumps(self.initial))
            (self.hw/'chip_select').write_text('1\n')
            (self.tmp/'failed-once').unlink(missing_ok=True)
            r=self.call(shell,'apply','4',FAIL_POWER_ON='1')
            self.assertNotEqual(r.returncode,0)
            self.assertIn('sim_switch_failed_restored',r.stderr)
            self.assertEqual((self.hw/'chip_select').read_text().strip(),'1')
            self.assertTrue(json.loads(self.state.read_text())['up'])

    def test_initial_stock_card_import_maps_slot_and_keeps_explicit_op_preference(self):
        destination=self.tmp/'fresh-root'
        for shell in self.each_shell():
            code=f'. "{LIB}"\nf50pro_import_card "{destination}" 4 4\n'
            r=self.sh(shell,code,**self.extra)
            self.assertEqual(r.returncode,0,r.stderr)
            script=destination/'etc/uci-defaults/99-zz-f50pro-card'
            state=dict(self.initial);state.pop('f50pro_card')
            self.state.write_text(json.dumps(state))
            r=self.script(shell,script,**self.extra)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(json.loads(self.state.read_text())['data_sim'],1)
            self.assertEqual(json.loads(self.state.read_text())['f50pro_card'],4)
            state=dict(self.initial);state['f50pro_card']=3
            self.state.write_text(json.dumps(state))
            self.assertEqual(self.script(shell,script,**self.extra).returncode,0)
            self.assertEqual(json.loads(self.state.read_text())['f50pro_card'],3)

    def test_fresh_import_defaults_single_standby_without_overwriting_saved_rf(self):
        destination=self.tmp/'standby-root'
        policy=self.tmp/'standby-policy'
        for shell in self.each_shell():
            for dsds,expected in [('0','0 1'),('1','0 1')]:
                state=dict(self.initial);state.pop('f50pro_card');self.state.write_text(json.dumps(state))
                policy.unlink(missing_ok=True)
                result=self.sh(shell,f'. "{LIB}"\nf50pro_import_card "{destination}" 4 4 {dsds}\n',**self.extra)
                self.assertEqual(result.returncode,0,result.stderr)
                script=destination/'etc/uci-defaults/99-zz-f50pro-card'
                result=self.script(shell,script,UNISOC_RADIO_POLICY=policy,**self.extra)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(policy.read_text().strip(),expected)
                self.assertEqual(json.loads(self.state.read_text())['dual_standby'],0)
                state.pop('f50pro_card',None);self.state.write_text(json.dumps(state))
                policy.write_text('0 0\n')
                self.assertEqual(self.script(shell,script,UNISOC_RADIO_POLICY=policy,**self.extra).returncode,0)
                self.assertEqual(policy.read_text(),'0 0\n')
            self.assertNotEqual(self.sh(shell,f'. "{LIB}"\nf50pro_import_card "{destination}" 4 4 null\n',**self.extra).returncode,0)
        self.assertFalse((self.tmp/'commands').exists())

    def test_import_preserves_both_actual_stock_sources(self):
        destination=self.tmp/'sources-root'
        for shell in self.each_shell():
            state=dict(self.initial);state.pop('f50pro_card');self.state.write_text(json.dumps(state))
            code=f'. "{LIB}"\nf50pro_import_card "{destination}" 4 4 0 0 1\n'
            self.assertEqual(self.sh(shell,code,**self.extra).returncode,0)
            r=self.script(shell,destination/'etc/uci-defaults/99-zz-f50pro-card',**self.extra)
            self.assertEqual(r.returncode,0,r.stderr)
            state=json.loads(self.state.read_text())
            self.assertEqual([state['f50pro_route0'],state['f50pro_route1']],[0,4])
        invalid=self.tmp/'invalid-import'
        for shell in self.each_shell():
            r=self.sh(shell,f'. "{LIB}"\nf50pro_import_card "{invalid}" 4 4 0 1 1\n',**self.extra)
            self.assertNotEqual(r.returncode,0)
            self.assertFalse(invalid.exists(),'contradictory Android selection must not stage a partial script')

    def pair(self,shell,first,second,**extra):
        source=TOP/'devices/f50pro/overlay/opt/mu300/bin/f50pro-card-pair'
        script=self.tmp/'pair-controller'
        shims='\n'.join(n+'() { "$STUBLOG/stubs/'+n+'" "$@"; }' for n in ['ifdown','ifup','sleep'])
        script.write_text(source.read_text().replace('#!/bin/sh\n','#!/bin/sh\n'+shims+'\n',1))
        env=dict(self.extra,MU300_F50PRO_CONTROL=self.stubs/'mu300-u30pro-sim',
                 MU300_SIM_CONTROL_LOCK=self.tmp/'native-pair.lock')
        env.update(extra)
        return self.script(shell,script,'apply',str(first),str(second),**env)

    def test_pair_external_sources_only_changes_the_peer_without_restarting_data(self):
        for shell in self.each_shell():
            state=dict(self.initial);state.update(data_sim=1,radio=[0,1],f50pro_card=4)
            self.state.write_text(json.dumps(state));(self.run/'mu300-data-sim-actual').write_text('1\n')
            (self.hw/'chip_select').write_text('0\n');(self.hw/'psim_select').write_text('1\n')
            (self.tmp/'commands').unlink(missing_ok=True)
            r=self.pair(shell,3,4);self.assertEqual(r.returncode,0,r.stderr)
            state=json.loads(self.state.read_text())
            self.assertEqual([state['f50pro_route0'],state['f50pro_route1']],[3,4])
            self.assertEqual(state['data_sim'],1);self.assertEqual(state['radio'],[0,1])
            calls=(self.tmp/'commands').read_text()
            self.assertNotIn('ifdown',calls);self.assertNotIn('ifup',calls)
            self.assertNotIn('AT+SPACTCARD=1;',calls)
            self.assertNotIn('AT+SPACTCARD=0;+SFUN=4',calls)
            self.assertNotIn('AT+SPACTCARD=0;+CPIN?',calls)

    def test_all_two_stack_source_combinations_keep_default_data_and_wan_intent(self):
        for shell in self.each_shell():
            for first,second in [(0,1),(0,4),(3,1),(3,4)]:
                state=dict(self.initial);state.update(data_sim=1,f50pro_card=4,autostart=False,up=False)
                self.state.write_text(json.dumps(state))
                (self.run/'mu300-data-sim-actual').write_text('1\n')
                (self.hw/'chip_select').write_text('0\n');(self.hw/'psim_select').write_text('1\n')
                (self.tmp/'commands').unlink(missing_ok=True)
                r=self.pair(shell,first,second);self.assertEqual(r.returncode,0,r.stderr)
                state=json.loads(self.state.read_text())
                self.assertEqual([state['f50pro_route0'],state['f50pro_route1']],[first,second])
                self.assertEqual(state['data_sim'],1);self.assertFalse(state['up'])
                self.assertEqual(state['radio'],[1,1])
                self.assertNotIn('ifup',(self.tmp/'commands').read_text() if (self.tmp/'commands').exists() else '')

    def test_pair_failure_restores_both_sources_and_default_data(self):
        for shell in self.each_shell():
            self.state.write_text(json.dumps(self.initial))
            (self.run/'mu300-data-sim-actual').write_text('0\n')
            (self.hw/'chip_select').write_text('0\n');(self.hw/'psim_select').write_text('1\n')
            (self.tmp/'failed-once').unlink(missing_ok=True)
            r=self.pair(shell,3,1,FAIL_POWER_ON='1')
            self.assertNotEqual(r.returncode,0)
            self.assertIn('sim_switch_failed_restored',r.stderr)
            self.assertEqual((self.hw/'psim_select').read_text().strip(),'1')
            self.assertEqual((self.hw/'chip_select').read_text().strip(),'0')
            state=json.loads(self.state.read_text())
            self.assertEqual(state['data_sim'],0);self.assertTrue(state['up'])
            self.assertNotIn('f50pro_route0',state)

    def test_saved_pair_boot_replays_both_sources_without_enabling_rf(self):
        for shell in self.each_shell():
            state=dict(self.initial);state.update(f50pro_route0=3,f50pro_route1=4)
            self.state.write_text(json.dumps(state))
            (self.hw/'chip_select').write_text('1\n');(self.hw/'psim_select').write_text('1\n')
            (self.tmp/'commands').unlink(missing_ok=True)
            code='ln -s $$ "$MU300_U30PRO_RUN/mu300-radio-on.owner"\n"$MU300_BIN/mu300-u30pro-sim" boot\nrc=$?\nrm -f "$MU300_U30PRO_RUN/mu300-radio-on.owner"\nexit $rc'
            r=self.sh(shell,code,**self.extra);self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual((self.hw/'chip_select').read_text().strip(),'0')
            self.assertEqual((self.hw/'psim_select').read_text().strip(),'0')
            self.assertNotIn('+SFUN=4',(self.tmp/'commands').read_text())


if __name__=='__main__':
    import unittest
    unittest.main(verbosity=2)
