#!/usr/bin/env python3
"""Archive reviewed shared installer artifacts for anonymous, pinned downloads."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tarfile

TOP = Path(__file__).resolve().parents[1]


def main():
    if os.environ.get('U30PRO_BUILD_LOCKED') != '1':
        raise ValueError('Use tools/build-release.py run')
    _, work, layout = runpy.run_path(str(TOP/'tools/build-settings.py'))['settings']()
    sys.path.insert(0, str(TOP/'installer'))
    gui = runpy.run_path(str(TOP/'installer/package_gui.py'))
    mobile = runpy.run_path(str(TOP/'installer/package_android.py'))
    inputs = Path(layout['installer_artifacts'])
    commit = json.loads((TOP/'tools/public-inputs.lock.json').read_text())['installer_commit']
    actual = subprocess.check_output(['git', '-c', 'safe.directory='+str(TOP/'installer'),
        '-C', str(TOP/'installer'), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != commit:
        raise ValueError('Installer submodule differs from the build-input pin; do not publish mislabeled artifacts')
    pin = commit[:7]
    selected = [('windows', 'windows-x64'), ('macos-arm64', 'macos-arm64'), ('android', 'android-aarch64')]
    explicit = {'windows': 'OPENWRT_GUI_ARTIFACT',
                'macos-arm64': 'OPENWRT_GUI_MACOS_ARTIFACT',
                'android': 'OPENWRT_GUI_ANDROID_ARTIFACT'}
    output = work/'cache/u30pro-build-tools'
    output.mkdir(parents=True, exist_ok=True)
    result = {}
    for folder, platform in selected:
        # Match firmware packaging: archive the explicitly selected, verified
        # native artifacts without copying another full tool environment.
        root = Path(os.environ.get(explicit[folder], str(inputs/folder)))
        if folder == 'android':
            apk, metadata = mobile['artifact'](root)
            files = [apk, metadata]
        else:
            metadata = gui['validate_artifact'](root, platform, gui['sources']())
            files = [metadata]+[root/n for n in json.loads(metadata.read_text())['files']]
        target = output/('installer-'+platform+'-'+pin+'.tar.gz')
        if target.exists():
            raise ValueError('Build-input archive already exists; inspect it: '+str(target))
        with target.open('xb') as f, gzip.GzipFile(filename='', fileobj=f, mode='wb', mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode='w', dereference=False) as archive:
                for path in sorted(files):
                    info = archive.gettarinfo(str(path), arcname=path.relative_to(root).as_posix())
                    info.uid = info.gid = info.mtime = 0
                    info.uname = info.gname = ''
                    if info.isfile():
                        with path.open('rb') as stream:
                            archive.addfile(info, stream)
                    else:
                        archive.addfile(info)
        h = hashlib.sha256()
        with target.open('rb') as f:
            for block in iter(lambda: f.read(1 << 20), b''):
                h.update(block)
        result[folder] = {'file': target.name, 'sha256': h.hexdigest(), 'bytes': target.stat().st_size}
    (output/'SHA256SUMS').write_text(''.join(v['sha256']+'  '+v['file']+'\n' for v in result.values()))
    (output/'inputs.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'output': str(output), 'assets': result}, indent=2))


if __name__ == '__main__':
    main()
