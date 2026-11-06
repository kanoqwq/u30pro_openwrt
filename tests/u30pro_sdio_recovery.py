#!/usr/bin/env python3
"""Compile actual SDIO recovery/tuning functions against offline fault fixtures."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
TOP=Path(__file__).resolve().parents[1]
BASE=TOP/'devices/u30pro/native/kernel/ums9632/overlay/drivers'
HOST=BASE/'mmc/host/sdhci-sprd.c'
AIC=BASE/'unisoc_platform/aic8800/aic8800_fdrv'


def function(text,name):
    m=re.search(r'^(?:static )?(?:int|bool|void) '+name+r'\([^;]*?\)\s*\{',text,re.M)
    if not m: raise AssertionError(name)
    end=m.end();depth=1
    while depth: depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[m.start():end]


@unittest.skipUnless(os.name=='posix','native kernel fault fixtures require POSIX')
class Recovery(unittest.TestCase):
    def compile_run(self,code):
        with tempfile.TemporaryDirectory(prefix='pro-sdio-recovery-') as temp:
            folder=Path(temp);src=folder/'test.c';out=folder/'test';src.write_text(code)
            result=subprocess.run(['clang','-std=gnu11','-g','-O1','-pthread','-Wall','-Wextra','-Werror',
                '-Wno-unused-parameter','-Wno-unused-variable','-Wno-unused-function','-Wno-sign-compare',
                '-fsanitize=address,undefined','-fno-omit-frame-pointer',str(src),'-o',str(out)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(out)],capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_actual_tuning_complete_scan_rollback_temperature_and_lifecycle(self):
        source=HOST.read_text()
        state=source[source.index('#define SDIO_T_NONE'):source.index('struct sdhci_sprd_host {')]
        names=['sdhci_sprd_sdio_temperatures','sdhci_sprd_sdio_tune_work','sdhci_sprd_sdio_activity',
               'sdhci_sprd_sdio_tune_init','sdhci_sprd_sdio_tune_pause','sdhci_sprd_sdio_tune_resume',
               'sdhci_sprd_sdio_try','sdhci_sprd_sdio_execute_tuning']
        self.compile_run((TOP/'tests/fixtures/sdio_tuning.c').read_text().replace('/* PRODUCTION_STATE */',state)
                         .replace('/* PRODUCTION_FUNCTIONS */','\n'.join(function(source,n) for n in names)))

    def test_credit_retries_and_actual_send_never_replay_partial_fifo(self):
        header=re.sub(r'^#include <linux/[^>]+>\n','',(AIC/'aicwf_sdio_recovery.h').read_text(),flags=re.M)
        source=(AIC/'aicwf_sdio.c').read_text()
        self.compile_run((TOP/'tests/fixtures/aic_sdio_recovery.c').read_text().replace('/* PRODUCTION_HEADER */',header)
                         .replace('/* PRODUCTION_SEND */',function(source,'aicwf_sdio_send_pkt')))

    def test_production_power_and_remove_wiring(self):
        source=HOST.read_text()
        for n in ['sdhci_sprd_remove','sdhci_sprd_runtime_suspend']:
            f=function(source,n)
            self.assertLess(f.index('sdhci_sprd_sdio_tune_pause'),f.index('clk_disable_unprepare'))
        self.assertLess(function(source,'sdhci_sprd_remove').index('sdhci_sprd_sdio_tune_pause'),
                        function(source,'sdhci_sprd_remove').index('sdhci_remove_host'))
        self.assertIn('cancel_work_sync',function(source,'sdhci_sprd_sdio_tune_pause'))
        work=function(source,'sdhci_sprd_sdio_tune_work')
        self.assertNotIn('schedule_',work);self.assertNotIn('delayed_work',source)
        self.assertNotIn('sdio_inject',source)
        self.assertLess(work.index('sdhci_sprd_sdio_temperatures'),work.index('mutex_lock'))
        self.assertNotIn('thermal_zone_get_temp',function(source,'sdhci_sprd_sdio_execute_tuning'))
        probe=function(source,'sdhci_sprd_probe')
        self.assertLess(probe.index('sdhci_sprd_sdio_tune_init'),probe.index('__sdhci_add_host'))
        self.assertIn('sdhci_sprd_sdio_tune_pause(host, true)',source[source.index('err_cleanup_host:'):])

    def test_card_setup_and_fifo_errors_preserve_non_replay_semantics(self):
        for path in [AIC/'aicwf_sdio.c',AIC.parent/'aic8800_bsp/aicsdio.c']:
            text=path.read_text();start=text.index('int aicwf_sdiov3_func_init(')
            text=text[start:text.index('\n}',start)]
            self.assertGreater(text.index('mmc_retune_needed(host)'),text.rindex('aicwf_sdio_writeb('))
        text=(AIC/'aicwf_sdio.c').read_text()
        self.assertEqual(text.count('aicwf_sdio_fifo_error(sdiodev->func, ret)'),3)
        self.assertEqual(text.count('sdio_writesb(sdiodev->func, sdiodev->sdio_reg.wr_fifo_addr, buf, count)'),1)
        self.assertIn('regaddr == sdiodev->sdio_reg.flow_ctrl_reg',text)
        self.assertNotIn('sdio_retune_crc_disable(func)',text)

if __name__=='__main__': unittest.main(verbosity=2)
