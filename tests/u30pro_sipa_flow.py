#!/usr/bin/env python3
"""Actual SIPA request/flow functions: reordered grants and concurrent callbacks."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

TOP = Path(__file__).resolve().parents[1]
BASE = TOP / 'devices/u30pro/native/kernel/ums9632/overlay/drivers/unisoc_platform/net/sipa_v3'


def function(text, name):
    m = re.search(r'^static (?:int|bool|void) ' + name + r'\([^;]*?\)\s*\{', text, re.M)
    if not m:
        raise AssertionError(name)
    end, depth = m.end(), 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[m.start():end]


@unittest.skipUnless(os.name == 'posix', 'POSIX kernel fixture')
class Flow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='pro-sipa-flow-')
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name)
        source = (BASE / 'sipa_nic.c').read_text()
        body = '\n'.join(function(source, n) for n in (
            'sipa_nic_rm_res_granted', 'sipa_nic_rm_res_request', 'sipa_nic_sync_flow_ctrl'))
        code = (TOP / 'tests/fixtures/sipa_flow_control.c').read_text().replace('/* PRODUCTION_FUNCTIONS */', body)
        c = folder / 'flow.c'
        cls.exe = folder / 'flow'
        c.write_text(code)
        result = subprocess.run(['clang', '-std=gnu11', '-O1', '-g', '-pthread', '-Wall', '-Wextra', '-Werror',
                                 '-fsanitize=address,undefined', str(c), '-o', str(cls.exe)], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)

    def scenario(self, n):
        result = subprocess.run([str(self.exe), str(n)], capture_output=True, text=True, timeout=12)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_grant_before_delayed_enter(self): self.scenario(0)
    def test_pending_then_grant(self): self.scenario(1)
    def test_callback_completion_cannot_overtake(self): self.scenario(2)
    def test_overlap_and_stale_fifo_work(self): self.scenario(3)
    def test_immediate_grant_clears_pending(self): self.scenario(4)
    def test_grant_inside_request_does_not_rearm_wait(self): self.scenario(5)
    def test_real_pending_keeps_queue_stopped(self): self.scenario(6)
    def test_request_error_is_propagated_and_retryable(self): self.scenario(7)
    def test_closed_nic_ignores_late_notifications(self): self.scenario(8)
    def test_separate_nics(self): self.scenario(9)
    def test_parallel_repeated_resource_cycles(self): self.scenario(10)

    def test_production_lifetime_and_irq_wiring(self):
        text = (BASE / 'sipa_nic.c').read_text()
        self.assertLess(text.index('spin_lock_init(&nic->flow_lock)'), text.index('ret = sipa_nic_register_rm'))
        close = text[text.index('void sipa_nic_close('):]
        self.assertLess(close.index('atomic_set(&nic->status, NIC_CLOSE)'), close.index('cancel_work_sync'))
        for filename in ('sipa_eth.c', 'sipa_usb.c'):
            source = (BASE / filename).read_text()
            self.assertNotIn('static unsigned long queue_lock_flags', source)
            self.assertIn('unsigned long flags;', source)
        sender = (BASE / 'sipa_skb_send.c').read_text()
        self.assertIn('WRITE_ONCE(sender->fifo_flowctrl, true)', sender)
        self.assertIn('WRITE_ONCE(sender->fifo_flowctrl, false)', sender)


if __name__ == '__main__':
    unittest.main(verbosity=2)
