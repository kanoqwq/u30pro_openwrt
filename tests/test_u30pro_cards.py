"""U30 Pro stock SKU routing over the shared, broker-owned card transaction."""
import json
from pathlib import Path
from helpers import TOP, ShellTest
import test_v50_sim as fixtures

LIB = TOP/'devices/u30pro/overlay/opt/mu300/lib/u30pro-card.sh'


class U30ProCards(fixtures.PhysicalCardsFixture):
    def setUp(self):
        super().setUp()
        (self.root/'etc/mu300').mkdir(parents=True)
        (self.root/'etc/mu300/model').write_text('u30pro\n')
        (self.hw/'layout').write_text('mu5358\n')
        self.args.write_bytes(b'zteboot.zte_boardid=0\0')
        self.initial.pop('v50_card')
        self.initial['u30pro_card']=0
        self.state.write_text(json.dumps(self.initial))
        self.extra.update(TEST_MODEL='u30pro',MU300_U30PRO_CARD_LIB=LIB,
                          MU300_U30PRO_RUN=self.run,MU300_U30PRO_MUX=self.hw)
        self.stub('mu300-u30pro-sim',f'exec /bin/sh "{self.controller}" "$@"')

    def preinit(self,shell):
        return self.script(shell,TOP/'devices/u30pro/overlay/usr/sbin/u30pro-sim-preinit',**self.extra)

    def test_pre_cp_all_stock_choices_leave_runtime_boot_nothing_to_reroute(self):
        reference=json.loads((TOP/'devices/u30pro/board-topology.json').read_text())
        for shell in self.each_shell():
            for board,cards in reference['board_cards'].items():
                self.args.write_bytes(f'zteboot.zte_boardid={board}\0'.encode())
                for target in [None]+cards:
                    with self.subTest(shell=shell,board=board,target=target):
                        state=dict(self.initial)
                        if target is None:state.pop('u30pro_card')
                        else:state['u30pro_card']=target
                        self.state.write_text(json.dumps(state));before=self.state.read_bytes()
                        # Start with both selectors opposite to the saved/default pair.
                        chosen=target if target is not None else (3 if board=='5' else 0)
                        expected=(int(board=='6' or chosen==2),int(board=='5' or chosen==3))
                        (self.hw/'chip_select').write_text(str(1-expected[0]))
                        (self.hw/'psim_select').write_text(str(1-expected[1]))
                        (self.tmp/'commands').unlink(missing_ok=True)
                        r=self.preinit(shell);self.assertEqual(r.returncode,0,r.stderr)
                        # Board 5 has no peer stack: its unused chip selector stays untouched.
                        chip=int((self.hw/'chip_select').read_text())
                        self.assertEqual(chip,1-expected[0] if board=='5' else expected[0])
                        self.assertEqual(int((self.hw/'psim_select').read_text()),expected[1])
                        self.assertEqual(self.state.read_bytes(),before)
                        self.assertFalse((self.tmp/'commands').exists())
                        # Run the real late boot controller: no SFUN/reset/delay remains.
                        r=self.sh(shell,'ln -s $$ "$MU300_U30PRO_RUN/mu300-radio-on.owner"\n"$MU300_BIN/mu300-u30pro-sim" boot\nrc=$?\nrm -f "$MU300_U30PRO_RUN/mu300-radio-on.owner"\nexit $rc',**self.extra)
                        self.assertEqual(r.returncode,0,r.stderr)
                        self.assertFalse((self.tmp/'commands').exists())

    def test_pre_cp_two_internal_cards_already_correct_are_a_noop_even_after_cp(self):
        self.args.write_bytes(b'zteboot.zte_boardid=2\0')
        (self.run/'u30pro-cp-started').touch()
        before={p.name:p.read_bytes() for p in self.hw.iterdir()}
        for shell in self.each_shell():
            r=self.preinit(shell);self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(before,{p.name:p.read_bytes() for p in self.hw.iterdir()})
            self.assertFalse((self.run/'u30pro-sim-preinit').exists())
            self.assertFalse((self.tmp/'commands').exists())

    def test_pre_cp_invalid_card_or_layout_cannot_write_either_selector(self):
        for shell in self.each_shell():
            for board,target,layout in [(2,2,'mu5358'),(0,99,'mu5358'),(0,2,'mu3356')]:
                self.args.write_bytes(f'zteboot.zte_boardid={board}\0'.encode())
                self.state.write_text(json.dumps(dict(self.initial,u30pro_card=target)))
                (self.hw/'layout').write_text(layout)
                before={p.name:p.read_bytes() for p in self.hw.iterdir()}
                r=self.preinit(shell);self.assertNotEqual(r.returncode,0)
                self.assertEqual(before,{p.name:p.read_bytes() for p in self.hw.iterdir()})

    def test_pre_cp_unknown_board_preserves_stock_instead_of_guessing(self):
        self.args.write_bytes(b'zteboot.zte_boardid=99\0')
        before={p.name:p.read_bytes() for p in self.hw.iterdir()}
        for shell in self.each_shell():
            self.assertEqual(self.preinit(shell).returncode,0)
            self.assertEqual(before,{p.name:p.read_bytes() for p in self.hw.iterdir()})

    def test_pre_cp_cannot_change_a_live_modem(self):
        import socket
        self.state.write_text(json.dumps(dict(self.initial,u30pro_card=2)))
        before={p.name:p.read_bytes() for p in self.hw.iterdir()}
        directory=self.run/'mu300-modem';directory.mkdir()
        for guard in ('marker','bridge'):
            bridge=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            if guard=='marker':(self.run/'u30pro-cp-started').touch()
            else:bridge.bind(str(directory/'io.sock'))
            try:
                for shell in self.each_shell():
                    r=self.preinit(shell)
                    self.assertNotEqual(r.returncode,0)
                    self.assertIn('cp_already_started',r.stderr)
                    self.assertEqual(before,{p.name:p.read_bytes() for p in self.hw.iterdir()})
            finally:
                bridge.close()
                (self.run/'u30pro-cp-started').unlink(missing_ok=True)
                (directory/'io.sock').unlink(missing_ok=True)

    def test_pre_cp_uses_product_map_not_the_identically_numbered_f50_board(self):
        for shell in self.each_shell():
            self.args.write_bytes(b'zteboot.zte_boardid=4\0')
            self.state.write_text(json.dumps(dict(self.initial,u30pro_card=3)))
            (self.hw/'psim_select').write_text('0\n')
            r=self.preinit(shell);self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual((self.hw/'psim_select').read_text().strip(),'1')
            self.assertFalse((self.tmp/'commands').exists())


    def test_all_stock_skus_do_not_reuse_v50_board_numbers(self):
        for shell in self.each_shell():
            for board,ids in [(0,[0,1,2,3]),(1,[0,1,2]),(2,[0,1]),(3,[0,1,3]),
                              (4,[0,1,2,3]),(5,[3]),(6,[0,2])]:
                self.args.write_bytes(f'zteboot.zte_boardid={board}\0'.encode())
                status=json.loads(self.call(shell,'status').stdout)
                self.assertEqual(status['cards'],ids)
                self.assertEqual(status['model'],'u30pro')
                for card in range(4):
                    r=self.call(shell,'validate',str(card))
                    self.assertEqual(r.returncode==0,card in ids,(board,card,r.stderr))
        self.assertFalse((self.tmp/'commands').exists())

    def test_cmdline_and_proc_precedence_and_unknown_id(self):
        for shell in self.each_shell():
            (self.root/'proc/cmdline').write_text('zteboot.zte_boardid=6 console=ttyS1')
            self.assertEqual(json.loads(self.call(shell,'status').stdout)['cards'],[0,2])
            (self.root/'proc/driver').mkdir(exist_ok=True)
            proc=self.root/'proc/driver/board_id';proc.write_text('5\n')
            self.assertEqual(json.loads(self.call(shell,'status').stdout)['cards'],[3])
            proc.write_text('99\n')
            self.assertFalse(json.loads(self.call(shell,'status').stdout)['supported'])
            self.assertNotEqual(self.call(shell,'apply','0').returncode,0)
            proc.unlink();(self.root/'proc/cmdline').unlink()
        self.assertFalse((self.tmp/'commands').exists())

    def test_all_board_selectors_report_only_fitted_sources_and_correct_imei_bank(self):
        reference=json.loads((TOP/'devices/u30pro/board-topology.json').read_text())
        for shell in self.each_shell():
            for board,ids in reference['board_cards'].items():
                self.args.write_bytes(f'zteboot.zte_boardid={board}\0'.encode())
                for chip,psim in [(0,0),(0,1),(1,0),(1,1)]:
                    (self.hw/'chip_select').write_text(str(chip));(self.hw/'psim_select').write_text(str(psim))
                    expected=[3 if psim else 0,2 if chip else 1]
                    expected=[card if card in ids else None for card in expected]
                    for stack in (0,1):
                        (self.run/'mu300-data-sim-actual').write_text(str(stack))
                        result=self.call(shell,'status')
                        self.assertEqual(result.returncode,0,result.stderr)
                        status=json.loads(result.stdout)
                        self.assertEqual(status['logical_cards'],expected,(board,chip,psim))
                        self.assertEqual(status['active_card'],expected[stack])
        self.assertFalse((self.tmp/'commands').exists(),'read-only mapping must never send AT')

    def test_single_standby_can_switch_back_to_disabled_first_stack(self):
        self.stub('mu300-radio-allowed','case "$1" in --dsds) echo 0;; *) exit 1;; esac')
        for shell in self.each_shell():
            state=dict(self.initial,data_sim=1);self.state.write_text(json.dumps(state))
            (self.hw/'psim_select').write_text('0\n')
            result=self.call(shell,'apply','0')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(self.state.read_text())['data_sim'],0)

    def test_physical_switch_reuses_rf_order_replay_and_rollback(self):
        for shell in self.each_shell():
            for target,attribute,stack in [(2,'chip_select',1),(3,'psim_select',0)]:
                self.state.write_text(json.dumps(self.initial))
                (self.tmp/'commands').unlink(missing_ok=True)
                for name in ('chip_select','psim_select'):(self.hw/name).write_text('0\n')
                r=self.call(shell,'apply',str(target));self.assertEqual(r.returncode,0,r.stderr)
                calls=(self.tmp/'commands').read_text()
                expected=[f'AT+SPACTCARD={stack};+SFUN=5',f'AT+SPACTCARD={stack};+SFUN=3',
                          'sleep 5',f'AT+SPACTCARD={stack};+SFUN=2',f'replay {stack} replay early',
                          f'AT+SPACTCARD={stack};+SFUN=4']
                positions=[calls.index(value) for value in expected]
                self.assertEqual(positions,sorted(positions))
                self.assertNotIn(f'AT+SPACTCARD={1-stack};+SFUN',calls)
                self.assertEqual((self.hw/attribute).read_text().strip(),'1')
                self.assertEqual(json.loads(self.state.read_text())['u30pro_card'],target)

    def test_chip_route_uses_second_logical_stack_and_keeps_saved_policy(self):
        for shell in self.each_shell():
            self.state.write_text(json.dumps(self.initial))
            (self.hw/'chip_select').write_text('0\n')
            r=self.call(shell,'apply','2');self.assertEqual(r.returncode,0,r.stderr)
            state=json.loads(self.state.read_text())
            self.assertEqual((state['data_sim'],state['u30pro_card']),(1,2))
            calls=(self.tmp/'commands').read_text()
            self.assertIn('AT+SPACTCARD=1;+SFUN=5',calls)
            self.assertNotIn('AT+SPACTCARD=2;',calls)
            self.assertFalse((self.run/'mu300/u30pro-switch-incomplete').exists())

    def test_factory_board6_boot_routes_chip3_and_never_raises_rf(self):
        for shell in self.each_shell():
            self.args.write_bytes(b'zteboot.zte_boardid=6\0')
            state=dict(self.initial);state.pop('u30pro_card')
            self.state.write_text(json.dumps(state));(self.hw/'chip_select').write_text('0\n')
            (self.tmp/'commands').unlink(missing_ok=True)
            r=self.sh(shell,'ln -s $$ "$MU300_U30PRO_RUN/mu300-radio-on.owner"\n"$MU300_BIN/mu300-u30pro-sim" boot\nrc=$?\nrm -f "$MU300_U30PRO_RUN/mu300-radio-on.owner"\nexit $rc',**self.extra)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual((self.hw/'chip_select').read_text().strip(),'1')
            calls=(self.tmp/'commands').read_text()
            self.assertIn('AT+SPACTCARD=1;+SFUN=2',calls)
            self.assertNotIn('+SFUN=4',calls)
            self.assertNotIn('ifdown',calls)

    def test_matching_boot_route_adds_no_at_or_delay(self):
        for shell in self.each_shell():
            self.args.write_bytes(b'zteboot.zte_boardid=2\0')
            (self.hw/'chip_select').write_text('0\n');(self.hw/'psim_select').write_text('0\n')
            (self.tmp/'commands').unlink(missing_ok=True)
            r=self.sh(shell,'ln -s $$ "$MU300_U30PRO_RUN/mu300-radio-on.owner"\n"$MU300_BIN/mu300-u30pro-sim" boot\nrc=$?\nrm -f "$MU300_U30PRO_RUN/mu300-radio-on.owner"\nexit $rc',**self.extra)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertFalse((self.tmp/'commands').exists())


if __name__=='__main__':
    import unittest
    unittest.main(verbosity=2)
