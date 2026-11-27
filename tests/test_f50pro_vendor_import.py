"""Run the stock-runtime importer against private Android filesystem fixtures."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from helpers import TOP, shells


class StockCardImport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='f50pro-stock-import-')
        self.base = Path(self.temp.name)
        self.root = self.base / 'root'
        self.android = self.base / 'android'
        self.payload = self.base / 'payload'
        self.commands = self.base / 'bin'
        for path in (self.root/'etc/mu300', self.android/'vendor/etc',
                     self.android/'odm/firmware/aic8800', self.android/'proc',
                     self.android/'sys/module/sim_gpio_ctl/parameters',
                     self.payload, self.commands):
            path.mkdir(parents=True, exist_ok=True)
        (self.root/'etc/mu300/platform').write_text('u30pro\n')
        (self.root/'etc/mu300/model').write_text('f50pro\n')
        lib = self.root/'opt/mu300/lib/f50pro-card.sh'
        lib.parent.mkdir(parents=True)
        shutil.copyfile(TOP/'devices/f50pro/overlay/opt/mu300/lib/f50pro-card.sh', lib)
        (self.android/'proc/cmdline').write_text('zteboot.zte_boardid=4\n')
        for name in ('modem_cp_info.xml', 'modem_sp_info.xml', 'modem_ch_info.xml'):
            (self.android/'vendor/etc'/name).write_text('<fixture/>\n')
        (self.android/'odm/firmware/aic8800/fw.bin').write_bytes(b'fixture firmware')
        (self.payload/'u30pro-map.tsv').write_text('modem /dev/block/by-name/modem\n')
        self.stub('getprop', 'echo MU3356\n')
        self.stub('uci', 'exit 1\n')
        # The Android settings tool receives: get system <key>.
        self.stub('settings', 'case "$3" in zte_webserver_sim_slot_id) echo "${STOCK_CARD:-4}";; car_mode_dual_sim_switch) echo 0;; esac\n')
        source = (TOP/'tools/mu300-vendor-from-device.sh').read_text()
        source = re.sub(r'(?<![\w/])/(vendor|odm|sys)/',
                        lambda m: str(self.android)+'/'+m.group(1)+'/', source)
        self.script = self.base/'vendor-import.sh'
        self.script.write_text(source)
        self.env = dict(os.environ, PATH=str(self.commands)+os.pathsep+os.environ['PATH'],
                        MU300_SYSROOT=str(self.android), MU300_PAYLOAD_DIR=str(self.payload),
                        MU300_U30PRO_RUN=str(self.base/'run'))

    def stub(self, name, body):
        path = self.commands/name
        path.write_text('#!/bin/sh\n'+body)
        path.chmod(0o755)

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, shell, *, card='4', chip='00', psim='1'):
        for name, value in (('gpio_sim_ctrl', chip), ('gpio_sim_ctrl_psim', psim)):
            path = self.android/'sys/module/sim_gpio_ctl/parameters'/name
            if value is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(value+'\n')
        return subprocess.run(shell+[str(self.script), str(self.root), 'openwrt'],
                              env=dict(self.env, STOCK_CARD=card), text=True,
                              capture_output=True, timeout=10)

    def test_consistent_selection_stages_current_sources(self):
        for shell in shells():
            with self.subTest(shell=shell):
                result = self.invoke(shell)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                text = (self.root/'etc/uci-defaults/99-zz-f50pro-card').read_text()
                self.assertIn("f50pro_route0='0'", text)
                self.assertIn("f50pro_route1='4'", text)

    def test_stale_saved_card_does_not_abort_runtime_import(self):
        for shell in shells():
            with self.subTest(shell=shell):
                result = self.invoke(shell, chip='01')
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                self.assertIn('inconsistent', result.stderr)
                self.assertFalse((self.root/'etc/uci-defaults/99-zz-f50pro-card').exists())
                self.assertTrue((self.root/'opt/mu300/vendor/u30pro/modem/modem_cp_info.xml').is_file())

    def test_incomplete_selector_snapshot_does_not_import_a_partial_pair(self):
        for shell in shells():
            result = self.invoke(shell, psim=None)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertIn('inconsistent', result.stderr)
            self.assertFalse((self.root/'etc/uci-defaults/99-zz-f50pro-card').exists())

    def test_reported_board4_snapshot_keeps_defaults_and_completes_import(self):
        # Reported Android values: saved card 0, getter "10", psim 0.
        for shell in shells():
            result = self.invoke(shell, card='0', chip='10', psim='0')
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertIn('board=4 card=0 chip=0 psim=0', result.stderr)
            self.assertFalse((self.root/'etc/uci-defaults/99-zz-f50pro-card').exists())

    def test_no_selector_snapshot_still_imports_a_valid_saved_card(self):
        for shell in shells():
            result = self.invoke(shell, chip=None, psim=None)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            script = (self.root/'etc/uci-defaults/99-zz-f50pro-card').read_text()
            self.assertIn("f50pro_card='4'", script)
            self.assertNotIn('f50pro_route0=', script)

    def test_missing_required_firmware_remains_fatal(self):
        (self.android/'odm/firmware/aic8800/fw.bin').unlink()
        for shell in shells():
            self.assertNotEqual(self.invoke(shell).returncode, 0)

    def test_missing_required_modem_xml_remains_fatal(self):
        (self.android/'vendor/etc/modem_cp_info.xml').unlink()
        for shell in shells():
            result = self.invoke(shell)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Missing U30 Pro modem XML', result.stderr)

    def test_valid_card_import_write_failure_remains_fatal(self):
        (self.root/'etc/uci-defaults').write_text('occupied path\n')
        for shell in shells():
            self.assertNotEqual(self.invoke(shell).returncode, 0)

    def test_failed_defaults_write_cannot_be_reported_as_skipped_metadata(self):
        defaults = self.root/'etc/uci-defaults'
        defaults.mkdir()
        (defaults/'99-zz-f50pro-card').symlink_to('/dev/full')
        for shell in shells():
            result = self.invoke(shell)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Failed to write initial F50 Pro SIM settings', result.stderr)

    def test_u30pro_never_imports_the_f50pro_card_snapshot(self):
        (self.root/'etc/mu300/model').write_text('u30pro\n')
        for shell in shells():
            result = self.invoke(shell, card='0', chip='10', psim='0')
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertFalse((self.root/'etc/uci-defaults/99-zz-f50pro-card').exists())
            self.assertNotIn('inconsistent', result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
