#!/usr/bin/env python3
"""Apply the reviewed Wi-Fi patches to the caller's owned root staging.

The existing DFS patch stays immutable. A prepared root may add the new band
guard without bypassing its prior source/result receipt or reinstalling rootfs.
"""
import hashlib
import json
from pathlib import Path
import subprocess

PATCHES = ('wifi-scripts-no-dfs.patch', 'wifi-scripts-chanlist-band.patch')
RELATIVE = 'usr/share/ucode/wifi/hostapd.uc'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stage(root, patch_dir, receipt):
    root, patch_dir, receipt = Path(root), Path(patch_dir), Path(receipt)
    target = root / RELATIVE
    applied = json.loads(receipt.read_text()) if receipt.is_file() else {}
    # Verify every existing contribution against the composed current file
    # before modifying anything, including when another patch is newly added.
    for name in PATCHES:
        if name in applied and applied[name] != {'patch': digest(patch_dir/name), 'result': digest(target)}:
            raise ValueError('Shared root patch source/result changed: ' + name)
    for name in PATCHES:
        if name in applied:
            continue
        argv = ['patch', '--batch', '--fuzz=0', '-d', str(root), '-p1', '-i', str(patch_dir/name)]
        subprocess.run(argv + ['--dry-run'], check=True, capture_output=True, text=True)
        subprocess.run(argv, check=True, capture_output=True, text=True)
        applied[name] = {'patch': digest(patch_dir/name), 'result': digest(target)}
        # Both reviewed patches contribute to one file. Record the verified
        # composed result, so a later repeat validates the real final file.
        for previous in PATCHES:
            if previous in applied:
                applied[previous]['result'] = digest(target)
        temporary = receipt.with_suffix(receipt.suffix+'.new')
        temporary.write_text(json.dumps(applied, indent=2)+'\n')
        temporary.replace(receipt)
    text = target.read_text()
    for function in ('device_no_dfs', 'device_chanlist_band'):
        if text.count(function+'(config);') != 1:
            raise ValueError('Shared Wi-Fi policy missing or duplicated: '+function)
    return applied
