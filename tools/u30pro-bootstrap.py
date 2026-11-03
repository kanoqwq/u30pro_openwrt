#!/usr/bin/env python3
"""Fetch pinned public inputs. No login, device, private dump or adjacent repo."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import runpy
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import urllib.error
import time
import http.client

TOP = Path(__file__).resolve().parents[1]
LOCK = json.loads((TOP/'tools/public-inputs.lock.json').read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def fetch(record, destination):
    destination = Path(destination)
    if destination.is_symlink():
        raise ValueError('Download target is a symlink: '+str(destination))
    if destination.exists():
        if not destination.is_file() or sha(destination) != record['sha256']:
            raise ValueError('Cached input checksum mismatch; inspect '+str(destination))
        return destination
    if not record['url'].startswith('https://'):
        raise ValueError('Public build inputs require HTTPS')
    destination.parent.mkdir(parents=True, exist_ok=True)
    pending = destination.with_name(destination.name+'.partial')
    if pending.is_symlink():
        raise ValueError('Download partial is a symlink')
    print('Downloading '+record['url'], flush=True)
    request = urllib.request.Request(record['url'], headers={'User-Agent': 'u30pro-openwrt-builder/1'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as source, pending.open('wb') as target:
                shutil.copyfileobj(source, target, 1 << 20)
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.IncompleteRead) as error:
            if isinstance(error, urllib.error.HTTPError) and error.code not in (429,500,502,503,504):
                raise ValueError('Public input download failed: '+record['url']+'; '+str(error)) from error
            if attempt == 2:
                raise ValueError('Public input download failed after 3 attempts: '+record['url']+'; '+str(error)) from error
            print('Transient download failure; retrying the same pinned URL ('+str(attempt+2)+'/3)', flush=True)
            time.sleep(2*(attempt+1))
    if sha(pending) != record['sha256']:
        raise ValueError('Downloaded input checksum mismatch; retained '+str(pending))
    pending.rename(destination)
    return destination


def open_tar(path):
    """Python 3.10 also supports zstd archives through the host decoder."""
    if str(path).endswith('.zst'):
        temporary = tempfile.TemporaryFile()
        try:
            subprocess.run(['zstd', '-d', '-c', str(path)], stdout=temporary, check=True)
            temporary.seek(0)
            archive = tarfile.open(fileobj=temporary, mode='r:')
            archive._u30pro_stream = temporary
            return archive
        except BaseException:
            temporary.close()
            raise
    return tarfile.open(path)


def extract(path, destination, *, strip_root=False):
    """Extract only within an owned destination, validating links before use."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    root = destination.resolve()
    with open_tar(path) as archive:
        members = archive.getmembers()
        roots = {PurePosixPath(m.name).parts[0] for m in members if PurePosixPath(m.name).parts}
        if strip_root and len(roots) != 1:
            raise ValueError('Expected one source archive root')
        for links in (False, True):
            for member in members:
                name = PurePosixPath(member.name)
                if name.is_absolute() or '..' in name.parts or '\\' in member.name:
                    raise ValueError('Unsafe archive path: '+member.name)
                parts = name.parts[1:] if strip_root else name.parts
                if not parts:
                    continue
                target = destination.joinpath(*parts)
                if (member.issym() or member.islnk()) != links:
                    continue
                if not target.parent.resolve().is_relative_to(root):
                    raise ValueError('Archive parent escaped destination')
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.is_symlink():
                    raise ValueError('Duplicate archive symlink')
                if member.isdir():
                    target.mkdir(exist_ok=True)
                elif member.isfile():
                    if target.exists():
                        raise ValueError('Duplicate archive file')
                    with archive.extractfile(member) as source, target.open('xb') as out:
                        shutil.copyfileobj(source, out)
                    target.chmod(member.mode & 0o777)
                elif member.issym():
                    if Path(member.linkname).is_absolute() or not (target.parent/member.linkname).resolve().is_relative_to(root):
                        raise ValueError('Archive symlink escaped destination')
                    target.symlink_to(member.linkname)
                elif member.islnk():
                    link = PurePosixPath(member.linkname)
                    if link.is_absolute() or '..' in link.parts:
                        raise ValueError('Archive hardlink escaped destination')
                    linkparts = link.parts[1:] if strip_root else link.parts
                    source = destination.joinpath(*linkparts)
                    if not source.resolve().is_relative_to(root) or not source.is_file():
                        raise ValueError('Missing/unsafe archive hardlink target')
                    shutil.copyfile(source, target)
                    target.chmod(member.mode & 0o777)
                else:
                    raise ValueError('Unsupported archive member: '+member.name)
        stream = getattr(archive, '_u30pro_stream', None)
    if stream:
        stream.close()


