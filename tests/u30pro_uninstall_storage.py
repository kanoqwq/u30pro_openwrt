"""Run the production maintenance wait script in a private fake-device root."""
import os
from pathlib import Path
import runpy
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

TOP=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(TOP/'installer'),str(TOP/'installer/tests')]
from test_u30pro_boot import image,boot
from backend.uninstall_boot import build,archives,entries


@unittest.skipUnless(os.name=='posix' and hasattr(os,'geteuid') and os.geteuid()==0,
                     'requires Linux chroot and private fixture block nodes')
class MaintenanceStorage(unittest.TestCase):
    def test_real_generated_request_reaches_userdata_before_and_after_root_removal(self):
        _,_,layout=runpy.run_path(str(TOP/'tools/build-settings.py'))['settings']()
        init=(TOP/'devices/u30pro/init').read_bytes().replace(b'\r\n',b'\n')
        wait=(TOP/'devices/u30pro/boot-wait.sh').read_bytes().replace(b'\r\n',b'\n')
        generic=boot.overlay({'init':(init,stat.S_IFREG|0o755),
            'etc/u30pro-boot-wait.sh':(wait,stat.S_IFREG|0o644)})
        # The distributed canonical payload deliberately has no root-mode file.
        canonical=image(b'UNCHANGED KERNEL',generic,64<<20)
        for slot in ('a','b'):
            request=build(canonical,'mu300',{},android_slot=slot)
            members={n:v for arc in archives(boot.native_boot_parts(request)[1]) for n,v,m in entries(arc)}
            self.assertEqual(members['etc/mu300-android-slot'],(slot+'\n').encode())
            self.assertNotIn(b'desktop_storage_start ||',members['init'])
            for disk in ('mmcblk0','sda'):
                def part(n):return disk+('p' if disk.startswith('mmc') else '')+str(n)
                for root_present in (True,False):
                    with self.subTest(slot=slot,disk=disk,root_present=root_present), \
                            tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as directory:
                        root=Path(directory)
                        for name in ('bin','etc','dev','usr/sbin'):(root/name).mkdir(parents=True,exist_ok=True)
                        binary=root/'bin/busybox';shutil.copyfile(layout['busybox'],binary);binary.chmod(0o755)
                        for name in ('sh','cat'):(root/'bin'/name).symlink_to('busybox')
                        (root/'etc/wait.sh').write_bytes(members['etc/u30pro-boot-wait.sh'])
                        mode=root/'etc/mu300-desktop-root-mode'
                        mode.write_bytes(members['etc/mu300-desktop-root-mode'])
                        nodes=root/'usr/sbin/u30pro-nodes';nodes.write_text('#!/bin/busybox sh\nexit 0\n');nodes.chmod(0o755)
                        for n in ((4,83,84) if root_present else (4,83)):
                            os.mknod(root/'dev'/part(n),stat.S_IFBLK|0o600,os.makedev(240,254))
                        command=('export PATH=/bin; . /etc/wait.sh; '
                            'mu300_storage_disk() { echo '+disk+'; }; '
                            'mu300_storage_part() { case "$1" in misc) echo '+part(4)+';; '
                            'userdata) echo '+part(83)+';; mu300root) echo '+part(84)+';; esac; }; '
                            'if u30pro_wait_storage; then echo WORKER_REACHABLE; else echo RESCUE; exit 42; fi')
                        result=subprocess.run(['chroot',root,'/bin/busybox','sh','-c',command],capture_output=True,text=True,timeout=10)
                        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                        self.assertIn('WORKER_REACHABLE',result.stdout)
                        # Negative control reproduces the released-image defect.
                        mode.unlink()
                        result=subprocess.run(['chroot',root,'/bin/busybox','sh','-c',command],capture_output=True,text=True,timeout=10)
                        self.assertEqual(result.returncode,42,result.stdout+result.stderr)


if __name__=='__main__':unittest.main()
