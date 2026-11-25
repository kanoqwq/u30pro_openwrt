"""Run real Pro SIPA TX, completion and netdev notifier functions with host DMA."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

TOP = Path(__file__).resolve().parents[1]
BASE = Path(os.environ.get('SIPA_TEST_SOURCE', TOP / 'devices/u30pro/native/kernel/ums9632/overlay/drivers/unisoc_platform/net/sipa_v3'))


def function(text, name):
    match = re.search(r'^static [\w *]+\b' + name + r'\([^;]*?\)\s*\{', text, re.M)
    if not match:
        raise AssertionError(name)
    end, depth = match.end(), 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[match.start():end]


@unittest.skipUnless(os.name == 'posix', 'POSIX C fixtures')
class Datapath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='pro-sipa-datapath-')
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name)
        cls.executables = {}
        for fixture, filename, names in (
            ('tx', 'sipa_eth.c', ('sipa_eth_start_xmit',)),
            ('completion', 'sipa_skb_send.c', ('sipa_do_free_skb', 'sipa_free_sent_items')),
            ('notifier', 'sipa_dummy.c', ('sipa_dummy_netdev_event_handler',)),
        ):
            body = '\n'.join(function((BASE / filename).read_text(), name) for name in names)
            code = (TOP / f'tests/fixtures/sipa_{fixture}.c').read_text().replace('/* PRODUCTION_FUNCTIONS */', body)
            source = folder / (fixture + '.c')
            source.write_text(code)
            exe = source.with_suffix('')
            result = subprocess.run(['clang', '-std=gnu11', '-O1', '-g', '-pthread',
                                     '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                                     str(source), '-o', str(exe)], capture_output=True, text=True)
            if result.returncode:
                raise AssertionError(result.stderr)
            cls.executables[fixture] = exe

    def scenario(self, fixture, scenario):
        result = subprocess.run([str(self.executables[fixture]), str(scenario)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_tx_all_headroom_sizes_and_repeated_busy(self): self.scenario('tx', 0)
    def test_tx_failed_linearization_consumes_skb(self): self.scenario('tx', 1)
    def test_tx_failed_cow_consumes_skb(self): self.scenario('tx', 2)
    def test_tx_permanent_failure_drops_once(self): self.scenario('tx', 3)
    def test_tx_down_interface_drops_once(self): self.scenario('tx', 4)
    def test_native_ncm_never_changes_ipa_mode(self): self.scenario('notifier', 0)
    def test_legacy_sipa_usb_balances_up_and_down(self): self.scenario('notifier', 1)
    def test_notifier_does_not_match_usb_name_prefix(self): self.scenario('notifier', 2)
    def test_completions_return_all_owned_credits(self): self.scenario('completion', 0)
    def test_duplicate_completion_does_not_invent_credit(self): self.scenario('completion', 1)
    def test_unmatched_does_not_skip_following_packets(self): self.scenario('completion', 2)
    def test_stale_descriptor_resyncs_outside_lock(self): self.scenario('completion', 3)
    def test_partial_batch_advances_only_consumed_prefix(self): self.scenario('completion', 4)
    def test_flow_requeue_runs_outside_send_lock(self): self.scenario('completion', 5)
    def test_empty_sender_drains_spurious_completion(self): self.scenario('completion', 6)
    def test_unmatched_never_frees_different_owned_skb(self): self.scenario('completion', 7)
    def test_concurrent_completion_detaches_owned_skb_once(self): self.scenario('completion', 8)


if __name__ == '__main__':
    unittest.main(verbosity=2)
