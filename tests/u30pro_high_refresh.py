"""Exercise the production clock policy without touching a display or device."""
from pathlib import Path
import subprocess
import tempfile
import unittest

TOP = Path(__file__).resolve().parents[1]
NATIVE = TOP / 'devices/u30pro/native'


class Refresh(unittest.TestCase):
    def test_optional_clock_lifecycle(self):
        platform = (NATIVE / 'tools/ui/platform.h').read_text()
        main = (NATIVE / 'tools/u30pro_ui.c').read_text()
        clock = platform[platform.index('static int fast_panel,'):platform.index('/* The kernel driver can send')]
        tick = main[main.index('static void panel_speed_tick('):main.index('\n#endif', main.index('static void panel_speed_tick('))]
        harness = r'''
#include <assert.h>
#include <string.h>
static int writes, hz, window, asleep, interval=1000;
static struct { int playing, fps; } lw;
static long frame_interval(void) { return interval; }
static int sysfs_write(const char *p, const char *v) {
    writes++;
    if(strstr(p,"spi_hz")) hz=atoi(v); else window=atoi(v);
    return 1;
}
CLOCK
TICK
int main(void) {
    panel_speed_tick(100);assert(hz==0&&window==0&&writes==2);
    interval=16;panel_speed_tick(200);assert(hz==0&&writes==2);
    fast_panel=1;panel_speed_tick(300);assert(hz==96000000&&window==4000&&writes==4);
    interval=1000;panel_speed_tick(1299);assert(hz==96000000&&writes==4);
    panel_speed_tick(1300);assert(hz==0&&window==0&&writes==6);
    lw.playing=1;lw.fps=50;panel_speed_tick(1500);assert(hz==96000000);
    asleep=1;panel_speed_tick(1501);assert(hz==0&&window==0);
    asleep=0;panel_speed_tick(1600);assert(hz==96000000);
    fast_panel=0;panel_speed(1);assert(hz==0&&window==0);
    lw.playing=0;lw.fps=24;panel_speed_tick(3000);
    fast_panel=1;panel_speed_tick(3001);assert(hz==0);
    return 0;
}
'''.replace('CLOCK', clock).replace('TICK', tick).replace('#include <assert.h>', '#include <assert.h>\n#include <stdlib.h>')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'refresh.c').write_text(harness)
            subprocess.run(['cc', '-std=gnu11', '-Wall', '-Werror', str(root / 'refresh.c'), '-o', str(root / 'refresh')], check=True)
            subprocess.run([str(root / 'refresh')], check=True, timeout=5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
