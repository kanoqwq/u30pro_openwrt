"""Exercise the actual ADI restart preparation with private PMIC/PSCI stubs."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from u30pro_sdio_clock import function

TOP = Path(__file__).resolve().parents[1]
DRIVER = TOP/'devices/u30pro/native/kernel/ums9632/overlay/drivers/spi/spi-sprd-adi.c'


@unittest.skipUnless(os.name == 'posix', 'compile the kernel C fixture on Linux')
class Restart(unittest.TestCase):
    def test_actual_prepare_and_registration(self):
        text = DRIVER.read_text()
        definitions = '\n'.join(re.findall(
            r'^#define\s+(?:HWRST_STATUS_\w+|UMS9632_\w+)[^\n]*', text, re.M))
        helpers = '\n'.join(function(text, name) for name in (
            'sprd_adi_ums9632_reboot_mode', 'sprd_adi_prepare_psci_restart',
            'sprd_adi_register_restart'))
        source = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;
#define NOTIFY_DONE 0
#define SYS_OFF_MODE_RESTART 3
#define dev_emerg(...) (++errors)
struct device { void *of_node; };
struct sys_off_data { void *cb_data; const char *cmd; };
struct sprd_adi_data {
 bool psci_restart_prepare;
 int (*restart)(struct sys_off_data *);
};
struct sprd_adi { struct device *dev;const struct sprd_adi_data *data; };
static int reads,writes,errors,read_fail,write_fail,bad_readback;
static int properties,property_error,property_value,sys_calls,legacy_calls,register_error;
static u32 reg_value;
static int legacy_callback(struct sys_off_data *data) { (void)data;return 0; }
static int sprd_adi_read(struct sprd_adi *s,u32 reg,u32 *out) {
 (void)s;assert(reg==0x21d4);reads++;
 if(read_fail==reads)return -EIO;
 *out=reg_value^((bad_readback && reads==2)?1:0);return 0;
}
static int sprd_adi_write(struct sprd_adi *s,u32 reg,u32 value) {
 (void)s;assert(reg==0x21d4);writes++;
 if(write_fail)return -EBUSY;
 reg_value=value;return 0;
}
static int of_property_read_u32(void *node,const char *name,u32 *value) {
 assert(node && !strcmp(name,"sprd,psci-reboot"));properties++;
 if(property_error)return property_error;
 *value=property_value;return 0;
}
static int devm_register_sys_off_handler(struct device *dev,int mode,int priority,
 int (*callback)(struct sys_off_data *),void *data) {
 assert(dev && data && callback);
 assert(mode==SYS_OFF_MODE_RESTART && priority==130 && priority>129);
 sys_calls++;return register_error;
}
static int devm_register_restart_handler(struct device *dev,
 int (*callback)(struct sys_off_data *),void *data) {
 assert(dev && data && callback==legacy_callback);legacy_calls++;return register_error;
}
@@DEFINITIONS@@
@@HELPERS@@
static void reset(void) {
 reads=writes=errors=read_fail=write_fail=bad_readback=0;
 properties=property_error=sys_calls=legacy_calls=register_error=0;
 property_value=1;reg_value=0xabcd;
}
int main(void) {
 struct device dev={(void*)1};struct sprd_adi_data config={true,0};
 struct sprd_adi s={&dev,&config};struct sys_off_data event={&s,0};
 const struct {const char *cmd;u32 mode;} cases[]={
  {0,0x40},{"",0x40},{"unknown",0x40},{"recovery",0x20},{"recovery-extra",0x20},
  {"bootloader",0x30},{"alarm",0x50},{"fastsleep",0x60},{"panic",0x80},
  {"special",0x70},{"cftreboot",0x90},{"autodloader",0xa0},{"iqmode",0xb0},
  {"sprdisk",0xc0},{"tospanic",0x02},{"factorytest",0xe0}
 };
 for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);i++) {
  reset();event.cmd=cases[i].cmd;
  assert(sprd_adi_prepare_psci_restart(&event)==NOTIFY_DONE);
  assert(reg_value==(0xab00|cases[i].mode));
  assert(reads==2 && writes==1 && !errors);
 }
 for(unsigned i=2;i<=4;i+=2) {
  reset();reg_value=0xab00|i;event.cmd=0;
  assert(sprd_adi_prepare_psci_restart(&event)==NOTIFY_DONE);
  assert(reg_value==(0xab00|i) && reads==1 && !writes && !errors);
 }
 reset();read_fail=1;assert(!sprd_adi_prepare_psci_restart(&event));
 assert(!writes && reads==1 && errors==1 && reg_value==0xabcd);
 reset();write_fail=1;assert(!sprd_adi_prepare_psci_restart(&event));
 assert(writes==1 && reads==1 && errors==1 && reg_value==0xabcd);
 reset();read_fail=2;assert(!sprd_adi_prepare_psci_restart(&event));
 assert(writes==1 && reads==2 && errors==1);
 reset();bad_readback=1;assert(!sprd_adi_prepare_psci_restart(&event));assert(errors==1);
 reset();assert(!sprd_adi_register_restart(&s));assert(sys_calls==1 && !legacy_calls);
 reset();register_error=-EBUSY;assert(sprd_adi_register_restart(&s)==-EBUSY);
 reset();property_error=-EINVAL;assert(!sprd_adi_register_restart(&s));assert(!sys_calls && !legacy_calls);
 reset();property_value=0;assert(!sprd_adi_register_restart(&s));assert(!sys_calls);
 reset();property_value=2;assert(!sprd_adi_register_restart(&s));assert(!sys_calls);
 reset();config.psci_restart_prepare=false;assert(!sprd_adi_register_restart(&s));
 assert(!properties && !sys_calls && !legacy_calls);
 reset();config.restart=legacy_callback;assert(!sprd_adi_register_restart(&s));
 assert(!properties && !sys_calls && legacy_calls==1);
 return 0;
}
'''.replace('@@DEFINITIONS@@', definitions).replace('@@HELPERS@@', helpers)
        with tempfile.TemporaryDirectory(prefix='pro-restart-') as temp:
            directory = Path(temp)
            (directory/'test.c').write_text(source)
            result = subprocess.run(['gcc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                     str(directory/'test.c'), '-o', str(directory/'test')],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(directory/'test')], check=True, timeout=5)

    def test_platform_and_psci_ownership(self):
        text = DRIVER.read_text()
        self.assertEqual(text.count('.psci_restart_prepare = true'), 1)
        block = text.split('static struct sprd_adi_data ums9632_data = {', 1)[1].split('};', 1)[0]
        self.assertIn('.psci_restart_prepare = true', block)
        prepare = function(text, 'sprd_adi_prepare_psci_restart')
        self.assertNotIn('REG_WDG_', prepare)
        self.assertNotIn('SYSTEM_OFF', prepare.split('/* Preparation only.')[0])
        psci = TOP/'devices/u30pro/native/kernel/ums9632/overlay/drivers/firmware/psci/psci.c'
        self.assertRegex(psci.read_text(), r'psci_sys_reset_nb\s*=\s*\{[^}]*\.priority\s*=\s*129')
        probe = function(text, 'sprd_adi_probe')
        self.assertIn('sprd_adi_register_restart(sadi)', probe)


if __name__ == '__main__':
    unittest.main()
