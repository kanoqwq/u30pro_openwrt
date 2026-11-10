"""Versioned interface receipt for external modules, independent of build time.

Shared algorithm with the Pro firmware's tools/kernel-abi.py. Hash the actual
configured public headers, generated layout headers, config and export table;
implementation-only edits and build timestamps do not change this identity.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess


def identity(source, objects):
    source, objects = Path(source), Path(objects)
    paths = {'config': objects / '.config', 'exports': objects / 'Module.symvers'}
    for prefix, base in [('include', source / 'include'),
                         ('arch/arm64/include', source / 'arch/arm64/include'),
                         ('generated', objects / 'include/generated'),
                         ('arch-generated', objects / 'arch/arm64/include/generated')]:
        if not base.is_dir():
            raise ValueError('Configured kernel headers missing: ' + prefix)
        for path in sorted(base.rglob('*.h')):
            if path.name in ('compile.h', 'utsversion.h'):
                continue  # build identity/time, never a public type or layout
            paths[prefix + '/' + path.relative_to(base).as_posix()] = path
    inputs = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in sorted(paths.items())}
    encoded = json.dumps({'format': 1, 'inputs': inputs}, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def receipt(source, objects):
    objects = Path(objects)
    release = re.fullmatch(r'#define UTS_RELEASE "([^"]+)"\s*', (objects / 'include/generated/utsrelease.h').read_text())
    notes = subprocess.check_output(['readelf', '-n', str(objects / 'vmlinux')], text=True)
    build_id = re.search(r'Build ID:\s*([a-f0-9]+)', notes)
    if not release or not build_id:
        raise ValueError('Missing configured kernel identity')
    return dict(format=1, kernel_release=release[1], kernel_build_id=build_id[1],
                abi_sha256=identity(source, objects))
