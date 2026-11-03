"""Retained roots can be rebuilt after archives/checkouts move; wrong roots cannot."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


TOP = Path(__file__).resolve().parents[1]
package = None
if os.name == 'posix':
    spec = importlib.util.spec_from_file_location('u30pro_package', TOP/'tools/u30pro-package.py')
    package = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package)


class SourceCopyReached(Exception):
    pass


@unittest.skipUnless(os.name == 'posix', 'firmware staging runs on Linux')
class RetainedRoot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.stage = self.work/'package-work/u30pro-release'
        self.root = self.stage/'root'
        (self.root/'etc/mu300').mkdir(parents=True)
        (self.root/'etc/mu300/platform').write_text('u30pro\n')
        (self.stage/'.owner').write_text(package.OWNER+'\n')
        self.state = {'base': package.BASE_SHA, 'step': 'packaged',
                      'release': str(self.work/'deleted-checkout/old.zip'),
                      'sha256': '0'*64}
        self.save()
        for name, value in [('WORK', self.work), ('STAGE', self.stage), ('ROOT', self.root)]:
            patcher = mock.patch.object(package, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(package, 'copy_tree', side_effect=SourceCopyReached)
        self.copy = patcher.start()
        self.addCleanup(patcher.stop)

    def save(self):
        (self.stage/'state.json').write_text(json.dumps(self.state))

    def test_missing_previous_archive_does_not_block_current_source_copy(self):
        self.assertFalse(Path(self.state['release']).exists())
        for refresh in (False, True):
            with self.subTest(refresh=refresh), self.assertRaises(SourceCopyReached):
                package.sources(refresh=refresh)
        self.assertEqual(json.loads((self.stage/'state.json').read_text()), self.state)

    def test_wrong_base_stops_before_copy(self):
        self.state['base'] = 'other-base'
        self.save()
        with self.assertRaisesRegex(ValueError, 'different OpenWrt base'):
            package.sources()
        self.copy.assert_not_called()

    def test_wrong_platform_stops_before_copy(self):
        (self.root/'etc/mu300/platform').write_text('f50\n')
        with self.assertRaisesRegex(ValueError, 'U30 Pro profile'):
            package.sources()
        self.copy.assert_not_called()

    def test_unowned_root_stops_before_copy(self):
        (self.stage/'.owner').write_text('another-task\n')
        with self.assertRaisesRegex(ValueError, 'Unowned'):
            package.sources()
        self.copy.assert_not_called()

    def test_unfinished_dependency_install_stops_before_copy(self):
        self.state['step'] = 'base-extracted'
        self.save()
        with self.assertRaisesRegex(ValueError, 'dependency installation'):
            package.sources()
        self.copy.assert_not_called()

    def test_symlinked_root_stops_before_copy(self):
        outside = self.work/'outside'
        self.root.rename(outside)
        try:
            self.root.symlink_to(outside, target_is_directory=True)
        except OSError:
            outside.rename(self.root)
            self.skipTest('Host does not permit directory symlinks')
        with self.assertRaisesRegex(ValueError, 'escaped'):
            package.sources()
        self.copy.assert_not_called()

    def test_new_applet_replaces_only_its_legacy_generated_shim(self):
        aliases=self.root/'opt/mu300/busybox-bin'
        aliases.mkdir(parents=True)
        (aliases/'mountpoint').write_text('#!/bin/sh\nlegacy shim\n')
        (self.root/'bin').mkdir()
        real=self.root/'bin/mountpoint'
        real.write_bytes(b'package-owned executable')
        package.busybox_aliases(self.root,['mountpoint'])
        self.assertTrue((aliases/'mountpoint').is_symlink())
        self.assertEqual(os.readlink(aliases/'mountpoint'),'../bin/busybox')
        self.assertEqual(real.read_bytes(),b'package-owned executable')
        package.busybox_aliases(self.root,['mountpoint'])
        self.assertTrue((aliases/'mountpoint').is_symlink())

    def test_applet_path_cannot_escape_generated_aliases(self):
        with self.assertRaisesRegex(ValueError,'Invalid busybox applet'):
            package.busybox_aliases(self.root,['../outside'])
        self.assertFalse((self.root/'opt/mu300/outside').exists())


if __name__ == '__main__':
    unittest.main()
