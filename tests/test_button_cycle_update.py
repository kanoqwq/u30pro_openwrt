"""Ordinary updates retain policy, two source choices, actions and user data."""
import io
import shutil
import tarfile
import unittest
from helpers import TOP
from test_update import Update

class ButtonUpdate(Update):
    def test_first_and_followup_keep_cycle_and_pair_preferences(self):
        files={
            **{dest:TOP/src for dest,src in {
                'opt/mu300/bin/u30pro-card-pair':'devices/u30pro/overlay/opt/mu300/bin/u30pro-card-pair',
                'usr/share/ucode/mu300/u30pro-card-pair.uc':'devices/u30pro/overlay/usr/share/ucode/mu300/u30pro-card-pair.uc',
                'usr/sbin/u30pro-sim-preinit':'devices/u30pro/overlay/usr/sbin/u30pro-sim-preinit',
                'opt/mu300/bin/mobile-data':'rootfs/overlay/opt/mu300/bin/mobile-data',
                'opt/mu300/bin/mu300-data-sim':'rootfs/overlay/opt/mu300/bin/mu300-data-sim',
                'usr/libexec/unisoc-modem/data-sim':'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/data-sim',
                'usr/libexec/unisoc-modem/product-form':'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/product-form',
                'www/luci-static/resources/view/mu300/sim.js':'openwrt/luci-app-mu300/htdocs/luci-static/resources/view/mu300/sim.js'}.items()},
            **{'www/luci-static/resources/'+name:TOP/'openwrt/luci-app-mu300/htdocs/luci-static/resources'/name
               for name in ('mu300/common.js','view/mu300/traffic.js')},
            'opt/mu300/bin/mu300-physical-sim':TOP/'rootfs/overlay/opt/mu300/bin/mu300-physical-sim',
            'usr/share/ucode/mu300/f50pro-feedback.uc':TOP/'devices/f50pro/overlay/usr/share/ucode/mu300/f50pro-feedback.uc',
            'usr/sbin/f50pro-leds':TOP/'devices/f50pro/overlay/usr/sbin/f50pro-leds',
            'usr/libexec/unisoc-modem/f50pro-sim-key.uc':TOP/'devices/f50pro/overlay/usr/libexec/unisoc-modem/f50pro-sim-key.uc',
            'usr/share/ucode/mu300/button-cycle.uc':TOP/'rootfs/overlay/usr/share/ucode/mu300/button-cycle.uc',
            'usr/libexec/unisoc-modem/button-cycle.uc':TOP/'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/button-cycle.uc',
            'usr/libexec/unisoc-modem/buttons.py':TOP/'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/buttons.py',
            'www/luci-static/resources/mu300/buttons.js':TOP/'openwrt/luci-app-mu300/htdocs/luci-static/resources/mu300/buttons.js'}
        for shell in self.each_shell():
            old,_=self.vendor_update_fixture()
            user={'etc/config/unisoc_modem':b"config modem 'main'\n option f50pro_button_cycle 'list'\n option f50pro_route0 '3'\n option f50pro_route1 '4'\n option u30pro_route0 '3'\n option u30pro_route1 '2'\n option f50pro_button_double 'custom'\n option f50pro_button_double_command 'logger mine'\n",
                'etc/config/u30pro_native_control':b"config control 'settings'\n option home_button_cycle 'list'\n option home_double_action 'data-switch'\n",
                'root/my-plugin/config':b'user plugin data'}
            for name,data in user.items():
                p=old/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
            for iteration in [0,1]:
                content={name:path.read_bytes()+b'\n'*iteration for name,path in files.items()}
                content['sbin/init']=b'#!/bin/sh\n'
                with tarfile.open(self.disk/'.mu300-update/mu300-openwrt-rootfs.tar.gz','w:gz') as tar:
                    for name,data in content.items():
                        t=tarfile.TarInfo(name);t.size=len(data);t.mode=0o755;tar.addfile(t,io.BytesIO(data))
                p=self.up(shell,'sync() { :; }; is_root() { false; }; apply_one openwrt buttons-new')
                self.assertEqual(p.returncode,0,p.stdout+p.stderr)
                for name,data in content.items():self.assertEqual((old/name).read_bytes(),data)
                for name,data in user.items():self.assertEqual((old/name).read_bytes(),data)
                shutil.rmtree(self.disk/'openwrt.old')
            shutil.rmtree(old)

def load_tests(loader,tests,pattern):
    return unittest.TestSuite([ButtonUpdate('test_first_and_followup_keep_cycle_and_pair_preferences')])

if __name__=='__main__':
    unittest.main(defaultTest='ButtonUpdate.test_first_and_followup_keep_cycle_and_pair_preferences',verbosity=2)
