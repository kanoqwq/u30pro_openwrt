"""Legacy differential-update identity repair, without devices or modem access."""
import json
import os
from pathlib import Path
import runpy
import tempfile
import unittest


TOP = Path(__file__).resolve().parents[1]
SCRIPT = TOP / 'devices/u30pro/overlay/usr/sbin/u30pro-product-identity'
prepare = runpy.run_path(str(SCRIPT))['prepare']


class ProductIdentity(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='pro-identity-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.base = self.root / 'etc/mu300'
        self.base.mkdir(parents=True)
        self.mux = self.root / 'sys/bus/platform/devices/sim_gpio_ctl'
        self.mux.mkdir(parents=True)
        self.marker = self.base / 'model'
        (self.base / 'platform').write_text('u30pro\n')
        self.product('u30pro')
        # Sentinel GPIO values and unrelated user configuration must survive.
        (self.mux / 'chip_select').write_text('1\n')
        (self.mux / 'psim_select').write_text('0\n')
        (self.base / 'hotspot.conf').write_text('user settings\n')
        self.before = {p: p.read_bytes() for p in (
            self.mux / 'chip_select', self.mux / 'psim_select', self.base / 'hotspot.conf')}

    def tearDown(self):
        for path, content in self.before.items():
            self.assertEqual(path.read_bytes(), content)
        self.assertFalse(list(self.base.glob('.model-*')))

    def product(self, name):
        (self.base / 'release.json').write_text(json.dumps({'profile': name}))
        (self.mux / 'layout').write_text({'u30pro': 'mu5358', 'f50pro': 'mu3356'}[name] + '\n')

    def test_missing_marker_is_restored_for_both_products(self):
        for name in ('u30pro', 'f50pro'):
            with self.subTest(product=name):
                self.product(name)
                self.assertEqual(prepare(self.root, restore=True), name)
                self.assertEqual(self.marker.read_bytes(), (name + '\n').encode())
                self.assertEqual(self.marker.stat().st_mode & 0o777, 0o644)
                self.marker.unlink()

    def test_read_only_check_does_not_repair(self):
        with self.assertRaisesRegex(ValueError, 'missing'):
            prepare(self.root)
        self.assertFalse(self.marker.exists())

    def test_existing_identity_is_not_rewritten(self):
        self.marker.write_text('u30pro\n')
        before = self.marker.stat()
        self.assertEqual(prepare(self.root, restore=True), 'u30pro')
        self.assertEqual(self.marker.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertEqual(self.marker.stat().st_ino, before.st_ino)

    def test_product_and_hardware_mismatch_both_directions(self):
        for product, wrong in (('u30pro', 'mu3356'), ('f50pro', 'mu5358')):
            self.product(product)
            (self.mux / 'layout').write_text(wrong)
            with self.assertRaisesRegex(ValueError, 'layout disagree'):
                prepare(self.root, restore=True)
            self.assertFalse(self.marker.exists())

    def test_existing_invalid_or_empty_marker_is_not_overwritten(self):
        for value in ('', 'bogus\n'):
            self.marker.write_text(value)
            with self.assertRaisesRegex(ValueError, 'unsupported product marker'):
                prepare(self.root, restore=True)
            self.assertEqual(self.marker.read_text(), value)

    def test_existing_valid_marker_does_not_add_release_or_mux_requirements(self):
        (self.base / 'release.json').unlink()
        (self.base / 'platform').unlink()
        (self.mux / 'layout').unlink()
        for product in ('u30pro', 'f50pro'):
            self.marker.write_text(product + '\n')
            self.assertEqual(prepare(self.root, restore=True), product)
            self.assertEqual(self.marker.read_text(), product + '\n')

    def test_existing_valid_symlink_is_preserved(self):
        target = self.base / 'custom-product'
        target.write_text('u30pro\n')
        self.marker.symlink_to(target)
        self.assertEqual(prepare(self.root, restore=True), 'u30pro')
        self.assertTrue(self.marker.is_symlink())

    def test_release_and_platform_are_required(self):
        for release in ('{}', '{"profile":"mu300"}', 'broken json', '[]'):
            (self.base / 'release.json').write_text(release)
            with self.assertRaises((ValueError, KeyError, TypeError)):
                prepare(self.root, restore=True)
            self.assertFalse(self.marker.exists())
        self.product('u30pro')
        (self.base / 'platform').write_text('mu300')
        with self.assertRaisesRegex(ValueError, 'platform'):
            prepare(self.root, restore=True)
        (self.base / 'platform').unlink()
        with self.assertRaises(OSError):
            prepare(self.root, restore=True)

    def test_missing_mux_and_symlink_marker_are_rejected(self):
        (self.mux / 'layout').unlink()
        with self.assertRaises(OSError):
            prepare(self.root, restore=True)
        self.product('u30pro')
        self.marker.symlink_to(self.base / 'missing-product')
        with self.assertRaisesRegex(ValueError, 'regular file'):
            prepare(self.root, restore=True)

    def test_concurrent_matching_repair_is_safe(self):
        from unittest.mock import patch
        link = os.link
        def race(source, target):
            target.write_text('u30pro\n')
            link(source, target)
        with patch('os.link', side_effect=race):
            self.assertEqual(prepare(self.root, restore=True), 'u30pro')
        self.assertEqual(self.marker.read_text(), 'u30pro\n')

    def test_concurrent_conflicting_repair_is_not_overwritten(self):
        from unittest.mock import patch
        def race(source, target):
            target.write_text('f50pro\n')
            raise FileExistsError()
        with patch('os.link', side_effect=race):
            with self.assertRaisesRegex(ValueError, 'changed during'):
                prepare(self.root, restore=True)
        self.assertEqual(self.marker.read_text(), 'f50pro\n')

    def test_identity_precedes_form_and_sim_initialization(self):
        service = (TOP / 'devices/u30pro/overlay/etc/init.d/mu300-vendor').read_text()
        self.assertLess(service.index('u30pro-product-identity --restore'), service.index('product-form boot'))
        self.assertLess(service.index('product-form boot'), service.index('u30pro-sim-preinit'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
