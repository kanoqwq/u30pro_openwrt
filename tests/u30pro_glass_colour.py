"""Run the real wallpaper tone/render code on synthetic colours, no device access."""
from pathlib import Path
import subprocess
import tempfile
import unittest

TOP = Path(__file__).resolve().parents[1]
NATIVE = TOP / 'devices/u30pro/native'


class GlassColour(unittest.TestCase):
    def test_colour_contrast_exposure_and_setting_boundaries(self):
        source = r'''#define UI_HOST
#define UI_RUN "TEST_RUN"
#define UI_SYSFS "TEST_RUN"
#define main simulator_main
#include "u30pro_ui.c"
#undef main
#include <assert.h>
static void solid(int r, int g, int b) {
 for(int i=0;i<WP_N;i++){wp_rgb[i*3]=r;wp_rgb[i*3+1]=g;wp_rgb[i*3+2]=b;}
}
static int luma(const uint8_t *q) {return (q[0]*77+q[1]*150+q[2]*29)>>8;}
int main(void) {
 ui_init_canvases();wp_dim=0;glass_clear=100;glass_blur=0;glass_tint=0;
 /* Pale skin/pink keeps more chroma than proportional RGB darkening. */
 solid(245,205,210);wp_derive(0);
 uint8_t pink[]={245,205,210},out[3];
 tone_px(&wp_tones[0],pink,out);
 int proportional=((pink[0]-pink[1])*wp_tones[0].fac[luma(pink)])>>16;
 assert(out[0]>out[1]&&out[0]-out[1]>proportional);
 /* A bright gradient must retain visible tonal separation under the glass. */
 for(int i=0;i<WP_N;i++)for(int c=0;c<3;c++)wp_rgb[i*3+c]=160+(i%96);
 wp_derive(0);
 uint8_t lo[]={184,184,184},hi[]={232,232,232},a[3],b[3];
 tone_px(&wp_tones[0],lo,a);tone_px(&wp_tones[0],hi,b);
 assert(b[0]-a[0]>=20);
 /* A dark picture needs no exposure reduction. */
 solid(25,25,25);wp_derive(0);assert(fabsf(wp_gain-1.f)<.0001f);
 tone_px(&wp_tones[0],wp_rgb,out);assert(out[0]==25&&out[1]==25&&out[2]==25);
 /* Live frames approach their own exposure, not an abrupt brightness jump. */
 solid(245,245,245);wp_derive(0);float bright=wp_gain;
 solid(25,25,25);wp_derive(1);float smoothed=wp_gain;
 assert(smoothed>bright&&smoothed<1.f);
 assert(fabsf(smoothed-(bright+(1.f-bright)*.15f))<.0001f);
 wp_derive(0);assert(fabsf(wp_gain-1.f)<.0001f);
 /* Cover opaque/clear glass, dark/light/theme tints and all input lumas. */
 for(int tint=0;tint<NTINT;tint++)for(int clear=0;clear<=100;clear+=10){
  glass_tint=tint;glass_clear=clear;
  for(int i=0;i<WP_N;i++)for(int c=0;c<3;c++)wp_rgb[i*3+c]=i%256;
  wp_derive(0);assert(isfinite(wp_gain));
  /* White-fog glass uses its lightening curve, not the dark exposure gain. */
  if(tint!=2)assert(wp_gain>=0.f&&wp_gain<=1.f);
  for(int k=0;k<2;k++){
   int previous=-1;
   for(int l=0;l<256;l++){
    uint8_t q[]={(uint8_t)l,(uint8_t)l,(uint8_t)l};
    tone_px(&wp_tones[k],q,out);
    /* The existing 16.16 lightening path can round adjacent grays by one LSB. */
    if(!(out[0]==out[1]&&out[1]==out[2]&&out[0]+1>=previous))
     fprintf(stderr,"tone boundary tint=%d clear=%d input=%d out=%d,%d,%d previous=%d gain=%f\n",tint,clear,l,out[0],out[1],out[2],previous,wp_gain);
    assert(out[0]==out[1]&&out[1]==out[2]&&out[0]+1>=previous);
    if(tint==2)assert(out[0]>=l);
    previous=out[0];
   }
  }
 }
 /* Full scrim is neutral, rather than introducing a blue cast. */
 for(int i=0;i<WP_N;i++)scr.p[i]=0x808080;
 scrim(&scr,255);
 assert((scr.p[0]>>16&255)==(scr.p[0]>>8&255));
 assert((scr.p[0]>>8&255)==(scr.p[0]&255));
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'glass.c').write_text(source.replace('TEST_RUN', directory))
            subprocess.run(['cc', '-std=gnu11', '-O1', '-I', str(NATIVE / 'tools'),
                            str(root / 'glass.c'), '-lm', '-ldl', '-o', str(root / 'glass')],
                           check=True, capture_output=True)
            result = subprocess.run([str(root / 'glass')], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
