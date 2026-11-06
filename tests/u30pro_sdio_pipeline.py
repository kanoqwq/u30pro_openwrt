#!/usr/bin/env python3
"""Run the production AIC queue/aggregate code with pthread SDIO fault injection.

No device access. The shim replaces kernel scheduling and bus I/O, not the
production ring, boundary checks, aggregate packing or producer logic.
"""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import unittest

TOP = Path(__file__).resolve().parents[1]
DRIVER = TOP / 'devices/u30pro/native/kernel/ums9632/overlay/drivers/unisoc_platform/aic8800/aic8800_fdrv'


def function(source, name):
    match = re.search(r'^(?:static )?(?:int|void) ' + name + r'\([^;]*?\)\s*\{', source, re.M)
    if not match:
        raise AssertionError(name)
    end = match.end()
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[match.start():end]


@unittest.skipUnless(os.name == 'posix', 'kernel scheduling fixtures require POSIX')
class Pipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='aic-txpipe-')
        cls.root = Path(cls.tmp.name)
        header = re.sub(r'^#include <linux/[^>]+>\n', '',
                        (DRIVER / 'aicwf_txpipe.h').read_text(), flags=re.M)
        src = (DRIVER / 'aicwf_sdio.c').read_text()
        code = (TOP / 'tests/fixtures/aic_sdio_pipeline.c').read_text()
        functions = '\n\n'.join(function(src, name) for name in (
            'tx_aggr_set', 'aicwf_sdio_aggrbuf_reset', 'aicwf_sdio_aggr_send',
            'aicwf_sdio_aggr', 'aicwf_sdio_send'))
        code = code.replace('/* PRODUCTION_HEADER */', header)
        code = code.replace('/* PRODUCTION_FUNCTIONS */', functions)
        source = cls.root / 'pipeline.c'
        source.write_text(code)
        cls.exe = cls.root / 'pipeline'
        cmd = [os.environ.get('CC', 'clang'), '-std=gnu11', '-O1', '-g', '-pthread',
               '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
               '-Wno-unused-variable', '-Wno-sign-compare',
               '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
               str(source), '-o', str(cls.exe)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        life = (TOP / 'tests/fixtures/aic_sdio_lifecycle.c').read_text()
        transport = (DRIVER / 'aicwf_txrxif.c').read_text()
        life = life.replace('/* PRODUCTION_FUNCTIONS */', '\n\n'.join(
            function(transport, name) for name in ('aicwf_bus_deinit', 'aicwf_bus_init')))
        life_source = cls.root / 'lifecycle.c'
        life_source.write_text(life)
        cls.life = cls.root / 'lifecycle'
        result = subprocess.run(cmd[:-3] + [str(life_source), '-o', str(cls.life)],
                                capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_case(self, name):
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=1:abort_on_error=1')
        result = subprocess.run([str(self.exe), name], env=env,
                                capture_output=True, text=True, timeout=25)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_order_buffer_ownership_and_overlap(self): self.run_case('order')
    def test_cancel_wakes_full_queue_without_freeing_inflight(self): self.run_case('cancel')
    def test_sdio_error_is_latched_and_never_replayed(self): self.run_case('io-error')
    def test_full_queue_timeout_keeps_inflight_memory(self): self.run_case('queue-timeout')
    def test_drain_timeout_keeps_inflight_memory(self): self.run_case('drain-timeout')
    def test_allocation_and_thread_failure_unwind(self): self.run_case('init-fail')
    def test_separate_devices_and_idle_teardown(self): self.run_case('two-devices')
    def test_parameter_and_byte_boundaries(self): self.run_case('bounds')
    def test_real_aggregate_padding_and_rotating_buffers(self): self.run_case('packing')
    def test_real_producer_byte_flush_and_credit_order(self): self.run_case('producer')
    def test_lowered_limit_flushes_an_existing_aggregate(self): self.run_case('lower-limit')
    def test_invalid_aggregate_is_rejected_before_bus_io(self): self.run_case('invalid-aggregate')

    def test_real_bus_partial_start_failures_and_teardown(self):
        result = subprocess.run([str(self.life)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_lifecycle_and_power_integration(self):
        src = (DRIVER / 'aicwf_sdio.c').read_text()
        release = function(src, 'aicwf_sdio_release')
        self.assertLess(release.index('aicwf_txpipe_join'), release.index('sdio_claim_host'))
        self.assertLess(release.index('aicwf_bus_deinit'), release.index('aicwf_txpipe_destroy'))
        self.assertLess(release.index('kthread_stop(sdiodev->pwrctl_tsk)'),
                        release.index('aicwf_bus_deinit'))
        deinit = function((DRIVER / 'aicwf_txrxif.c').read_text(), 'aicwf_bus_deinit')
        for name in ('bustx_thread', 'busirq_thread', 'busrx_thread'):
            self.assertLess(deinit.index('kthread_stop(bus_if->' + name + ')'),
                            deinit.index('rwnx_platform_deinit'))
        stop = function(src, 'aicwf_sdio_bus_stop')
        self.assertLess(stop.index('aicwf_txpipe_cancel'), stop.index('down_interruptible'))
        for name in ('aicwf_sdio_flow_ctrl', 'aicwf_sdio_flow_ctrl_msg', 'aicwf_sdio_tx_msg'):
            func = function(src, name)
            self.assertIn('aicwf_txpipe_drain', func)
            if 'sdio_claim_host' in func:
                self.assertLess(func.index('aicwf_txpipe_drain'), func.index('sdio_claim_host'))
        for name in ('aicwf_sdio_sleep_allow', 'aicwf_sdio_pwrctl_thread'):
            self.assertIn('!aicwf_txpipe_busy', function(src, name))
        self.assertIn('module_param(tx_pipeline, bool, 0444)', src)
        self.assertNotIn('freq_qos_', src)


if __name__ == '__main__':
    unittest.main(verbosity=2)
