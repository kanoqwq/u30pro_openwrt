"""Actual native frame decoder and incremental renderer, without touching hardware."""
import importlib.util
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib

TOP=Path(__file__).resolve().parents[1]
NATIVE=TOP/'devices/u30pro/native'

@unittest.skipUnless(os.name=='posix','POSIX native simulator')
class WallpaperTiles(unittest.TestCase):
    def test_decode_loop_legacy_malformed_and_reground(self):
        spec=importlib.util.spec_from_file_location('make_live',TOP/'tests/ui/make_live.py')
        fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            frames=[fixture.frame(i) for i in range(5)]
            header=b'U3LW'+struct.pack('<BBHHHI',2,24,240,240,16,5)
            parts=[];prev=None
            for f in frames:
                block=zlib.compress(fixture.payload(prev,f));parts.append(struct.pack('<I',len(block))+block);prev=f
            (base/'wallpaper.live').write_bytes(header+b''.join(parts))
            for fps in (0,50,60,61):
                (base/f'fps{fps}.live').write_bytes(header[:5]+bytes([fps])+header[6:]+b''.join(parts))
            (base/'frames.rgb').write_bytes(b''.join(frames))
            (base/'trailing.live').write_bytes(header+b''.join(parts)+b'x')
            bad=zlib.compress(b'\1'+b'\0'*29)
            (base/'first-delta.live').write_bytes(header[:12]+struct.pack('<I',1)+struct.pack('<I',len(bad))+bad)
            bomb=zlib.compress(b'\0'*(240*240*3+100))
            (base/'oversize.live').write_bytes(header[:12]+struct.pack('<I',1)+struct.pack('<I',len(bomb))+bomb)
            from PIL import Image
            Image.frombytes('RGB',(240,240),frames[0]).save(base/'wallpaper.jpg')
            jpg=(base/'wallpaper.jpg').read_bytes()
            (base/'legacy.live').write_bytes(b'U3LW'+struct.pack('<BBHHHI',1,15,240,240,0,1)+struct.pack('<I',len(jpg))+jpg)
            source=r'''#define UI_HOST
#define UI_RUN "TEST_RUN"
#define UI_SYSFS "TEST_RUN"
#define main simulator_main
#include "u30pro_ui.c"
#undef main
#include <assert.h>
static void scene(int n) {
 asleep=0;notice[0]=0;tc.down=tc.sdrag=0;anim_on=dragging=sheet_anim=fling.on=scroll_moving=0;tx_off=0;
 pin_mode=0;ov=OV_NONE;sheet=SH_NONE;sheet_pos=0;fn_sub=-1;page=PG_HOME;
 switch(n){case 0:pin_mode=PIN_LOCKSCR;break;case 1:break;case 2:page=PG_SIGNAL;break;
 case 3:page=PG_TRAFFIC;break;case 4:page=PG_FUNC;break;case 5:page=PG_FUNC;fn_sub=1;break;
 case 6:sheet=SH_CTRL;sheet_pos=1;break;case 7:pin_mode=PIN_UNLOCK;break;case 8:ov=OV_QR;break;}
}
int main(void) {
 static uint8_t expected[WP_N*3];static uint32_t keep[WP_N];
 ui_init_canvases();g_ms=vclock=10000;
 assert(lw_open(UI_RUN "/wallpaper.live")==0);
 FILE *raw=fopen(UI_RUN "/frames.rgb","rb");assert(raw);
 const int order[]={0,4,1,3,0,2,4};
 for(unsigned i=0;i<sizeof(order)/sizeof(*order);i++){
  assert(lw_show(order[i])==0);assert(fseek(raw,(long)order[i]*sizeof expected,SEEK_SET)==0);
  assert(fread(expected,1,sizeof expected,raw)==sizeof expected);assert(!memcmp(wp_rgb,expected,sizeof expected));
 }
 fclose(raw);wp_on=1;wp_live_pages=LIVE_ALL;
 for(int tint=0;tint<4;tint++)for(int s=0;s<9;s++){
  glass_tint=tint;glass_blur=(tint%3)*50;glass_clear=20+tint*20;wp_derive();scene(s);compose();
  assert(wp_ground_rest(&scr));
  for(int f=0;f<3;f++){
   assert(lw_show((lw.cur+1)%lw.n)==0);wp_reground(&scr);memcpy(keep,scr.p,sizeof keep);compose();
   int worst=0,over8=0;
   for(int i=0;i<WP_N;i++)for(int k=0;k<24;k+=8){int d=abs((int)(keep[i]>>k&255)-(int)(scr.p[i]>>k&255));if(d>worst)worst=d;over8+=d>8;}
   if(over8){fprintf(stderr,"reground tint=%d scene=%d worst=%d over8=%d\n",tint,s,worst,over8);return 1;}
   assert(wp_ground_rest(&scr));
  }
 }
 assert(lw_open(UI_RUN "/trailing.live")==-1);
 assert(lw_open(UI_RUN "/first-delta.live")==0);assert(lw_show(0)==-1);
 assert(lw_open(UI_RUN "/oversize.live")==0);assert(lw_show(0)==-1);
 assert(lw_open(UI_RUN "/legacy.live")==0);assert(lw_show(0)==0);assert(lw.ver==1);
 lw_close();
 assert(lw_open(UI_RUN "/fps50.live")==0);assert(lw.fps==50);assert(lw_show(0)==0);lw_close();
 assert(lw_open(UI_RUN "/fps60.live")==0);assert(lw.fps==60);assert(lw_show(0)==0);lw_close();
 assert(lw_open(UI_RUN "/fps0.live")==-1);assert(lw_open(UI_RUN "/fps61.live")==-1);
 return 0;
}
'''.replace('TEST_RUN',str(base))
            (base/'test.c').write_text(source)
            subprocess.run(['gcc','-std=gnu11','-O1','-I',str(NATIVE/'tools'),str(base/'test.c'),'-lm','-ldl','-o',str(base/'test')],check=True,capture_output=True)
            result=subprocess.run([str(base/'test')],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__=='__main__':unittest.main(verbosity=2)