def materialize(archive, target, identity, *, strip_root=True):
    target = Path(target)
    receipt = target/'.u30pro-input.json'
    if target.exists():
        if target.is_symlink() or not receipt.is_file() or json.loads(receipt.read_text()) != identity:
            raise ValueError('Unowned/stale input tree: '+str(target))
        return target
    pending = target.with_name(target.name+'.extracting')
    if pending.exists():
        raise ValueError('Failed extraction retained; inspect '+str(pending))
    target.parent.mkdir(parents=True, exist_ok=True)
    extract(archive, pending, strip_root=strip_root)
    (pending/'.u30pro-input.json').write_text(json.dumps(identity, sort_keys=True)+'\n')
    pending.rename(target)
    return target


def public_native(archive, manifest_path, layout):
    manifest = {}
    for line in Path(manifest_path).read_text().splitlines():
        digest, name = line.split(None, 1)
        manifest[name.lstrip('*')] = digest
    templates = Path(layout['boot_templates'])
    board = Path(layout['board_bundle'])
    prefix = 'build/kernel-port-20261017/p19-stock-mm-trial/'
    selected = {prefix+n+'.img': templates/(n+'.img') for n in ('boot', 'vendor_boot', 'init_boot')}
    cp = 'build/kernel-port-20261017/p127-modem-userspace/'
    selected.update({cp+n: board/'etc/u30pro/modem'/n for n in ('modem_cp_info.xml', 'modem_sp_info.xml', 'modem_ch_info.xml')})
    fw = 'build/verified/erofs/odm/firmware/aic8800/'
    selected.update({name: board/'odm/firmware/aic8800'/name.removeprefix(fw) for name in manifest if name.startswith(fw)})
    found = set()
    with tarfile.open(archive) as tar:
        for member in tar:
            name = member.name.removeprefix('./')
            if name not in selected:
                continue
            if name in found or not member.isfile():
                raise ValueError('Invalid public native member: '+name)
            data = tar.extractfile(member).read()
            if hashlib.sha256(data).hexdigest() != manifest[name]:
                raise ValueError('Public member checksum mismatch: '+name)
            target = selected[name]
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and (target.is_symlink() or target.read_bytes() != data):
                raise ValueError('Public input changed: '+str(target))
            if not target.exists():
                target.write_bytes(data)
            found.add(name)
    if found != set(selected):
        raise ValueError('Missing published native inputs: '+str(set(selected)-found))
    provenance = {'archive_sha256': LOCK['assets']['native']['sha256'],
                  'manifest_sha256': LOCK['assets']['native_manifest']['sha256']}
    files = {target.name: {'sha256': manifest[name], 'size': target.stat().st_size, 'source': name}
             for name, target in selected.items() if target.parent == templates}
    (templates/'templates.json').write_text(json.dumps({'profile': 'u30pro', 'origin': provenance,
        'device_bound': False, 'files': files}, indent=2)+'\n')
    map_path = board/'etc/u30pro/modem/map.tsv'
    shutil.copyfile(TOP/'devices/u30pro/modem-map.tsv', map_path)
    board_files = {str(path.relative_to(board)): {'sha256': sha(path)} for path in selected.values() if path.is_relative_to(board)}
    board_files['etc/u30pro/modem/map.tsv'] = {'sha256': sha(map_path)}
    (board/'board-inputs.json').write_text(json.dumps({'format': 1, 'profile': 'u30pro',
        'origin': provenance, 'files': board_files}, indent=2)+'\n')


