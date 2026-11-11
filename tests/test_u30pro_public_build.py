"""Real downloader/extractor fixtures; no external network, Docker or device."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
import runpy
import subprocess
from unittest import mock

TOP = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('public_bootstrap', TOP/'tools/u30pro-bootstrap.py')
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class PublicInputs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def record(self, content):
        return {'url': 'https://downloads.example.test/pinned.tar',
                'sha256': hashlib.sha256(content).hexdigest()}

    def test_explicit_native_inputs_do_not_require_an_unused_default_cache(self):
        build=runpy.run_path(str(TOP/'tools/u30pro-build.py'))
        fields={'windows':'OPENWRT_GUI_ARTIFACT','macos-arm64':'OPENWRT_GUI_MACOS_ARTIFACT',
                'android':'OPENWRT_GUI_ANDROID_ARTIFACT'}
        roots={name:self.root/name for name in fields}
        with mock.patch.dict(os.environ,{variable:str(roots[name]) for name,variable in fields.items()}):
            self.assertEqual(build['installer_paths']({'installer_artifacts':self.root/'unused'}),roots)
            for path in roots.values():path.mkdir()
            lpac=self.root/'lpac';lpac.mkdir()
            inspect=mock.Mock()
            original=runpy.run_path

            def load(path,*args,**kwargs):
                if Path(path)==TOP/'openwrt/lpac-state.py':
                    return {'inspect':inspect}
                return original(path,*args,**kwargs)

            # The unused default must not reject otherwise selected inputs.
            with mock.patch.object(runpy,'run_path',side_effect=load), \
                    self.assertRaisesRegex(FileNotFoundError,'Makefile'):
                build['check_inputs']({'installer_artifacts':self.root/'unused',
                                      'kernel_source':self.root,'lpac_apks':lpac})
            inspect.assert_called_once_with(lpac)

    def test_missing_explicit_native_input_cannot_use_an_available_default(self):
        build=runpy.run_path(str(TOP/'tools/u30pro-build.py'))
        base=self.root/'defaults'
        for name in ('windows','macos-arm64','android'):(base/name).mkdir(parents=True)
        with mock.patch.dict(os.environ,{'OPENWRT_GUI_ARTIFACT':str(self.root/'explicit-missing')}):
            with self.assertRaisesRegex(ValueError,'explicit-missing'):
                build['check_inputs']({'installer_artifacts':base})

    def archive(self, members):
        path = self.root/'input.tar'
        with tarfile.open(path, 'w') as tar:
            for name, content, kind in members:
                info = tarfile.TarInfo(name)
                if kind == 'file':
                    info.size = len(content)
                    info.mode = 0o755
                    tar.addfile(info, io.BytesIO(content))
                else:
                    info.type = tarfile.SYMTYPE
                    info.linkname = content
                    tar.addfile(info)
        return path

    def test_download_verifies_and_reuses_without_network(self):
        content = b'pinned input\n'
        target = self.root/'cache/input'
        record = self.record(content)
        with mock.patch.object(bootstrap.urllib.request, 'urlopen', return_value=io.BytesIO(content)) as get:
            bootstrap.fetch(record, target)
            self.assertEqual(get.call_count, 1)
            bootstrap.fetch(record, target)
            self.assertEqual(get.call_count, 1)
        self.assertEqual(target.read_bytes(), content)

    def test_bad_download_never_becomes_valid_cache(self):
        target = self.root/'input'
        with mock.patch.object(bootstrap.urllib.request, 'urlopen', return_value=io.BytesIO(b'wrong')):
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                bootstrap.fetch(self.record(b'right'), target)
        self.assertFalse(target.exists())
        self.assertTrue(target.with_name('input.partial').exists())

    def test_transient_failure_retries_only_the_same_pinned_url(self):
        content = b'pinned input'
        failures = [bootstrap.urllib.error.URLError('temporary DNS failure'), io.BytesIO(content)]
        with mock.patch.object(bootstrap.urllib.request,'urlopen',side_effect=failures) as get:
            with mock.patch.object(bootstrap.time,'sleep'):
                bootstrap.fetch(self.record(content),self.root/'input')
        self.assertEqual(get.call_count,2)
        self.assertEqual(get.call_args_list[0].args[0].full_url,get.call_args_list[1].args[0].full_url)

    def test_missing_public_asset_is_not_retried_or_substituted(self):
        error = bootstrap.urllib.error.HTTPError('https://example.test/missing',404,'missing',None,None)
        with mock.patch.object(bootstrap.urllib.request,'urlopen',side_effect=error) as get:
            with self.assertRaisesRegex(ValueError,'download failed'):
                bootstrap.fetch(self.record(b'content'),self.root/'input')
        self.assertEqual(get.call_count,1)
        self.assertFalse((self.root/'input').exists())

    def test_modified_cache_is_not_overwritten_or_redownloaded(self):
        target = self.root/'input'
        target.write_bytes(b'locally modified')
        with mock.patch.object(bootstrap.urllib.request, 'urlopen') as get:
            with self.assertRaisesRegex(ValueError, 'Cached input checksum'):
                bootstrap.fetch(self.record(b'right'), target)
            get.assert_not_called()
        self.assertEqual(target.read_bytes(), b'locally modified')

    def test_insecure_download_is_rejected(self):
        record = self.record(b'x')
        record['url'] = 'http://example.test/input'
        with self.assertRaisesRegex(ValueError, 'HTTPS'):
            bootstrap.fetch(record, self.root/'input')

    def test_source_extraction_strips_one_root_and_keeps_mode(self):
        archive = self.archive([('version/file', b'hello', 'file')])
        destination = self.root/'tree'
        bootstrap.extract(archive, destination, strip_root=True)
        self.assertEqual((destination/'file').read_bytes(), b'hello')
        if os.name == 'posix':
            self.assertTrue((destination/'file').stat().st_mode & 0o100)

    def test_path_traversal_is_rejected(self):
        archive = self.archive([('../outside', b'bad', 'file')])
        with self.assertRaisesRegex(ValueError, 'Unsafe archive path'):
            bootstrap.extract(archive, self.root/'tree')
        self.assertFalse((self.root/'outside').exists())

    def test_absolute_link_is_rejected(self):
        archive = self.archive([('link', '/etc/passwd', 'link')])
        with self.assertRaisesRegex(ValueError, 'symlink escaped'):
            bootstrap.extract(archive, self.root/'tree')

    def test_parent_link_is_rejected(self):
        archive = self.archive([('link', '../outside', 'link')])
        with self.assertRaisesRegex(ValueError, 'symlink escaped'):
            bootstrap.extract(archive, self.root/'tree')

    def test_duplicate_file_is_rejected(self):
        archive = self.archive([('file', b'one', 'file'), ('file', b'two', 'file')])
        with self.assertRaisesRegex(ValueError, 'Duplicate archive file'):
            bootstrap.extract(archive, self.root/'tree')

    def test_source_tree_identity_prevents_silent_cache_substitution(self):
        archive = self.archive([('version/file', b'hello', 'file')])
        target = self.root/'source'
        identity = self.record(archive.read_bytes())
        bootstrap.materialize(archive, target, identity)
        bootstrap.materialize(archive, target, identity)
        with self.assertRaisesRegex(ValueError, 'Unowned/stale'):
            bootstrap.materialize(archive, target, self.record(b'other'))

    def test_default_paths_do_not_require_the_maintainers_machine(self):
        config = json.loads((TOP/'tools/build-layout.json').read_text())
        text = json.dumps(config).lower()
        for value in ('/mnt/d/', '/home/kano', 'd:/git', 'e5-linux', 'e5-openwrt-src', 'stock_capture', 'partition_reference'):
            self.assertNotIn(value, text)
        self.assertEqual(config['compiler']['kind'], 'toolchain')
        self.assertEqual(config['installer_artifacts_kind'], 'published')

    def test_installer_cache_path_is_derived_from_the_single_version_pin(self):
        settings = runpy.run_path(str(TOP/'tools/build-settings.py'))['settings']
        _, _, layout = settings(workspace=TOP/'out/test-installer-lock-workspace')
        pin = bootstrap.LOCK['installer_commit']
        self.assertEqual(Path(layout['installer_artifacts']).name, pin[:7])
        actual = subprocess.check_output(['git', '-C', str(TOP/'installer'), 'rev-parse', 'HEAD'], text=True).strip()
        self.assertEqual(pin, actual)
        for platform, asset in (('windows-x64', 'installer_windows'), ('macos-arm64', 'installer_macos'), ('android-aarch64', 'installer_android')):
            url = bootstrap.LOCK['assets'][asset]['url']
            self.assertIn('/build-tools-'+pin[:7]+'/', url)
            self.assertTrue(url.endswith('/installer-'+platform+'-'+pin[:7]+'.tar.gz'))

    def test_public_lock_has_only_repository_files_or_anonymous_https_and_sha256(self):
        for name, entry in bootstrap.LOCK['assets'].items():
            with self.subTest(asset=name):
                self.assertRegex(entry['sha256'], r'^[0-9a-f]{64}$')
                self.assertEqual(int('path' in entry)+int('url' in entry), 1)
                if 'path' in entry:
                    self.assertTrue(bootstrap.repository_input(entry).is_file())
                else:
                    self.assertTrue(entry['url'].startswith('https://'))
                    self.assertNotIn('@', entry['url'])

    def test_native_inputs_are_in_the_checkout_not_a_private_download(self):
        for name in ('native', 'native_manifest'):
            record = bootstrap.LOCK['assets'][name]
            with mock.patch.object(bootstrap.urllib.request, 'urlopen', side_effect=AssertionError('network access')):
                source = bootstrap.repository_input(record)
            self.assertTrue(source.is_relative_to(TOP))
        config = json.loads((TOP/'tools/build-layout.json').read_text())
        for key, name in (('input_archive', 'native'), ('input_manifest', 'native_manifest')):
            self.assertEqual(config[key], '{repo}/'+bootstrap.LOCK['assets'][name]['path'])

    def test_repository_input_rejects_escape_corruption_and_stale_override(self):
        with mock.patch.object(bootstrap, 'TOP', self.root):
            record = {'path': 'input', 'sha256': hashlib.sha256(b'right').hexdigest()}
            (self.root/'input').write_bytes(b'right')
            self.assertEqual(bootstrap.repository_input(record), self.root/'input')
            with self.assertRaisesRegex(ValueError, 'update explicit'):
                bootstrap.repository_input(record, self.root/'old-private-cache')
            (self.root/'input').write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                bootstrap.repository_input(record)
            for name in ('../outside', '/outside', r'..\outside'):
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Invalid repository'):
                    bootstrap.repository_input(dict(record, path=name))


@unittest.skipUnless(os.name == 'posix', 'target symlinks use Linux semantics')
class TargetRootLinks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)/'target'
        (self.root/'usr/lib').mkdir(parents=True)
        self.resolve = runpy.run_path(str(TOP/'tools/target-root.py'))['target_file']

    def test_absolute_library_link_stays_in_target_root(self):
        (self.root/'lib').mkdir()
        (self.root/'usr/lib/target.so').write_bytes(b'ARM64 target')
        (self.root/'lib/library.so').symlink_to('/usr/lib/target.so')
        self.assertEqual(self.resolve(self.root,'lib/library.so').read_bytes(),b'ARM64 target')

    def test_absolute_parent_directory_link_stays_in_target_root(self):
        (self.root/'lib').symlink_to('/usr/lib',target_is_directory=True)
        (self.root/'usr/lib/target.so').write_bytes(b'ARM64 target')
        (self.root/'usr/lib/library.so').symlink_to('target.so')
        self.assertEqual(self.resolve(self.root,'lib/library.so').read_bytes(),b'ARM64 target')

    def test_missing_target_cannot_use_a_host_file(self):
        (self.root/'lib').mkdir()
        (self.root/'lib/library.so').symlink_to('/etc/passwd')
        with self.assertRaises(FileNotFoundError):
            self.resolve(self.root,'lib/library.so')

    def test_link_loop_is_rejected(self):
        (self.root/'a').symlink_to('b')
        (self.root/'b').symlink_to('a')
        with self.assertRaisesRegex(ValueError,'loop'):
            self.resolve(self.root,'a')

    def test_parent_escape_is_rejected(self):
        (self.root/'a').symlink_to('../outside')
        with self.assertRaisesRegex(ValueError,'escaped'):
            self.resolve(self.root,'a')


if __name__ == '__main__':
    unittest.main()
