#!/usr/bin/env python3
"""Prepare a minimal native-input archive for review; never upload or publish."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile

SOURCE_ARCHIVE_SHA256 = 'c8ebf96318436c7581d65676de0241c9cb401719484cdd118ccc079945dfb9ae'
SOURCE_MANIFEST_SHA256 = 'f2d97092e63f7be9bebb855e48dc2ae8f689d6a0a0fe80d91d7042a66670c9d9'
BOOT = 'build/kernel-port-20261017/p19-stock-mm-trial/'
MODEM = 'build/kernel-port-20261017/p127-modem-userspace/'
WIFI = 'build/verified/erofs/odm/firmware/aic8800/'
MEMBERS = tuple(BOOT+n+'.img' for n in ('boot', 'vendor_boot', 'init_boot')) + tuple(
    MODEM+n for n in ('modem_cp_info.xml', 'modem_sp_info.xml', 'modem_ch_info.xml')) + tuple(
    WIFI+n for n in ('aic_powerlimit_8800d80x2.txt', 'aic_userconfig_8800d80x2.txt',
                    'fmacfw_8800d80x2.bin', 'fw_adid_8800d80x2_u05.bin',
                    'fw_patch_8800d80x2_u05.bin', 'fw_patch_table_8800d80x2_u05.bin',
                    'lmacfw_rf_8800d80x2.bin'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else digest_stream(stream)


def digest_stream(stream):
    result = hashlib.sha256()
    for block in iter(lambda: stream.read(1 << 20), b''):
        result.update(block)
    return result.hexdigest()


def export(archive, manifest, destination):
    if sha(archive) != SOURCE_ARCHIVE_SHA256 or sha(manifest) != SOURCE_MANIFEST_SHA256:
        raise ValueError('Original native-input archive/manifest checksum mismatch')
    known = {}
    for line in Path(manifest).read_text(encoding='utf-8').splitlines():
        checksum, name = line.split(None, 1)
        name = name.lstrip('*').removeprefix('./')
        if name in known:
            raise ValueError('Duplicate original manifest entry')
        known[name] = checksum
    if not set(MEMBERS).issubset(known):
        raise ValueError('Missing required native-input manifest entries')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    output = destination/'u30pro-native-inputs-20261107.tar.xz'
    found = {}
    # Explicit allowlist: never copy observations, captures, NV or full backups.
    with tarfile.open(archive) as source, tarfile.open(output, 'w:xz', format=tarfile.USTAR_FORMAT) as target:
        for member in source:
            name = member.name.removeprefix('./')
            if name not in MEMBERS:
                continue
            if name in found or not member.isfile() or not 0 < member.size <= 128 << 20:
                raise ValueError('Invalid required native-input member: '+name)
            data = source.extractfile(member).read()
            checksum = hashlib.sha256(data).hexdigest()
            if checksum != known[name]:
                raise ValueError('Native-input member checksum mismatch: '+name)
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            entry.mode = 0o644
            target.addfile(entry, io.BytesIO(data))
            found[name] = {'sha256': checksum, 'bytes': len(data)}
    if set(found) != set(MEMBERS):
        raise ValueError('Missing required native-input files; incomplete output retained for diagnosis')
    selected = destination/'MANIFEST.sha256'
    selected.write_text(''.join(found[n]['sha256']+'  '+n+'\n' for n in sorted(found)), encoding='utf-8', newline='\n')
    outputs = {p.name: {'sha256': sha(p), 'bytes': p.stat().st_size} for p in (output, selected)}
    report = {'format': 1, 'publication': 'not-published',
              'source_archive_sha256': SOURCE_ARCHIVE_SHA256,
              'source_manifest_sha256': SOURCE_MANIFEST_SHA256,
              'files': found, 'assets': outputs}
    (destination/'review.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    (destination/'SHA256SUMS').write_text(''.join(v['sha256']+'  '+n+'\n' for n, v in outputs.items()), encoding='utf-8')
    print(json.dumps({'output': str(destination), 'members': len(found), 'assets': outputs}, indent=2))
    return report


def main():
    if os.environ.get('U30PRO_BUILD_LOCKED') != '1':
        raise ValueError('Use tools/build-release.py run')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    export(args.archive, args.manifest, args.output)


if __name__ == '__main__':
    main()