def provision(layout, work):
    """Only public, fixed URLs; existing valid downloads are reused in place."""
    downloads = work/'cache/u30pro-downloads'
    def get(name, target=None):
        record = LOCK['assets'][name]
        return fetch(record, target or downloads/record['url'].rsplit('/', 1)[1])
    native = get('native', Path(layout['input_archive']))
    manifest = get('native_manifest', Path(layout['input_manifest']))
    public_native(native, manifest, layout)
    get('rootfs', work/'cache/u30pro-root/openwrt-25.12.5-armsr-armv8-rootfs.tar.gz')
    get('theme', Path(layout['theme']))
    source = Path(layout['kernel_source'])
    if layout.get('kernel_source_kind') == 'prepared':
        if not source.is_dir() or not (Path(layout['kernel_objects'])/'u30pro-build.json').is_file():
            raise ValueError('Explicit prepared kernel has no registered build receipt')
    elif layout.get('kernel_source_kind') == 'downloaded':
        materialize(get('kernel'), source, LOCK['assets']['kernel'])
    else:
        raise ValueError('Select downloaded or explicitly prepared kernel source')
    Path(layout['kernel_objects']).mkdir(parents=True, exist_ok=True)
    compiler = layout['compiler']
    if compiler['kind'] == 'toolchain':
        if platform.machine() not in ('x86_64', 'AMD64'):
            raise ValueError('The pinned public toolchain requires a Linux x86_64 build host')
        materialize(get('toolchain'), Path(compiler['directory']), LOCK['assets']['toolchain'])
    elif compiler['kind'] == 'docker-volume':
        subprocess.run(['docker', 'image', 'inspect', compiler['image']], stdout=subprocess.DEVNULL, check=True)
        subprocess.run(['docker', 'volume', 'inspect', compiler['volume']], stdout=subprocess.DEVNULL, check=True)
    else:
        raise ValueError('Unknown explicitly selected compiler')
    for name in ('json-c', 'libubox', 'ubus', 'uci'):
        materialize(get(name), work/'sources/u30pro-libs'/name, LOCK['assets'][name])
    materialize(get('busybox'), work/'sources/u30pro-busybox', LOCK['assets']['busybox'])
    if layout.get('installer_artifacts_kind') == 'published':
        for name, asset in (('windows', 'installer_windows'), ('macos-arm64', 'installer_macos'), ('android', 'installer_android')):
            root = Path(layout['installer_artifacts'])/name
            # Installers validate their complete file set, so keep bootstrap
            # ownership receipts next to each artifact directory, not inside it.
            receipt = root.with_name(root.name+'.input.json')
            identity = LOCK['assets'][asset]
            if root.exists():
                if not receipt.is_file() or json.loads(receipt.read_text()) != identity:
                    raise ValueError('Installer input is unowned or stale: '+name)
            else:
                archive = get(asset)
                root.parent.mkdir(parents=True, exist_ok=True)
                pending = root.with_name(root.name+'.extracting')
                extract(archive, pending)
                pending.rename(root)
                receipt.write_text(json.dumps(identity)+'\n')
    elif layout.get('installer_artifacts_kind') != 'registered':
        raise ValueError('Select published or explicitly registered installer artifacts')
    print('Pinned public inputs prepared; no device or adjacent firmware checkout accessed', flush=True)


def main():
    if os.environ.get('U30PRO_BUILD_LOCKED') != '1':
        raise ValueError('Use tools/build-release.py bootstrap or build')
    _, work, layout = runpy.run_path(str(TOP/'tools/build-settings.py'))['settings']()
    provision(layout, work)


if __name__ == '__main__':
    main()
