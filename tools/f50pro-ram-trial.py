#!/usr/bin/env python3
"""Build a file-only F50 Pro RAM trial from registered, production inputs.

No ADB, flashing, GPT, NV or installation. Caller supplies this device's backed
up templates, a fresh 32-byte control block and read-only stock selection.
Invoke through build-release.py run --profiles f50pro-6.12.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import stat
import struct
import tarfile

TOP=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--templates',type=Path,required=True)
    p.add_argument('--control',type=Path,required=True)
    p.add_argument('--android-slot',choices=('a','b'),required=True)
    p.add_argument('--board',type=int,required=True)
    p.add_argument('--card',type=int,required=True)
    p.add_argument('--dsds',choices=('0','1'),required=True,
                   help='Actual Android car_mode_dual_sim_switch; never infer from SIM presence')
    p.add_argument('--chip',choices=('0','1'),required=True)
    p.add_argument('--psim',choices=('0','1'),required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if os.environ.get('U30PRO_BUILD_LOCKED')!='1' or os.environ.get('UMS9632_MODEL')!='f50pro':
        raise ValueError('Use the logged build runner with the F50 Pro profile')
    package=runpy.run_path(str(TOP/'tools/u30pro-package.py'))
    package['owned']();package['verified_kernel']()
    root=package['ROOT']
    if (root/'etc/mu300/model').read_text().strip()!='f50pro':raise ValueError('Wrong prepared root')
    boards=json.loads((TOP/'devices/f50pro/board-topology.json').read_text())['boards']
    board=boards.get(str(a.board))
    if not board or a.board==1000 or a.card not in board['builtin']+board['physical']:
        raise ValueError('Unverified stock physical-card selection')
    desktop=runpy.run_path(str(TOP/'desktop/boot_image.py'))
    control=a.control.read_bytes()
    trial=desktop['boot_control'](control,a.android_slot)
    if a.out.exists():raise ValueError('Trial output already exists; inspect before reuse')
    a.out.mkdir(parents=True)
    root_tar=a.out/'root.tar.gz'
    with tarfile.open(root_tar,'w:gz',compresslevel=3,dereference=False) as tar:
        for path in sorted(root.iterdir()):tar.add(path,arcname=path.name)
    report=package['verified_kernel']()
    release=runpy.run_path(str(TOP/'tools/release-identity.py'))['identify'](TOP,'f50pro',report['version'])
    release['trial']='RAM-only; NV writeback off; Android next boot; 600 second timeout'
    files={}
    def add(name,data,mode=0o644):files[name]=(data,stat.S_IFREG|mode)
    for name,path in {
        'init':TOP/'devices/f50pro/ram-init',
        'bin/busybox':Path(package['LAYOUT']['busybox']),
        'usr/sbin/u30pro-nodes':package['RUNTIME']/'u30pro-nodes',
        'usr/sbin/u30pro-usb':package['NATIVE']/'ui/native-control/overlay/usr/sbin/u30pro-usb'
    }.items():
        data=path.read_bytes()
        add(name,data.replace(b'\r\n',b'\n') if data.startswith(b'#!') else data,0o755)
    for name,data in {'etc/mu300-model':b'f50pro\n',
            'etc/trial-android-bc.bin':control,'etc/trial-linux-bc.bin':trial,
            'etc/trial-android-slot':(a.android_slot+'\n').encode(),
            'etc/trial-board':(str(a.board)+'\n').encode(),
            'etc/trial-card':(str(a.card)+'\n').encode(),
            'etc/trial-dsds':(a.dsds+'\n').encode(),
            'etc/trial-chip':(a.chip+'\n').encode(),
            'etc/trial-psim':(a.psim+'\n').encode(),
            'etc/trial-release.json':(json.dumps(release)+'\n').encode(),
            'trial-root.tar.gz':root_tar.read_bytes()}.items():add(name,data)
    builder=runpy.run_path(str(TOP/'boot/build-boot-image.py'))
    ram=builder['lz4_legacy'](builder['cpio_archive']({'dev','proc','sys','run','tmp','newroot'},files))
    kernel=(package['KERNEL']/'arch/arm64/boot/Image').read_bytes()
    templates={name:(a.templates/(name+'_'+a.android_slot+'.img')).read_bytes()
               for name in ('boot','vendor_boot','init_boot')}
    header=bytearray(templates['boot'][:4096])
    struct.pack_into('<II',header,8,len(kernel),len(ram));struct.pack_into('<I',header,1580,0)
    header[44:1580]=b'loglevel=5\0'.ljust(1536,b'\0')
    payload=bytes(header)+kernel+bytes(-len(kernel)%4096)+ram
    if len(payload)>48<<20:raise ValueError('RAM trial exceeds the boot diagnostic boundary')
    fw=runpy.run_path(str(package['NATIVE']/'tools/firmware.py'))
    canonical=fw['retain_avb_container'](templates['boot'],payload)
    codec=runpy.run_path(str(TOP/'installer/runtime/luci-app-unisoc-ota/root/usr/lib/unisoc-ota/boot.py'))
    output=codec['native_images'](canonical,templates)
    (a.out/'canonical.img').write_bytes(canonical)
    (a.out/'linux-bc.bin').write_bytes(trial)
    rows={}
    for name,data in output.items():
        (a.out/(name+'.img')).write_bytes(data)
        rows[name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    manifest=dict(model='f50pro',android_slot=a.android_slot,linux_slot='b' if a.android_slot=='a' else 'a',
                  board=a.board,card=a.card,dsds=a.dsds,chip=a.chip,psim=a.psim,root='RAM-only',nv_writeback='off',
                  kernel_sha256=report['image_sha256'],files=rows,
                  root_sha256=package['digest'](root_tar),boot_payload_bytes=len(payload),device_writes=False)
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    root_tar.unlink()  # This owned temporary payload is now inside verified containers.
    print(json.dumps(manifest,indent=2),flush=True)


if __name__=='__main__':main()
