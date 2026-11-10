"""Real native screen replay: full-screen call UI without hardware or dialing."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

TOP = Path(__file__).resolve().parents[1]
NATIVE = TOP / 'devices/u30pro/native/tools'


@unittest.skipUnless(os.name == 'posix', 'POSIX native screen simulator')
class IncomingScreen(unittest.TestCase):
    def test_locked_popup_ignore_hangup_return_and_dual_slot_lifetimes(self):
        code = r'''#define UI_HOST
#define UI_RUN "TEST_RUN"
#define main simulator_main
#include "u30pro_ui.c"
#undef main
#include <assert.h>
static void tap(int x,int y) {
 compose();ui_touch(T_DOWN,x,y,vclock);vclock+=40;g_ms=vclock;ui_touch(T_UP,x,y,vclock);compose();
}
int main(void) {
 ui_init_canvases();g_ms=vclock=10000;D.feed_ok=1;page=PG_SIGNAL;
 assert(gx_has_all(FN16,"来电未知号码") && gx_has_all(FN14,"忽略挂断处理中内置卡外置卡"));
 locked=1;lock_on=1;pin_mode=PIN_LOCKSCR;asleep=1;
 IncomingCall calls[3]={
  {.id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",.number="+8613800000000",.label="内置卡1"},
  {.id="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",.number="12345",.label="外置卡1"},
  {.id="dddddddddddddddddddddddddddddddd",.number="54321",.label="内置卡2"}};
 incoming_replace(calls,1);compose();
 assert(!asleep && locked && pin_mode==PIN_LOCKSCR && page==PG_SIGNAL);
 assert(incoming_visible() && nhits==2);
 shot_write(UI_RUN,"incoming");
 // A ring does not expire under the usual screen timeout.
 vclock+=600000;g_ms=vclock;apply_idle(vclock);assert(!asleep);
 // Swipes cannot leave the popup or unlock the device.
 ui_touch(T_DOWN,200,120,vclock);ui_touch(T_MOVE,40,120,vclock);ui_touch(T_UP,40,120,vclock);
 assert(page==PG_SIGNAL && locked && incoming_visible());
 tap(78,180);assert(!incoming_visible() && !incoming_busy);
 assert(locked && pin_mode==PIN_LOCKSCR && page==PG_SIGNAL);
 // Repeated ring and number updates must not undo ignore.
 snprintf(calls[0].number,sizeof calls[0].number,"13800000000");
 incoming_replace(calls,1);compose();assert(!incoming_visible());
 incoming_replace(calls,2);compose();assert(incoming_visible()==&incoming_calls[1]);
 tap(162,180);assert(incoming_busy && incoming_visible());
 // A newly observed call behind the current popup must not clear its pending action.
 incoming_replace(calls,3);compose();assert(incoming_busy && incoming_visible()==&incoming_calls[1]);
 // An ended call disappears; the ignored other call stays dismissed.
 incoming_replace(calls,1);compose();assert(!incoming_visible() && !incoming_busy);
 incoming_replace(calls,0);assert(incoming_count==0);
 // A new lifetime with the same number reopens the popup.
 calls[0].id[0]='c';incoming_replace(calls,1);compose();assert(incoming_visible());
 // A short power press ignores only; it does not unlock or request hangup.
 ui_key(116,100);assert(!incoming_visible() && locked && page==PG_SIGNAL);
 return 0;
}'''
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'test.c').write_text(code.replace('TEST_RUN', directory))
            build = subprocess.run(['gcc', '-std=gnu11', '-O1', '-Wall', '-Wextra',
                                    '-Wno-unused-function', '-I', str(NATIVE),
                                    str(base / 'test.c'), '-lm', '-o', str(base / 'test')],
                                   capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            replay = subprocess.run([str(base / 'test')], capture_output=True, text=True, timeout=20)
            self.assertEqual(replay.returncode, 0, replay.stdout + replay.stderr)
            self.assertEqual(replay.stdout.count('CALL_HANGUP '), 1)
            if os.environ.get('U30PRO_SCREEN_ARTIFACTS'):
                import shutil
                out = Path(os.environ['U30PRO_SCREEN_ARTIFACTS'])
                out.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(base / 'incoming.ppm', out / 'incoming.ppm')


if __name__ == '__main__':
    unittest.main()
