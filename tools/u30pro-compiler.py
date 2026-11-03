"""One explicit compiler descriptor; no availability-based backend fallback."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

TOP = Path(__file__).resolve().parents[1]


def prefix(layout):
    compiler = layout['compiler']
    if compiler['kind'] == 'docker-volume':
        return compiler['prefix']
    if compiler['kind'] != 'toolchain':
        raise ValueError('Unknown compiler descriptor')
    root = Path(compiler['directory'])
    matches = [p for p in root.rglob('aarch64-openwrt-linux-musl-gcc') if p.is_file()]
    if len(matches) != 1:
        raise ValueError('Expected one compiler in the pinned public toolchain')
    return str(matches[0])[:-3]


def execute(argv, layout, work, env=None):
    compiler = layout['compiler']
    extra = {'STAGING_DIR': str(Path(prefix(layout)).parent.parent.parent), **(env or {})}
    if compiler['kind'] == 'docker-volume':
        def mapped(value):
            return str(value).replace(str(TOP), '/repo').replace(str(work), '/workspace')
        command = ['docker', 'run', '--rm', '-v', compiler['volume']+':/build:ro',
                   '-v', str(TOP)+':/repo:ro', '-v', str(work)+':/workspace',
                   '--entrypoint', '/usr/bin/env', compiler['image']]
        command += [k+'='+mapped(v) for k, v in extra.items()]
        command += [mapped(v) for v in argv]
        subprocess.run(command, stdin=subprocess.DEVNULL, check=True)
    else:
        subprocess.run(list(map(str, argv)), env={**os.environ, **extra}, stdin=subprocess.DEVNULL, check=True)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def static_tools(layout, work, jobs):
    cross = prefix(layout)
    source = work/'sources/u30pro-busybox'
    objects = work/'objects/u30pro-busybox'
    objects.mkdir(parents=True, exist_ok=True)
    busybox = Path(layout['busybox'])
    receipt = busybox.with_suffix('.build.json')
    identity = {'source': json.loads((source/'.u30pro-input.json').read_text()),
                'compiler': layout['compiler'], 'builder': sha(Path(__file__))}
    old = json.loads(receipt.read_text()) if receipt.is_file() else {}
    if not (busybox.is_file() and old.get('inputs') == identity and old.get('sha256') == sha(busybox)):
        make = ['make', '-C', source, 'O='+str(objects), 'ARCH=arm64', 'CROSS_COMPILE='+cross]
        execute(make+['defconfig'], layout, work)
        config = objects/'.config'
        # Docker-volume builds use the shared host filesystem for .config too.
        text = config.read_text()
        settings = {'STATIC': 'y', 'PIE': 'n', 'TC': 'n', 'USE_BB_CRYPT': 'y',
                    'USE_BB_CRYPT_SHA': 'y', 'SHA1_HWACCEL': 'n', 'SHA256_HWACCEL': 'n'}
        import re
        for name, value in settings.items():
            text = re.sub(r'^(?:CONFIG_'+name+r'=.*|# CONFIG_'+name+r' is not set)\n', '', text, flags=re.M)
            text += 'CONFIG_'+name+'='+value+'\n'
        config.write_text(text)
        execute(make+['oldconfig'], layout, work)
        execute(make+['-j'+str(jobs)], layout, work)
        busybox.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(objects/'busybox', busybox)
        busybox.chmod(0o755)
        receipt.write_text(json.dumps({'inputs': identity, 'sha256': sha(busybox)}, indent=2)+'\n')
    target = Path(layout['at_transport'])
    target.parent.mkdir(parents=True, exist_ok=True)
    source = TOP/'tools/atd-io/mu300-atd-io.c'
    import runpy
    artifact = runpy.run_path(str(TOP/'tools/atd-io/artifact.py'))
    # A source/binary receipt selects reuse; a mismatched receipt requires a
    # normal source build, never editing the recorded source fingerprint.
    expected = target.with_name(target.name+'.build.json')
    if target.is_file() and expected.is_file():
        old = json.loads(expected.read_text())
        if old.get('source_sha256') == sha(source) and old.get('binary_sha256') == sha(target):
            artifact['check'](target)
            return
    execute([cross+'gcc', '-O2', '-Wall', '-Wextra', '-Werror', '-static',
             source, '-o', target], layout, work)
    expected.write_text(json.dumps(artifact['inspect'](target), indent=2)+'\n')


def development_libraries(layout, work, jobs):
    """Compile linkable development libraries, not stripped runtime APK files."""
    cross = prefix(layout)
    target = work/'artifacts/u30pro-dev'
    target.mkdir(parents=True, exist_ok=True)
    lock = json.loads((TOP/'tools/public-inputs.lock.json').read_text())
    receipt = target/'build.json'
    identity = {'sources': {n: lock['assets'][n] for n in ('json-c','libubox','ubus','uci')},
                'compiler': layout['compiler'], 'builder': sha(Path(__file__))}
    old = json.loads(receipt.read_text()) if receipt.is_file() else {}
    if old.get('inputs') == identity and old.get('files') and all(
            (target/n).is_file() and sha(target/n) == wanted for n,wanted in old['files'].items()):
        return
    versions = {'libubox': '20260213', 'ubus': '20251202', 'uci': '20250120'}
    env = {'PKG_CONFIG_LIBDIR': str(target/'lib/pkgconfig'), 'PKG_CONFIG_SYSROOT_DIR': '',
           'PKG_CONFIG_PATH': ''}
    for name in ('json-c', 'libubox', 'ubus', 'uci'):
        source = work/'sources/u30pro-libs'/name
        build = work/'objects/u30pro-dev'/name
        command = ['cmake', '-S', source, '-B', build, '-DCMAKE_SYSTEM_NAME=Linux',
            '-DCMAKE_SYSTEM_PROCESSOR=aarch64', '-DCMAKE_C_COMPILER='+cross+'gcc',
            '-DCMAKE_AR='+cross+'ar', '-DCMAKE_RANLIB='+cross+'ranlib',
            '-DCMAKE_INSTALL_PREFIX='+str(target), '-DCMAKE_INSTALL_LIBDIR=lib',
            '-DCMAKE_PREFIX_PATH='+str(target), '-DCMAKE_BUILD_TYPE=Release',
            '-DCMAKE_FIND_ROOT_PATH='+str(target), '-DCMAKE_FIND_ROOT_PATH_MODE_LIBRARY=ONLY',
            '-DCMAKE_FIND_ROOT_PATH_MODE_INCLUDE=ONLY', '-DCMAKE_FIND_ROOT_PATH_MODE_PROGRAM=NEVER',
            '-DBUILD_LUA=OFF', '-DBUILD_EXAMPLES=OFF', '-DBUILD_TESTING=OFF',
            '-DDISABLE_EXTRA_LIBS=TRUE']
        if name in versions:
            command.append('-DABIVERSION='+versions[name])
        execute(command, layout, work, env)
        execute(['cmake', '--build', build, '--parallel', str(jobs)], layout, work, env)
        execute(['cmake', '--install', build], layout, work, env)
    files = {str(p.relative_to(target)): sha(p) for folder in ('lib','include')
             for p in (target/folder).rglob('*') if p.is_file()}
    receipt.write_text(json.dumps({'inputs': identity, 'files': files}, indent=2)+'\n')
