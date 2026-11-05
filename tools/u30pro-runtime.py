#!/usr/bin/env python3
"""Compile U30 Pro helpers/panel with the selected source-pinned musl toolchain."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import runpy

TOP = Path(__file__).resolve().parents[1]
NATIVE = TOP / 'devices/u30pro/native'
_, WORKSPACE, LAYOUT = runpy.run_path(str(TOP/'tools/build-settings.py'))['settings']()
OUT = WORKSPACE / 'artifacts/u30pro-runtime'
COMPILER = runpy.run_path(str(TOP/'tools/u30pro-compiler.py'))
HEADERS = Path(LAYOUT['headers'])
ROOT = WORKSPACE/'package-work/u30pro-release/root'
LINK_LIBS = WORKSPACE/'artifacts/u30pro-dev/lib'
CP_FILES = ('main', 'boot', 'layout', 'util', 'secure', 'hw_linux', 'nvglue', 'nv', 'mon', 'logchan')
SOURCES = {
    'u30-modemd': ['modem-native-re/src/' + p + '.c' for p in CP_FILES],
    'u30pro-nvsyncd': ['tools/u30pro_nvsyncd.c'],
    'u30pro-refnotifyd': ['tools/u30pro_refnotifyd.c'],
    'u30pro-nodes': ['kernel/ums9632/native/stage0_linux.c'],
    'u30pro-watchdog-keeper': ['kernel/ums9632/native/u30pro_watchdog_keeper.c'],
    'u30pro-panel': ['tools/u30pro_ui.c'],
    'u30pro-nfc': ['tools/u30pro_nfc.c'],
    'sml-voltage-check': [],
    'mu300-keys': [],
}
SHARED_SOURCES = {
    'sml-voltage-check': TOP/'tools/sml-voltage/sml-voltage-check.c',
    'mu300-keys': TOP/'tools/keys/mu300-keys.c',
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_elf(path, dynamic=False):
    data = path.read_bytes()
    if data[:6] != b'\x7fELF\x02\x01' or int.from_bytes(data[18:20], 'little') != 183:
        raise ValueError('Not a little-endian AArch64 executable: ' + str(path))
    headers = subprocess.check_output(['readelf', '-l', '-d', str(path)], text=True)
    if dynamic:
        if '/lib/ld-musl-aarch64.so.1' not in headers:
            raise ValueError('Panel must use the target musl loader')
    elif 'INTERP' in headers or '(NEEDED)' in headers:
        raise ValueError('Hardware helper must be static: ' + str(path))


def build():
    if os.environ.get('U30PRO_BUILD_LOCKED') != '1':
        raise ValueError('Use tools/build-release.py run')
    OUT.mkdir(parents=True, exist_ok=True)
    metadata = OUT / 'runtime.json'
    previous = json.loads(metadata.read_text()) if metadata.exists() else {}
    result = {'format': 1, 'files': {}}
    for name, sources in SOURCES.items():
        dynamic = name == 'u30pro-panel'
        dependencies = [NATIVE / p for p in sources]
        if name in SHARED_SOURCES: dependencies = [SHARED_SOURCES[name]]
        dependencies += sorted((NATIVE / ('tools/ui' if dynamic else 'modem-native-re/src')).glob('*.h'))
        inputs = {str(p.relative_to(TOP)): digest(p) for p in dependencies}
        libraries = []
        if dynamic:
            for soname in ('libubus.so.20251202', 'libubox.so.20260213', 'libuci.so.20250120'):
                source = LINK_LIBS/soname
                data = source.read_bytes()
                if data[:6] != b'\x7fELF\x02\x01' or int.from_bytes(data[18:20], 'little') != 183:
                    raise ValueError('Expected ARM64 target library: '+soname)
                libraries.append(source)
        identity = {'sources': inputs, 'compiler': LAYOUT['compiler'], 'dynamic': dynamic,
                    'headers': {str(p.relative_to(HEADERS)): digest(p) for p in HEADERS.rglob('*.h')} if dynamic else {},
                    'libraries': {p.name: digest(p) for p in libraries},
                    'builder': digest(Path(__file__))}
        old = previous.get('files', {}).get(name, {})
        target = OUT / name
        if old.get('inputs') == identity and target.is_file() and digest(target) == old.get('sha256'):
            verify_elf(target, dynamic)
            result['files'][name] = old
            continue
        pending = OUT / (name + '.building')
        if pending.exists():
            raise ValueError('Failed compiler output retained: ' + str(pending))
        flags = ['-std=gnu11', '-Os', '-Wall', '-Wextra', '-Wno-error=misleading-indentation', '-s',
                 '-ffile-prefix-map='+str(TOP)+'=/source',
                 '-ffile-prefix-map='+str(WORKSPACE)+'=/build']
        flags += ['-I'+str(HEADERS), '-L'+str(LINK_LIBS),
                  '-Wl,-rpath-link,'+str(LINK_LIBS)] if dynamic else ['-static']
        if name == 'u30-modemd':
            flags += ['-pthread', '-Wno-unused-parameter']
        command = [COMPILER['prefix'](LAYOUT)+'gcc', *flags,
                   *([SHARED_SOURCES[name]] if name in SHARED_SOURCES else [NATIVE/p for p in sources]),
                   '-o', pending, *(['-l:'+p.name for p in libraries]+['-lm'] if dynamic else [])]
        COMPILER['execute'](command, LAYOUT, WORKSPACE)
        verify_elf(pending, dynamic)
        pending.replace(target)
        result['files'][name] = {'inputs': identity, 'sha256': digest(target), 'bytes': target.stat().st_size}
        metadata.write_text(json.dumps(result, indent=2) + '\n')
    metadata.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'runtime': str(OUT), 'binaries': len(result['files']), 'hardware_accessed': False}))


if __name__ == '__main__':
    build()
