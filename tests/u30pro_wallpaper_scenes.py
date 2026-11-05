"""Real native scene policy and target ucode settings, without hardware access."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import struct
import tempfile
import unittest
import uuid
import zlib

TOP = Path(__file__).resolve().parents[1]
NATIVE = TOP/'devices/u30pro/native'


@unittest.skipUnless(os.name == 'posix', 'POSIX native simulator and target container')
class WallpaperScenes(unittest.TestCase):
    def test_native_scene_matrix_pause_presets_and_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = r'''#define UI_HOST
#define UI_RUN "TEST_RUN"
#define UI_SYSFS "TEST_RUN"
#define main simulator_main
#include "u30pro_ui.c"
#undef main
#include <assert.h>
static void reset_scene(int scene) {
 asleep=0;notice[0]=0;tc.down=tc.sdrag=0;anim_on=dragging=sheet_anim=fling.on=scroll_moving=0;tx_off=0;
 pin_mode=0;ov=OV_NONE;sheet=SH_NONE;sheet_pos=0;fn_sub=-1;page=PG_HOME;
 switch(scene) {
 case LIVE_LOCK:pin_mode=PIN_LOCKSCR;break;
 case LIVE_HOME:break;
 case LIVE_SIGNAL:page=PG_SIGNAL;break;
 case LIVE_TRAFFIC:page=PG_TRAFFIC;break;
 case LIVE_FUNC:page=PG_FUNC;break;
 case LIVE_FNPAGE:page=PG_FUNC;fn_sub=1;break;
 case LIVE_SHEET:sheet=SH_CTRL;sheet_pos=1;break;
 case LIVE_PIN:pin_mode=PIN_UNLOCK;break;
 case LIVE_POPUP:ov=OV_QR;break;
 }
}
int main(void) {
 ui_init_canvases();g_ms=vclock=10000;
 const int scenes[]={LIVE_LOCK,LIVE_HOME,LIVE_SIGNAL,LIVE_TRAFFIC,LIVE_FUNC,LIVE_FNPAGE,LIVE_SHEET,LIVE_PIN,LIVE_POPUP};
 for(int i=0;i<9;i++)for(int j=0;j<9;j++){
  reset_scene(scenes[j]);wp_live_pages=scenes[i];assert(live_here()==(i==j));
  wp_live_pages=LIVE_ALL;assert(live_here());wp_live_pages=0;assert(!live_here());
 }
 for(int legacy=0;legacy<3;legacy++)for(int j=0;j<9;j++){
  reset_scene(scenes[j]);wp_live_pages=-1;wp_live=legacy;
  assert(live_here()==((legacy>=1&&j==0)||(legacy==2&&j==1)));
 }
 reset_scene(LIVE_HOME);wp_live_pages=LIVE_ALL;
 asleep=1;assert(!live_here());asleep=0;notice[0]='x';assert(!live_here());notice[0]=0;
 tc.down=1;assert(!live_here());tc.down=0;anim_on=1;assert(!live_here());anim_on=0;
 dragging=1;assert(!live_here());dragging=0;sheet_anim=1;assert(!live_here());sheet_anim=0;
 tc.sdrag=1;assert(!live_here());tc.sdrag=0;fling.on=1;assert(!live_here());fling.on=0;
 scroll_moving=1;assert(!live_here());scroll_moving=0;tx_off=1;assert(!live_here());tx_off=-1;assert(!live_here());tx_off=0;
 assert(live_here());
 wp_live_pages=3;live_next();assert(live_mask()==511&&wp_live==2);
 live_next();assert(live_mask()==0&&wp_live==0);live_next();assert(live_mask()==1&&wp_live==1);
 live_next();assert(live_mask()==3&&wp_live==2);wp_live_pages=12;assert(live_preset()==NLIVE_PRESETS);
 live_next();assert(live_mask()==0);
 wp_live_pages=511;wp_live=2;settings_save();wp_live_pages=-1;wp_live=0;settings_load();
 assert(live_mask()==511&&wp_live==2);
 assert(gx_has_all(FN14,"动态壁纸关闭锁屏和主页全部界面自定义"));
 return 0;
}
'''.replace('TEST_RUN', str(base))
            (base/'test.c').write_text(source)
            result = subprocess.run(['gcc', '-std=gnu11', '-O1', '-I', str(NATIVE/'tools'),
                                     str(base/'test.c'), '-lm', '-o', str(base/'test')],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(base/'test')], text=True, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    @unittest.skipUnless(shutil.which('docker'), 'target ucode container')
    def test_target_rpc_mask_legacy_validation_and_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base/'config').mkdir()
            config = base/'config/u30pro_native_control'
            config.write_text("config display 'display'\noption wp_live '2'\n")
            module = (NATIVE/'ui/native-control/overlay/usr/share/u30pro/wallpaper.uc').read_text()
            module = module.replace('let uci = cursor();', "let uci = cursor('/fixture/config');")
            (base/'wallpaper.uc').write_text(module)
            (base/'rpc-wrapper').write_bytes(
                (NATIVE/'ui/native-control/overlay/usr/libexec/rpcd/u30pro-wallpaper').read_bytes())
            name = 'wallpaper-scenes-'+uuid.uuid4().hex[:8]
            subprocess.run(['docker','run','-d','--network','none','--platform','linux/arm64',
                            '--name',name,'-v',str(base)+':/fixture',
                            os.environ.get('FLOW_TEST_IMAGE','mu300-openwrt-base:25.12.5'),
                            '/bin/sleep','180'],check=True,stdout=subprocess.DEVNULL)
            try:
                signature = json.loads(subprocess.check_output(
                    ['docker','exec',name,'/bin/sh','/fixture/rpc-wrapper','list'],text=True))
                self.assertIn('pages',signature['set'])
                self.assertIn('live',signature['set'])
                self.assertIn('fast_panel',signature['set'])
                def rpc(method, values=None, ok=True):
                    result = subprocess.run(['docker','exec','-i',name,'/usr/bin/ucode',
                                             '/fixture/wallpaper.uc',method],
                                            input=json.dumps(values or {}),text=True,capture_output=True,timeout=10)
                    self.assertEqual(result.returncode==0,ok,result.stdout+result.stderr)
                    return json.loads(result.stdout)
                self.assertEqual(rpc('get')['settings']['pages'],3)
                self.assertEqual(rpc('get')['settings']['fast_panel'],0)
                self.assertEqual(rpc('set',dict(fast_panel=1))['settings']['fast_panel'],1)
                rpc('set',dict(glass=50))
                self.assertEqual(rpc('get')['settings']['fast_panel'],1)
                for invalid in (-1,2,1.5,'bad'):
                    before=config.read_bytes()
                    self.assertIn('error',rpc('set',dict(fast_panel=invalid),ok=False))
                    self.assertEqual(config.read_bytes(),before)
                self.assertEqual(rpc('set',dict(fast_panel=0))['settings']['fast_panel'],0)
                for mask in (0,1,2,3,4,12,128,256,383,511):
                    value=rpc('set',dict(pages=mask))['settings']
                    self.assertEqual(value['pages'],mask)
                    self.assertEqual(value['live'],2 if mask&2 else 1 if mask&1 else 0)
                    self.assertEqual(rpc('get')['settings']['pages'],mask)
                for invalid in (-1,512,1.5,'bad'):
                    before=config.read_bytes()
                    self.assertIn('error',rpc('set',dict(pages=invalid),ok=False))
                    self.assertEqual(config.read_bytes(),before)
                for legacy,mask in ((0,0),(1,1),(2,3)):
                    value=rpc('set',dict(live=legacy))['settings']
                    self.assertEqual(value['pages'],mask)
                    self.assertNotIn('wp_live_pages',config.read_text())
                # Existing glass-only callers must preserve the user's selected scenes.
                rpc('set',dict(pages=12));rpc('set',dict(glass=25))
                self.assertEqual(rpc('get')['settings']['pages'],12)
                # Test the real target upload/install path with both clip versions.
                jpg=b'\xff\xd8\xff\xe0fixture'
                def clip(version,size=240,tail=b'',cmf=None,fps=24):
                    block=zlib.compress(b'\0'+bytes(240*240*3)) if version==2 else jpg
                    if cmf is not None:block=bytes(cmf)+block[2:]
                    return (b'U3LW'+struct.pack('<BBHHHI',version,fps,size,size,16 if version==2 else 0,1)+
                            struct.pack('<I',len(block))+block+tail)
                def upload(data):
                    (base/'upload.live').write_bytes(data);(base/'upload.jpg').write_bytes(jpg)
                    for ext in ('live','jpg'):
                        subprocess.run(['docker','exec',name,'cp','/fixture/upload.'+ext,
                                        '/tmp/u30pro-wallpaper.'+ext],check=True)
                for version in (1,2):
                    upload(clip(version))
                    value=rpc('install')['wallpaper']
                    self.assertTrue(value['live']);self.assertEqual(value['live_version'],version)
                before=rpc('get')['live_version']
                for fps in (50,60):
                    upload(clip(2,fps=fps))
                    self.assertEqual(rpc('install')['wallpaper']['fps'],fps)
                for invalid in (clip(2,tail=b'x'),clip(2,size=480),clip(2,cmf=(0x88,0x1c))):
                    upload(invalid)
                    self.assertIn('error',rpc('install',ok=False))
                    self.assertEqual(rpc('get')['live_version'],before)
            finally:
                subprocess.run(['docker','rm','-f',name],check=True,stdout=subprocess.DEVNULL)


if __name__=='__main__':
    unittest.main(verbosity=2)
