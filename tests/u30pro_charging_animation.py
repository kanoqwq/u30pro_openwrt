"""Replay the actual frame scheduler and charge ring without panel hardware."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

TOP = Path(__file__).resolve().parents[1]
NATIVE = TOP / 'devices/u30pro/native/tools'


@unittest.skipUnless(os.name == 'posix', 'POSIX native screen simulator')
class ChargingAnimation(unittest.TestCase):
    def test_visible_charge_ring_uses_fast_frames_without_touch(self):
        code = r'''#define UI_HOST
#define UI_RUN "TEST_RUN"
#define main simulator_main
#include "u30pro_ui.c"
#undef main
#include <assert.h>
int main(void) {
 ui_init_canvases(); g_ms=vclock=100000; D.feed_ok=1;
 page=PG_HOME; D.bat_ok=1; D.bat_pct=55; D.charging=1;
 assert(!tc.down && !dragging && !anim_on);
 assert(charging_animation_visible() && frame_interval()==16);
 compose(); size_t size=SCREEN*SCREEN*sizeof(uint32_t);
 void *first=malloc(size);memcpy(first,scr.p,size);
 g_ms+=16;compose();assert(memcmp(first,scr.p,size)!=0);free(first);
 pin_mode=PIN_LOCKSCR;assert(frame_interval()==16);
 pin_mode=PIN_UNLOCK;assert(!charging_animation_visible());pin_mode=PIN_NONE;
 page=PG_FUNC;fn_sub=-1;
 for(int i=0;i<nfn_entries;i++)if(fn_entries[i].plugin<0 && fn_entries[i].fn==FN_POWER)fn_sub=i;
 assert(fn_sub>=0 && frame_interval()==16);
 page=PG_SIGNAL;assert(!charging_animation_visible());
 page=PG_HOME;sheet=SH_CTRL;sheet_pos=1;assert(!charging_animation_visible());
 sheet=SH_NONE;sheet_pos=0;power_menu=1;assert(!charging_animation_visible());power_menu=0;
 notice[0]='x';assert(!charging_animation_visible() && frame_interval()==33);notice[0]=0;
 asleep=1;assert(!charging_animation_visible());asleep=0;
 D.charging=0;assert(!charging_animation_visible() && frame_interval()==1000);
 D.charging=1;D.bat_pct=0;assert(!charging_animation_visible());
 D.bat_pct=55;D.bat_ok=0;assert(!charging_animation_visible());
 return 0;
}'''
        with tempfile.TemporaryDirectory(prefix='charge-ring-') as directory:
            root = Path(directory)
            source = root/'test.c'
            source.write_text(code.replace('TEST_RUN', directory))
            p = subprocess.run(['gcc','-std=gnu11','-O1','-Wno-unused-function','-I',str(NATIVE),
                                str(source),'-lm','-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            p = subprocess.run([str(root/'test')],capture_output=True,text=True,timeout=20)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)


if __name__ == '__main__':
    unittest.main()
