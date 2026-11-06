"""Exercise the production clock policy without touching a display or device."""
from pathlib import Path
import subprocess
import tempfile
import unittest

TOP = Path(__file__).resolve().parents[1]
NATIVE = TOP / 'devices/u30pro/native'


class Refresh(unittest.TestCase):
    def test_real_driver_commands_and_pixels_use_separate_clocks(self):
        driver = (NATIVE / 'kernel/ums9632/overlay/drivers/unisoc_platform/display/u30pro-nv3002c.c').read_text()

        def function(signature):
            start = driver.index(signature)
            brace = driver.index('{', start)
            depth = 0
            for end in range(brace, len(driver)):
                depth += (driver[end] == '{') - (driver[end] == '}')
                if not depth:
                    return driver[start:end + 1]
            raise AssertionError('Incomplete production function')

        harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
typedef unsigned char u8; typedef uint16_t u16; typedef unsigned int uint;
#define min(a,b) ((a)<(b)?(a):(b))
#define container_of(ptr,type,member) ((type *)((char *)(ptr)-offsetof(type,member)))
#define SPI_DELAY_UNIT_SCK 0
#define MIPI_DCS_SET_COLUMN_ADDRESS 0x2a
#define MIPI_DCS_SET_PAGE_ADDRESS 0x2b
#define MIPI_DCS_WRITE_MEMORY_START 0x2c
#define U30_SPI_MAX_HZ 96000000
static uint u30_spi_hz, u30_word_delay;
struct spi_transfer {const void *tx_buf;size_t len;uint speed_hz;int bits_per_word;struct{u16 value;int unit;}word_delay;};
struct spi_message {struct spi_transfer *xfer;void (*complete)(void *);void *context;};
struct mipi_dbi {void *spi,*dc;}; struct mipi_dbi_dev {struct mipi_dbi dbi;};
struct u30_panel {struct mipi_dbi_dev dbidev;uint hz;u16 *frame[2];int frame_next;bool te_armed,wr_busy;unsigned long wr_t0;struct spi_transfer wr_xfer;struct spi_message wr_msg;int wr_done;};
static int dc,waits,events;static struct {uint hz;int bpw,dc,async;size_t len;u8 bytes[16];} trace[4];
static void gpiod_set_value_cansleep(void *gpio,int value){(void)gpio;dc=value;}
static int record(struct spi_transfer *t,int async){
 assert(events<4);trace[events].hz=t->speed_hz;trace[events].bpw=t->bits_per_word;
 trace[events].dc=dc;trace[events].async=async;trace[events].len=t->len;
 memcpy(trace[events].bytes,t->tx_buf,min(t->len,sizeof trace[events].bytes));events++;return 0;
}
static int spi_sync_transfer(void *spi,struct spi_transfer *t,int n){(void)spi;assert(n==1);return record(t,0);}
static int spi_async(void *spi,struct spi_message *m){(void)spi;return record(m->xfer,1);}
static void spi_message_init_with_transfers(struct spi_message *m,struct spi_transfer *t,int n){assert(n==1);m->xfer=t;}
static void u30_write_wait(struct u30_panel *p){waits++;p->wr_busy=false;}
static void u30_wait_te(struct u30_panel *p){(void)p;}
static unsigned long ktime_get_ns(void){return 1;}
static void u30_write_end(void *p){(void)p;}
static void reinit_completion(int *p){*p=0;}
SPI_FUNCTION
COMMAND_FUNCTION
int main(void){
 u16 frames[2][4],pixels[]={0x1234,0x5678,0x9abc,0xdef0};
 struct u30_panel p={.frame={frames[0],frames[1]}};
 struct mipi_dbi *dbi=&p.dbidev.dbi;
 const uint fast[]={0,96000000,192000000};
 for(uint hz=40000000;hz<=48000000;hz+=8000000)for(unsigned k=0;k<3;k++){
  p.hz=hz;u30_spi_hz=fast[k];events=0;u8 cmd=0xb9,param=2;
  assert(u30_command(dbi,&cmd,&param,1)==0);
  assert(events==2&&trace[0].hz==hz&&trace[1].hz==hz);
  assert(trace[0].dc==0&&trace[1].dc==1&&trace[0].bpw==8&&trace[1].bpw==8);
  assert(trace[0].bytes[0]==cmd&&trace[1].bytes[0]==param);
  for(cmd=0x11;cmd<=0x29;cmd+=0x18){events=0;assert(u30_command(dbi,&cmd,0,0)==0);assert(events==1&&trace[0].hz==hz);}
  events=0;cmd=MIPI_DCS_WRITE_MEMORY_START;
  assert(u30_command(dbi,&cmd,(u8 *)pixels,sizeof pixels)==0);
  assert(events==2&&trace[0].hz==hz&&trace[0].bpw==8&&trace[0].dc==0);
  assert(trace[1].hz==(fast[k]?min(fast[k],U30_SPI_MAX_HZ):hz));
  assert(trace[1].async&&trace[1].bpw==16&&trace[1].dc==1&&p.wr_busy);
  assert(!memcmp(trace[1].bytes,(u16[]){0xdef0,0x9abc,0x5678,0x1234},sizeof pixels));
  int previous=waits;events=0;cmd=0x28;
  assert(u30_command(dbi,&cmd,0,0)==0);
  assert(waits==previous+1&&!p.wr_busy&&trace[0].hz==hz);
 }
 return 0;
}
'''.replace('SPI_FUNCTION', function('static int u30_spi(')).replace('COMMAND_FUNCTION', function('static int u30_command('))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'clock.c').write_text(harness)
            subprocess.run(['cc', '-std=gnu11', '-Wall', '-Werror', str(root / 'clock.c'),
                            '-o', str(root / 'clock')], check=True)
            subprocess.run([str(root / 'clock')], check=True, timeout=5)

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
