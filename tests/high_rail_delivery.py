"""Real ordinary updater and diff generator/applier on isolated Pro fixture roots."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

from helpers import TOP
from test_update import Update

sys.path.insert(0,str(TOP/'installer'))
from backend.ota_engine import Engine, Patch
from backend.ota_package import analyze

FILES={
 'opt/mu300/bin/mu300-modemd':'rootfs/overlay/opt/mu300/bin/mu300-modemd',
 'usr/share/ucode/mu300/high-rail.uc':'rootfs/overlay/usr/share/ucode/mu300/high-rail.uc',
 'usr/share/ucode/mu300/dash.uc':'openwrt/luci-app-mu300/root/usr/share/ucode/mu300/dash.uc',
 'usr/sbin/u30pro-ui-feed':'devices/u30pro/overlay/usr/sbin/u30pro-ui-feed',
 'www/luci-static/resources/view/mu300/home.js':'openwrt/luci-app-mu300/htdocs/luci-static/resources/view/mu300/home.js',
 'www/luci-static/resources/mu300/common.js':'openwrt/luci-app-mu300/htdocs/luci-static/resources/mu300/common.js',
 'usr/lib/lua/luci/i18n/mu300.en.lmo':'openwrt/luci-app-mu300/lmo/mu300.en.lmo',
 'usr/lib/lua/luci/i18n/mu300.tr.lmo':'openwrt/luci-app-mu300/lmo/mu300.tr.lmo',
}
USER={'etc/config/wireless':b'user AP/password',
      'etc/config/unisoc_modem':b'user RF permissions',
      'etc/config/u30pro_native_control':b'user wallpaper settings',
      'root/wallpaper.png':b'user wallpaper', 'root/plugin/settings':b'user plugin data'}

def current(iteration=0):
    data={p:(TOP/source).read_bytes() for p,source in FILES.items()}
    data['usr/share/ucode/mu300/high-rail.uc']+=b'\n'*iteration
    panel=Path(os.environ.get('HIGH_RAIL_PANEL','/home/kano/openwrt-build/artifacts/u30pro-runtime/u30pro-panel'))
    binary=panel.read_bytes()
    assert binary[:6]==b'\x7fELF\x02\x01' and int.from_bytes(binary[18:20],'little')==183
    data['opt/u30pro/bin/u30pro-panel']=binary
    return data

def put(root,files):
    for name,data in files.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        path.chmod(0o755 if data.startswith((b'#!',b'\x7fELF')) else 0o644)

def archive(path,files):
    with tarfile.open(path,'w:gz') as tar:
        parents=sorted({str(p) for n in files for p in Path(n).parents if str(p)!='.'},key=lambda x:(x.count('/'),x))
        for name in parents:
            t=tarfile.TarInfo(name);t.type=tarfile.DIRTYPE;t.mode=0o755;t.uid=os.getuid();t.gid=os.getgid();tar.addfile(t)
        for name,data in files.items():
            t=tarfile.TarInfo(name);t.size=len(data);t.uid=os.getuid();t.gid=os.getgid()
            t.mode=0o755 if data.startswith((b'#!',b'\x7fELF')) else 0o644
            tar.addfile(t,io.BytesIO(data))

def release(root,profile,version,files):
    (root/'desktop').mkdir(parents=True);(root/'payload').mkdir()
    archive(root/'payload/mu300-openwrt.tar.gz',files)
    (root/'payload/boot-linux.img').write_bytes(b'unchanged fixture boot; never used on hardware')
    names=['payload/boot-linux.img','payload/mu300-openwrt.tar.gz']
    checks={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names}
    (root/'desktop/manifest.json').write_text(json.dumps({'magisk':checks,'desktop':{},'magisk_layout':{
        'boot-linux.img':names[0],'mu300-openwrt.tar.gz':names[1]}}))
    (root/'desktop/release.json').write_text(json.dumps({'profile':profile,'image_version':version,'kernel_release':'6.12.94-u30pro-p1','openwrt':'25.12.5'}))

class DiffDelivery(unittest.TestCase):
    def test_introduction_followup_rollback_and_preservation(self):
        for profile in ['u30pro','f50pro']:
            with self.subTest(profile=profile),tempfile.TemporaryDirectory() as d:
                d=Path(d);old={}
                for path,source in FILES.items():
                    r=subprocess.run(['git','-C',str(TOP),'show','HEAD:'+source],capture_output=True)
                    if r.returncode==0:old[path]=r.stdout
                old['opt/u30pro/bin/u30pro-panel']=b'synthetic previous panel'
                versions=[profile+'-rail-test-'+str(i) for i in range(3)]
                files=[old,current(),current(1)]
                if profile=='f50pro':
                    for f in files:
                        f.pop('opt/u30pro/bin/u30pro-panel',None);f.pop('usr/sbin/u30pro-ui-feed',None)
                for i in range(3):release(d/str(i),profile,versions[i],files[i])
                root=d/'root';put(root,{**old,**USER})
                identity=root/'etc/mu300/release.json';identity.parent.mkdir(parents=True,exist_ok=True)
                identity.write_text(json.dumps({'profile':profile,'image_version':versions[0],'kernel_release':'6.12.94-u30pro-p1'}))
                for i in [1,2]:
                    output=d/(str(i)+'.ota');report=analyze(d/str(i-1),d/str(i),output)
                    self.assertTrue(report['can_export'],report['blockers'])
                    with Patch(output) as patch:self.assertEqual(Engine(root).apply(patch)['status'],'complete')
                    for name,data in files[i].items():self.assertEqual((root/name).read_bytes(),data,name)
                    for name,data in USER.items():self.assertEqual((root/name).read_bytes(),data,name)
                engine=TOP/'installer/runtime/luci-app-unisoc-ota/root/usr/lib/unisoc-ota/engine.py'
                p=subprocess.run([sys.executable,str(engine),'rollback','--root',str(root)],capture_output=True,text=True)
                self.assertEqual(p.returncode,0,p.stdout+p.stderr)
                for name,data in files[1].items():self.assertEqual((root/name).read_bytes(),data,name)
                for name,data in USER.items():self.assertEqual((root/name).read_bytes(),data,name)

class OrdinaryDelivery(Update):
    def test_first_and_followup_screen_delivery(self):
        for shell in self.each_shell():
            old,_=self.vendor_update_fixture();put(old,USER)
            for iteration in [0,1]:
                files=current(iteration);files['sbin/init']=b'#!/bin/sh\n'
                archive(self.disk/'.mu300-update/mu300-openwrt-rootfs.tar.gz',files)
                p=self.up(shell,'sync() { :; }; is_root() { false; }; apply_one openwrt rail-test')
                self.assertEqual(p.returncode,0,p.stdout+p.stderr)
                for name,data in files.items():self.assertEqual((old/name).read_bytes(),data,name)
                for name,data in USER.items():self.assertEqual((old/name).read_bytes(),data,name)
                shutil.rmtree(self.disk/'openwrt.old')
            shutil.rmtree(old)

if __name__=='__main__':
    unittest.main(defaultTest=['DiffDelivery','OrdinaryDelivery.test_first_and_followup_screen_delivery'],verbosity=2)
