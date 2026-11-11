"""Retained roots can be rebuilt after archives/checkouts move; wrong roots cannot."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile
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
        # This fixture deliberately has only a platform marker, not an APK
        # database/root filesystem. Dependency installation is a separate
        # stage; never run a real ARM64 Docker install in this source-copy test.
        self.lpac_install = mock.Mock()
        run_path = package.runpy.run_path

        def load(path, *args, **kwargs):
            result = run_path(path, *args, **kwargs)
            if Path(path) == TOP/'openwrt/stage-lpac.py':
                result['install'] = self.lpac_install
            return result

        patcher = mock.patch.object(package.runpy, 'run_path', side_effect=load)
        patcher.start()
        self.addCleanup(patcher.stop)

    def save(self):
        (self.stage/'state.json').write_text(json.dumps(self.state))

    def test_epoch_dated_native_file_can_be_archived_without_changing_payload(self):
        source = self.work/'native.apk'
        source.write_bytes(b'verified native artifact')
        source.chmod(0o755)
        os.utime(source, (0, 0))
        staged = self.stage/'OpenWrt-Tools.apk'
        package.shutil.copy2(source, staged)
        package.normalize_zip_timestamp(staged)
        output = self.work/'package.zip'
        with zipfile.ZipFile(output, 'w') as archive:
            archive.write(staged, staged.name)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.read(staged.name), source.read_bytes())
            self.assertEqual(archive.getinfo(staged.name).date_time, (1980, 1, 1, 0, 0, 0))
        self.assertEqual(source.stat().st_mtime, 0)
        self.assertEqual(staged.stat().st_mode, source.stat().st_mode)

    def test_valid_native_timestamp_is_preserved(self):
        staged = self.stage/'valid.exe'
        staged.write_bytes(b'fixture')
        stamp = 1700000000
        os.utime(staged, (stamp, stamp))
        package.normalize_zip_timestamp(staged)
        self.assertEqual(staged.stat().st_mtime, stamp)

    def test_missing_previous_archive_does_not_block_current_source_copy(self):
        self.assertFalse(Path(self.state['release']).exists())
        for refresh in (False, True):
            with self.subTest(refresh=refresh), self.assertRaises(SourceCopyReached):
                package.sources(refresh=refresh)
        self.assertEqual(self.lpac_install.call_count, 2)
        self.lpac_install.assert_called_with(self.root, package.LAYOUT['lpac_apks'], package.ROOT_IMAGE)
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

    def test_root_archive_keeps_mount_points_without_runtime_files(self):
        for name in ['tmp/failed-test/config', 'run/modem/state', 'tmp2/keep', 'etc/mu300/model']:
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('fixture')
        output=self.work/'root.tar.gz'
        with package.tarfile.open(output,'w:gz') as archive:
            for path in self.root.iterdir():
                archive.add(path,arcname=path.name,filter=package.root_archive_member)
        with package.tarfile.open(output) as archive:
            names=set(archive.getnames())
            self.assertIn('tmp',names);self.assertIn('run',names)
            self.assertIn('tmp2/keep',names);self.assertIn('etc/mu300/model',names)
            self.assertFalse(any(n.startswith(('tmp/','run/')) for n in names))

    def test_boot_validation_uses_the_selected_layout(self):
        config = json.loads((TOP/'tools/build-layout.json').read_text())
        config['kernel_objects'] = '{workspace}/selected-objects'
        config['boot_templates'] = '{workspace}/selected-templates'
        selected = self.work/'selected.json'
        selected.write_text(json.dumps(config))
        original = package.runpy.run_path

        def inspect_inputs(paths):
            self.assertEqual(paths['kernel_objects'], self.work/'selected-objects')
            self.assertEqual(paths['boot_templates'], self.work/'selected-templates')
            raise SourceCopyReached

        def load(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if Path(path) == TOP/'tools/u30pro-build.py':
                result['check_sources'] = mock.Mock()
                result['check_inputs'] = inspect_inputs
            return result

        with mock.patch.dict(os.environ, {'U30PRO_BUILD_CONFIG': str(selected)}), \
                mock.patch.object(package.runpy, 'run_path', side_effect=load), \
                self.assertRaises(SourceCopyReached):
            package.canonical_boot()


if __name__ == '__main__':
    unittest.main()
