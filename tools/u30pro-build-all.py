#!/usr/bin/env python3
"""Canonical clone-to-ZIP pipeline, always under build-release.py's lock."""
import argparse
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

TOP = Path(__file__).resolve().parents[1]


def load(name):
    return runpy.run_path(str(TOP/'tools'/name))


def call(*args):
    print('Build step: '+' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=TOP, check=True)


def root_image(work, layout):
    image = layout['rootfs_image']
    dockerfile = TOP/'tools/build/u30pro-rootfs.Dockerfile'
    bootstrap = load('u30pro-bootstrap.py')
    expected = {'org.u30pro.base-sha256': bootstrap['LOCK']['assets']['rootfs']['sha256'],
                'org.u30pro.builder-sha256': bootstrap['sha'](dockerfile)}
    result = subprocess.run(['docker', 'image', 'inspect', image], capture_output=True, text=True)
    if result.returncode == 0:
        info = json.loads(result.stdout)[0]
        labels = info.get('Config', {}).get('Labels') or {}
        if info['Architecture'] != 'arm64' or any(labels.get(k) != v for k,v in expected.items()):
            raise ValueError('Build image tag has an unreviewed recipe; inspect '+image)
    else:
        call('docker', 'build', '--platform', 'linux/arm64', '-t', image,
             *[arg for k,v in expected.items() for arg in ('--label', k+'='+v)],
             '-f', dockerfile, work/'cache/u30pro-root')
    # This also reports missing host ARM64 binfmt support before root mutation.
    call('docker', 'run', '--rm', '--platform', 'linux/arm64', '--entrypoint', '/usr/bin/ucode',
         image, '-e', "import * as fs from 'fs'; print('ARM64 target ucode ready\\n');")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--jobs', type=int, default=2)
    p.add_argument('--prepare-only', action='store_true')
    args = p.parse_args()
    if not 1 <= args.jobs <= 256:
        p.error('--jobs must be between 1 and 256')
    if os.environ.get('U30PRO_BUILD_LOCKED') != '1':
        raise ValueError('Use tools/build-release.py build')
    _, work, layout = load('build-settings.py')['settings']()
    if os.geteuid() != 0:
        raise ValueError('Rootfs assembly needs root ownership and permissions; run sudo python3 '
                         'tools/build-release.py build --workspace '+str(work)+' --jobs '+str(args.jobs))
    required = ('docker', 'git', 'make', 'gcc', 'cmake', 'clang', 'ld.lld',
                'llvm-ar', 'llvm-nm', 'llvm-objcopy', 'llvm-objdump', 'llvm-readelf',
                'llvm-size', 'llvm-strip', 'zstd', 'xz', 'lz4', 'patch', 'cpio',
                'openssl', 'depmod', 'readelf')
    missing = [name for name in required if shutil.which(name) is None]
    if missing:
        raise ValueError('Install the documented Linux build dependencies: '+', '.join(missing))
    pin = load('u30pro-bootstrap.py')['LOCK']['installer_commit']
    actual = subprocess.check_output(['git', '-c', 'safe.directory='+str(TOP/'installer'),
        '-C', str(TOP/'installer'), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != pin:
        raise ValueError('Initialize the pinned installer submodule before building')
    load('u30pro-bootstrap.py')['provision'](layout, work)
    root_image(work, layout)
    package = load('u30pro-package.py')
    if not package['STAGE'].exists():
        package['bootstrap']()
    package['owned']()
    state = json.loads((package['STAGE']/'state.json').read_text())
    if state.get('base') != package['BASE_SHA']:
        raise ValueError('Prepared root belongs to a different OpenWrt base')
    if state['step'] == 'base-extracted':
        package['dependencies']()
    load('u30pro-compiler.py')['static_tools'](layout, work, args.jobs)
    load('u30pro-compiler.py')['development_libraries'](layout, work, args.jobs)
    # Validate all source-pinned installers now, before a kernel compilation.
    sys.path.insert(0, str(TOP/'installer'))
    gui = runpy.run_path(str(TOP/'installer/package_gui.py'))
    for name, platform in (('windows','windows-x64'), ('macos-arm64','macos-arm64')):
        gui['validate_artifact'](Path(layout['installer_artifacts'])/name, platform, gui['sources']())
    runpy.run_path(str(TOP/'installer/package_android.py'))['artifact'](Path(layout['installer_artifacts'])/'android')
    call(sys.executable, TOP/'tools/u30pro-build.py', 'check')
    if args.prepare_only:
        print('Public dependencies and static tools ready; no kernel/firmware package built', flush=True)
        return
    call(sys.executable, TOP/'tools/u30pro-build.py', 'kernel', '--jobs', args.jobs)
    call(sys.executable, TOP/'tools/u30pro-runtime.py')
    package['sources']()
    package['finish']()
    call('sh', TOP/'tools/test-u30pro-native.sh')
    call(sys.executable, TOP/'tools/test-u30pro-root.py')
    call(sys.executable, TOP/'tests/u30pro_boot_adapter.py')
    wrapped = package['STAGE']/'Image.wrapped'
    if wrapped.exists():
        proof = json.loads(wrapped.with_suffix('.manifest.json').read_text())
        if proof['input_sha256'] != package['digest'](package['KERNEL']/'arch/arm64/boot/Image'):
            package['clean_staging']()
    package['package']()


if __name__ == '__main__':
    main()
