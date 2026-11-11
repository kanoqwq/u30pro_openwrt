#!/usr/bin/env python3
"""Refresh native installer files in verified U30 Pro release archives only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import zipfile

TOP = Path(__file__).resolve().parents[1]


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def refresh():
    if os.environ.get('U30PRO_BUILD_LOCKED') != '1':
        raise ValueError('Run through tools/build-release.py run')
    workspace = Path(os.environ['U30PRO_WORKSPACE'])
    output_root = TOP / 'release'
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    building = output_root / ('.building-installer-refresh-' + stamp + '-' + str(os.getpid()))
    final = output_root / ('installer-refresh-' + stamp + '-' + str(os.getpid()))
    building.mkdir(parents=True, exist_ok=False)
    native = Path(os.environ.get('TMPDIR', workspace / 'tmp')) / 'native-installer-refresh'
    source_archives = {}
    expected = {'u30pro': 'u30pro-openwrt-25.12.5-*.zip',
                'f50pro': 'f50pro-openwrt-25.12.5-*.zip'}
    for product, pattern in expected.items():
        candidates = []
        for path in output_root.rglob(pattern):
            if not path.is_file() or '.building-' in path.parts:
                continue
            with zipfile.ZipFile(path) as archive:
                manifest = json.loads(archive.read('desktop/manifest.json'))
            if manifest.get('product') == product and manifest.get('kernel') == '6.12.94-u30pro-p1':
                candidates.append(path)
        if not candidates:
            raise ValueError('No prior verified release archive found for ' + product)
        source_archives[product] = max(candidates, key=lambda path: path.stat().st_mtime_ns)

    verify = runpy.run_path(str(TOP / 'tools/build-release.py'))['verify_archive']
    for path in source_archives.values():
        verify(path, require_diff=True, require_android=True)

    studio_command = [sys.executable, str(TOP / 'tools/package-diff-studio.py'),
                      '--prepare', '--package', str(native)]
    subprocess.run(studio_command, cwd=TOP, check=True)

    identify = runpy.run_path(str(TOP / 'tools/release-identity.py'))['identify']
    repack = runpy.run_path(str(TOP / 'tools/repack-with-diff.py'))['repack']
    revision = identify(TOP, 'u30pro', '6.12.94')
    assets = []
    for product, source in source_archives.items():
        target = building / (source.stem + '-installer-328c62d.zip')
        payload = repack(source, target, native, revision, refresh_native=True)
        verify(target, require_diff=True, require_android=True)
        checksum = sha(target)
        (building / (target.name + '.sha256')).write_text(
            checksum + '  ' + target.name + '\n', encoding='ascii')
        assets.append({'product': product, 'source_archive': source.name,
                       'source_sha256': sha(source), 'file': target.name,
                       'bytes': target.stat().st_size, 'sha256': checksum,
                       'firmware_payloads_unchanged': payload})

    record = {'format': 1, 'state': 'verified', 'build_type': 'native-installer-refresh',
              'source': revision, 'installer_commit': json.loads(
                  (TOP / 'tools/public-inputs.lock.json').read_text(encoding='utf-8'))['installer_commit'],
              'assets': assets}
    (building / 'BUILD-RUN.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    building.rename(final)
    print('Verified installer refresh: ' + str(final), flush=True)
    for asset in assets:
        print(asset['file'] + '  sha256=' + asset['sha256'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    refresh()
