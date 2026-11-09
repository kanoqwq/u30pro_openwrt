"""Execute the native shell estimator with failed/healthy fake thermal zones."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

TOP = Path(__file__).resolve().parents[1]
DRIVER = TOP/'devices/u30pro/native/kernel/ums9632/overlay/drivers/unisoc_platform/thermal_sensor/u30pro_sprd_shell_thm.c'


class ShellThermalLogging(unittest.TestCase):
    @unittest.skipUnless(shutil.which('cc'), 'requires host C compiler')
    def test_wcn_error_noise_is_quiet_without_changing_fallback_or_hot_readings(self):
        source=DRIVER.read_text()
        constants='\n'.join(line for line in source.splitlines() if line.startswith(('#define SHELL_THM_', '#define COEFF(', '#define HTY(')))
        callbacks=source[source.index('static int shell_virt_temp('):source.index('static void shell_work(')]
        prelude=r'''
#include <errno.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
static int warnings, debug_messages;
#define pr_warn_ratelimited(...) (++warnings)
#define dev_dbg_ratelimited(...) (++debug_messages)
#define div_s64(a,b) ((a)/(b))
#define WRITE_ONCE(a,b) ((a)=(b))
struct thermal_zone_device { int value, error; };
static int thermal_zone_get_temp(struct thermal_zone_device *tz,int *value) {
 if(tz->error)return tz->error;
 *value=tz->value;return 0;
}
struct shell_sensor {
 void *dev; int nsensor, ntemp, index; const char **sensor_names;
 struct thermal_zone_device **ntc, *board; int *coeff,*hty_temp,*ntc_temp_diff;
 int const_temp,virt_temp_diff,last_temp,cur_temp; bool init_flag,have_temp;
};
'''
        checks=r'''
int main(void) {
 struct thermal_zone_device wcn={40000,-EIO},board={43000,0};
 struct thermal_zone_device *sensors[]={&wcn}; const char *names[]={"wcn-thmzone"};
 int coeff[]={10000},history[]={25000};
 struct shell_sensor s={.nsensor=1,.ntemp=1,.sensor_names=names,.ntc=sensors,
  .board=&board,.coeff=coeff,.hty_temp=history,.last_temp=120000,.init_flag=true};
 for(int i=0;i<100;i++) { shell_update(&s); if(!s.have_temp||s.cur_temp!=43000)return 1; }
 if(warnings||debug_messages!=100)return 2;
 wcn.error=0;s.last_temp=120000;
 shell_update(&s);if(s.cur_temp!=40000)return 3;
 wcn.value=125000;
 shell_update(&s);if(s.cur_temp!=43000||warnings!=1)return 4;
 names[0]="pa-thmzone";wcn.error=-EIO;
 shell_update(&s);if(s.cur_temp!=43000||warnings!=2)return 5;
 board.error=-EIO;s.cur_temp=57000;
 shell_update(&s);if(s.cur_temp!=57000||warnings!=4)return 6;
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'shell.c';binary=root/'shell'
            path.write_text(prelude+constants+'\n'+callbacks+checks)
            subprocess.run(['cc','-std=c99','-Wall','-Werror',str(path),'-o',str(binary)],check=True,capture_output=True)
            subprocess.run([str(binary)],check=True)


if __name__ == '__main__': unittest.main()
