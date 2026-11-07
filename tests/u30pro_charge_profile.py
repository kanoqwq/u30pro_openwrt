"""Compile the real shared profile selector and charger DT loader with OF fixtures."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from u30pro_charge_sources import DRIVER, TOP, declaration


@unittest.skipUnless(os.name == 'posix', 'host C compiler')
class ChargeProfile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        root = Path(cls.temp.name)
        helper = (DRIVER/'u30pro-battery-profile.h').read_text()
        helper = re.sub(r'^#include.*$', '', helper, flags=re.M)
        source = (TOP/'tests/fixtures/u30pro_battery_profile.c').read_text()
        source = source.replace('/* PROFILE_HELPER */', helper).replace(
            '/* TABLE_LOADER */', declaration(r'^static int sgm_load_tables\([^;{}]*\)\s*\{'))
        (root/'test.c').write_text(source)
        cls.binary = root/'profile'
        subprocess.run(['gcc', '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                        '-Wno-sign-compare', str(root/'test.c'), '-o', str(cls.binary)], check=True)

    def case(self, n):
        subprocess.run([str(self.binary), str(n)], check=True, timeout=5)

    def test_live_battery_zero_profile(self): self.case(1)
    def test_second_profile_uses_its_own_current_and_voltage(self): self.case(2)
    def test_unknown_id_never_silently_selects_first_battery(self): self.case(3)
    def test_missing_malformed_and_out_of_range_id(self): self.case(4)
    def test_missing_or_wrong_selected_phandle_does_not_fall_back(self): self.case(5)
    def test_bad_id_table_and_adc_reference_preserve_node_lifetimes(self): self.case(6)
    def test_stock_short_resistor_id(self): self.case(7)
    def test_invalid_voltage_and_jeita_never_enable_policy(self): self.case(8)


if __name__ == '__main__': unittest.main(verbosity=2)
