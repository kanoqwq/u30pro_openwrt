"""Minimal input export: exact files, checksums and no unrelated private data."""
import hashlib
import io
import json
from pathlib import Path
import runpy
import tarfile
import tempfile
import unittest
from unittest.mock import patch

TOP = Path(__file__).resolve().parents[1]
api = runpy.run_path(str(TOP/'tools/export-native-build-inputs.py'))
export = api['export']
bootstrap = runpy.run_path(str(TOP/'tools/u30pro-bootstrap.py'))


class NativeExport(unittest.TestCase):
    def test_shipped_archive_has_exactly_the_approved_members_and_original_bytes(self):
        native = bootstrap['LOCK']['assets']['native']
        manifest = bootstrap['LOCK']['assets']['native_manifest']
        archive = bootstrap['repository_input'](native)
        original = json.loads((archive.parent/'ORIGIN.json').read_text())['files']
        checksums = dict((line.split(None, 1)[1], line.split(None, 1)[0]) for line in
                         bootstrap['repository_input'](manifest).read_text().splitlines())
        self.assertEqual(set(checksums), set(api['MEMBERS']))
        found = set()
        with tarfile.open(archive) as data:
            for member in data:
                self.assertTrue(member.isfile())
                self.assertIn(member.name, checksums)
                self.assertNotIn(member.name, found)
                self.assertEqual(hashlib.sha256(data.extractfile(member).read()).hexdigest(), checksums[member.name])
                self.assertEqual(original[member.name]['sha256'], checksums[member.name])
                self.assertEqual(original[member.name]['bytes'], member.size)
                found.add(member.name)
        self.assertEqual(found, set(api['MEMBERS']))

    def fixture(self, root, *, duplicate=False, symlink=False):
        source, manifest = root/'source.tar', root/'source.sha256'
        files = {name: ('fixture '+name).encode() for name in api['MEMBERS']}
        with tarfile.open(source, 'w') as archive:
            for name, data in files.items():
                entry = tarfile.TarInfo(name); entry.size = len(data)
                if symlink and name == api['MEMBERS'][0]:
                    entry.type = tarfile.SYMTYPE; entry.linkname = '/private'; entry.size = 0
                archive.addfile(entry, io.BytesIO(data))
            entry = tarfile.TarInfo('private/imei-and-nv-backup'); entry.size = 6
            archive.addfile(entry, io.BytesIO(b'secret'))
            if duplicate:
                name = api['MEMBERS'][0]; entry = tarfile.TarInfo(name); entry.size = len(files[name])
                archive.addfile(entry, io.BytesIO(files[name]))
        manifest.write_text(''.join(hashlib.sha256(data).hexdigest()+'  '+name+'\n' for name, data in files.items()), encoding='utf-8')
        return source, manifest, files

    def run_export(self, source, manifest, destination):
        with patch.dict(export.__globals__, SOURCE_ARCHIVE_SHA256=api['sha'](source), SOURCE_MANIFEST_SHA256=api['sha'](manifest)):
            return export(source, manifest, destination)

    def test_exact_selection_roundtrips_through_production_consumer(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source, manifest, files = self.fixture(root)
            report = self.run_export(source, manifest, root/'output')
            archive = root/'output/u30pro-native-inputs-20261107.tar.xz'
            with tarfile.open(archive) as result:
                self.assertEqual(set(result.getnames()), set(files))
                for entry in result:
                    self.assertEqual(result.extractfile(entry).read(), files[entry.name])
                    self.assertEqual((entry.uid, entry.gid, entry.mtime), (0, 0, 0))
            selected = root/'output/MANIFEST.sha256'
            consumer = bootstrap['public_native']
            locked = json.loads(json.dumps(bootstrap['LOCK']))
            locked['assets']['native']['sha256'] = report['assets'][archive.name]['sha256']
            locked['assets']['native_manifest']['sha256'] = report['assets'][selected.name]['sha256']
            with patch.dict(consumer.__globals__, LOCK=locked):
                consumer(archive, selected, {'boot_templates': root/'templates', 'board_bundle': root/'board'})
            self.assertEqual((root/'templates/boot.img').read_bytes(), files[api['MEMBERS'][0]])
            self.assertEqual(len(json.loads((root/'board/board-inputs.json').read_text())['files']), 11)
            self.assertEqual(report['publication'], 'not-published')

    def test_export_is_reproducible_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source, manifest, _ = self.fixture(root)
            first = self.run_export(source, manifest, root/'one')
            second = self.run_export(source, manifest, root/'two')
            self.assertEqual(first['assets'], second['assets'])
            with self.assertRaises(FileExistsError): self.run_export(source, manifest, root/'one')

    def test_changed_source_is_rejected_before_creating_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source, manifest, _ = self.fixture(root)
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'): export(source, manifest, root/'output')
            self.assertFalse((root/'output').exists())

    def test_duplicate_required_file_and_symlink_are_rejected(self):
        for kwargs in ({'duplicate': True}, {'symlink': True}):
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); source, manifest, _ = self.fixture(root, **kwargs)
                with self.assertRaisesRegex(ValueError, 'Invalid required'): self.run_export(source, manifest, root/'output')


if __name__ == '__main__': unittest.main()
