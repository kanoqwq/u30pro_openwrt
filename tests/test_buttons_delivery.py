"""First introduction and later button-code updates through the pinned OTA generator."""
import json
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest

TOP=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(TOP/'installer'),str(TOP/'installer/tests')]
from test_ota import mu_release
from backend.ota_package import analyze
from backend.ota_engine import Engine, Patch


@unittest.skipUnless(sys.platform=='linux','requires Linux file metadata')
class Delivery(unittest.TestCase):
    def test_first_and_second_update_preserve_saved_actions_and_user_data(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);live=base/'live';live.mkdir()
            config=b"config modem 'main'\n option u30air_button_double 'custom'\n option u30air_button_double_command 'logger mine'\n option f50pro_button_cycle 'list'\n option f50pro_route0 '3'\n option f50pro_route1 '4'\n option u30pro_route0 '3'\n option u30pro_route1 '2'\n"
            native=b"config control 'settings'\n option power_short_action 'none'\n option home_button_cycle 'list'\n option home_double_action 'data-switch'\n"
            saved={'etc/config/unisoc_modem':config,'etc/config/u30pro_native_control':native,
                   'etc/config/wireless':b'USER WIFI','root/user-data':b'KEEP DATA'}
            code={
              **{dest:(TOP/src).read_bytes() for dest,src in {
                'opt/mu300/bin/u30pro-card-pair':'devices/u30pro/overlay/opt/mu300/bin/u30pro-card-pair',
                'usr/share/ucode/mu300/u30pro-card-pair.uc':'devices/u30pro/overlay/usr/share/ucode/mu300/u30pro-card-pair.uc',
                'usr/sbin/u30pro-sim-preinit':'devices/u30pro/overlay/usr/sbin/u30pro-sim-preinit',
                'opt/mu300/bin/mobile-data':'rootfs/overlay/opt/mu300/bin/mobile-data',
                'opt/mu300/bin/mu300-data-sim':'rootfs/overlay/opt/mu300/bin/mu300-data-sim',
                'usr/libexec/unisoc-modem/data-sim':'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/data-sim',
                'usr/libexec/unisoc-modem/product-form':'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/product-form',
                'www/luci-static/resources/view/mu300/sim.js':'openwrt/luci-app-mu300/htdocs/luci-static/resources/view/mu300/sim.js'}.items()},
              **{'www/luci-static/resources/'+name:(TOP/'openwrt/luci-app-mu300/htdocs/luci-static/resources'/name).read_bytes()
                 for name in ('mu300/common.js','view/mu300/traffic.js')},
              'opt/mu300/bin/mu300-physical-sim':(TOP/'rootfs/overlay/opt/mu300/bin/mu300-physical-sim').read_bytes(),
              'usr/share/ucode/mu300/f50pro-feedback.uc':(TOP/'devices/f50pro/overlay/usr/share/ucode/mu300/f50pro-feedback.uc').read_bytes(),
              'usr/sbin/f50pro-leds':(TOP/'devices/f50pro/overlay/usr/sbin/f50pro-leds').read_bytes(),
              'usr/libexec/unisoc-modem/f50pro-sim-key.uc':(TOP/'devices/f50pro/overlay/usr/libexec/unisoc-modem/f50pro-sim-key.uc').read_bytes(),
              'usr/libexec/unisoc-modem/button-cycle.uc':(TOP/'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/button-cycle.uc').read_bytes(),
              'usr/share/ucode/mu300/button-cycle.uc':(TOP/'rootfs/overlay/usr/share/ucode/mu300/button-cycle.uc').read_bytes(),
              'usr/libexec/unisoc-modem/buttons':(TOP/'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/buttons').read_bytes(),
              'usr/libexec/unisoc-modem/buttons.py':(TOP/'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/buttons.py').read_bytes(),
              'www/luci-static/resources/mu300/buttons.js':(TOP/'openwrt/luci-app-mu300/htdocs/luci-static/resources/mu300/buttons.js').read_bytes(),
              'opt/mu300/bin/mu300-sysd':(TOP/'rootfs/overlay/opt/mu300/bin/mu300-sysd').read_bytes()}
            baseline={'usr/lib/anchor':b'old','etc/config/unisoc_modem':b'factory',
                      'etc/config/u30pro_native_control':b'factory'}
            for name,raw in dict(baseline,**saved).items():
                p=live/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
            # All payload ancestors already exist on the real control-center image.
            for name in code:(live/name).parent.mkdir(parents=True,exist_ok=True)
            identity=live/'etc/mu300/release.json';identity.parent.mkdir(exist_ok=True)
            identity.write_text(json.dumps(dict(image_version='mu300-r1',profile='mu300',kernel_release='7.2.8')))
            releases=[]
            for number,files in enumerate((baseline,dict(baseline,**code),
                    dict(baseline,**{name:raw+b'\n' for name,raw in code.items()})),1):
                path=base/str(number);mu_release(path,'mu300-r'+str(number),files)
                releases.append(path)
            for number in range(2):
                patch=base/(str(number)+'.ota')
                result=analyze(releases[number],releases[number+1],patch)
                self.assertTrue(result['can_export'],result['blockers'])
                ops={op['path'] for op in result['manifest']['operations']}
                self.assertTrue(set(code)<=ops)
                with Patch(patch) as archive:
                    self.assertEqual(Engine(live).apply(archive)['status'],'complete')
                for name,raw in saved.items():self.assertEqual((live/name).read_bytes(),raw)
                for name,raw in code.items():
                    self.assertEqual((live/name).read_bytes(),raw+(b'\n' if number else b''))
            engine=TOP/'installer/runtime/luci-app-unisoc-ota/root/usr/lib/unisoc-ota/engine.py'
            p=subprocess.run([sys.executable,str(engine),'rollback','--root',str(live)],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            for name,raw in code.items():self.assertEqual((live/name).read_bytes(),raw)
            for name,raw in saved.items():self.assertEqual((live/name).read_bytes(),raw)


if __name__=='__main__':unittest.main()
