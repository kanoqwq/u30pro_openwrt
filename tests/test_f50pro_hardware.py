"""F50 Pro data-host policy and no-op/configured key actions, no hardware."""
import json
import re
import subprocess
from pathlib import Path
from helpers import TOP,ShellTest

KEY=TOP/'devices/f50pro/overlay/opt/mu300/bin/f50pro-key-action'
SETTINGS=TOP/'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/buttons'

class Hardware(ShellTest):
    def setUp(self):
        super().setUp()
        self.root=self.tmp/'root';(self.root/'etc/mu300').mkdir(parents=True)
        (self.root/'etc/mu300/model').write_text('f50pro\n')
        self.run=self.tmp/'run';self.run.mkdir();(self.run/'mu300-data-sim-actual').write_text('1\n')
        self.stub('uci', '''case "$2" in get) cat "$STUBLOG/${3##*.}" 2>/dev/null;; set) n=${3%%=*}; printf '%s' "${3#*=}" > "$STUBLOG/${n##*.}";; commit|revert) :;; esac''')
        self.stub('jsonfilter', '''exec python3 -c 'import json,sys,re; d=json.load(sys.stdin); k=sys.argv[-1][2:]; m=re.fullmatch(r"(\\w+)\\[(\\d+)\\]",k); print(d[m[1]][int(m[2])] if m else d[k])' "$@"''')
        self.stub('mu300-physical-sim', "echo '{\"logical_cards\":[0,4]}'")
        for name in ('mu300-u30pro-sim','mu300-wifi-band','mu300-at'):
            self.stub(name,'echo "$0 $*" >> "$STUBLOG/actions"')
    def env(self,**extra):
        return super().env(**dict(dict(MU300_SYSROOT=self.root,MU300_RUN=self.run,MU300_BIN=self.stubs),**extra))
    def test_default_button_does_nothing_for_short_and_long(self):
        for shell in self.each_shell():
            for kind in ('short','long'):
                r=self.script(shell,KEY,kind);self.assertEqual(r.returncode,0,r.stderr)
        self.assertFalse((self.tmp/'actions').exists())
    def test_configured_data_key_uses_current_source_of_other_logical_stack(self):
        for shell in self.each_shell():
            (self.tmp/'f50pro_button_short').write_text('data-switch')
            (self.tmp/'actions').unlink(missing_ok=True)
            r=self.script(shell,KEY,'short');self.assertEqual(r.returncode,0,r.stderr)
            self.assertIn('mu300-u30pro-sim apply 0',(self.tmp/'actions').read_text())
            self.assertNotIn('mu300-at',(self.tmp/'actions').read_text())
    def test_settings_allowlist_and_non_f50_isolation(self):
        for shell in self.each_shell():
            r=self.script(shell,SETTINGS,'get');self.assertEqual(json.loads(r.stdout)['short'],'none')
            (self.tmp/'f50pro_button_short').write_text('poweroff;echo unsafe')
            r=self.script(shell,KEY,'short');self.assertNotEqual(r.returncode,0)
            (self.tmp/'f50pro_button_short').unlink()
            (self.root/'etc/mu300/model').write_text('u30pro\n')
            self.assertFalse(json.loads(self.script(shell,SETTINGS,'get').stdout)['supported'])
            self.assertNotEqual(self.script(shell,KEY,'short').returncode,0)
            (self.root/'etc/mu300/model').write_text('f50pro\n')
        self.assertFalse((self.tmp/'actions').exists())
    def test_real_kernel_external_host_predicate_requires_external_vbus(self):
        source=(TOP/'devices/u30pro/native/kernel/ums9632/overlay/drivers/unisoc_platform/usb/musb/musb_sprd.c').read_text()
        fn=re.search(r'static bool external_host_requested\([^}]+\}',source).group()
        code='#include <stdbool.h>\n#include <assert.h>\n'+fn+'\nint main(void){'
        for policy,ground,vbus,want in [(0,0,0,0),(0,0,1,0),(0,1,0,0),(0,1,1,1),(1,0,0,0),(1,0,1,1),(1,1,0,0),(1,1,1,1),(2,0,0,0),(2,0,1,0),(2,1,0,0),(2,1,1,0)]:
            code+=f'assert(external_host_requested({policy},{ground},{vbus})=={want});'
        code+='}'
        path=self.tmp/'host.c';path.write_text(code)
        subprocess.run(['clang','-Wall','-Wextra','-Werror',str(path),'-o',str(self.tmp/'host')],check=True)
        subprocess.run([self.tmp/'host'],check=True)

    def test_role_and_controller_enable_share_data_policy_without_changing_legacy_id(self):
        source=(TOP/'devices/u30pro/native/kernel/ums9632/overlay/drivers/unisoc_platform/usb/musb/musb_sprd.c').read_text()
        predicate=re.search(r'static bool external_host_requested\([^}]+\}',source).group()
        helper=re.search(r'static bool data_host_requested\([^}]+\}',source).group()
        # Actual production helper: host+sink must work with ID floating,
        # while the battery product retains grounded-ID even before VBUS.
        code='''#include <stdbool.h>
#include <assert.h>
#define READ_ONCE(x) (x)
#define MUSB_ID_GROUND 0
static bool external;
static bool sprd_ums9632_external_power_only(void){return external;}
struct sprd_glue {unsigned int external_data_policy; int id_state; bool vbus_active;};
'''+predicate+'\n'+helper+'''
int main(void){struct sprd_glue g={1,1,true};
external=true;assert(data_host_requested(&g));
g.vbus_active=false;assert(!data_host_requested(&g));
g.id_state=0;assert(!data_host_requested(&g));
g.vbus_active=true;g.external_data_policy=2;assert(!data_host_requested(&g));
external=false;assert(data_host_requested(&g));
g.vbus_active=false;assert(data_host_requested(&g));
g.id_state=1;assert(!data_host_requested(&g));}
'''
        path=self.tmp/'data-role.c';path.write_text(code)
        subprocess.run(['clang','-Wall','-Wextra','-Werror',str(path),'-o',str(self.tmp/'data-role')],check=True)
        subprocess.run([self.tmp/'data-role'],check=True)
        enable=source[source.index('static void sprd_musb_enable('):source.index('static void sprd_musb_disable(')]
        self.assertIn('data_host_requested(glue)',enable)

    def test_real_pd_callback_never_sources_vbus_for_external_power_product(self):
        source=(TOP/'devices/u30pro/native/kernel/ums9632/overlay/drivers/unisoc_platform/sprd_charger/power_delivery/sc27xx_pd.c').read_text()
        start=source.index('static int sc27xx_pd_set_vbus(')
        callback=source[start:source.index('\nstatic int sc27xx_pd_get_vbus(',start)]
        mocks=r'''
#include <stdbool.h>
#include <assert.h>
#include <errno.h>
#define NULL ((void*)0)
static int external=1,enabled=0,enables=0,disables=0,waits=0;
struct sc27xx_pd {int lock; bool vbus_on,charge_on; void *vbus,*dev;};
struct tcpc_dev {struct sc27xx_pd *pd;};
#define tcpc_to_sc27xx_pd(x) ((x)->pd)
#define mutex_lock(x) ((void)(x))
#define mutex_unlock(x) ((void)(x))
#define sprd_pd_log(...) ((void)0)
#define dev_info(...) ((void)0)
#define dev_err(...) ((void)0)
#define IS_ERR(x) (!(x))
static bool sprd_ums9632_external_power_only(void){return external;}
static void *devm_regulator_get_optional(void *d,const char *n){(void)d;(void)n;return &enabled;}
static int regulator_is_enabled(void *r){assert(r);return enabled;}
static int regulator_enable(void *r){assert(r);enables++;enabled=1;return 0;}
static int regulator_disable(void *r){assert(r);disables++;enabled=0;return 0;}
static void sc27xx_pd_wait_for_i2c_set_vbus(struct sc27xx_pd *p){(void)p;waits++;}
'''
        main=r'''
int main(void){struct sc27xx_pd p={0};struct tcpc_dev d={&p};
assert(sc27xx_pd_set_vbus(&d,1,0)==-EOPNOTSUPP);
assert(sc27xx_pd_set_vbus(&d,0,1)==0 && p.charge_on);
assert(!enables&&!disables&&!waits&&!p.vbus);
external=0;assert(!sc27xx_pd_set_vbus(&d,1,0));assert(enables==1&&enabled&&p.vbus_on);
assert(!sc27xx_pd_set_vbus(&d,0,0));assert(disables==1&&!enabled&&!p.vbus_on);}
'''
        path=self.tmp/'pd.c';path.write_text(mocks+callback+main)
        subprocess.run(['clang','-Wall','-Wextra','-Werror',str(path),'-o',str(self.tmp/'pd')],check=True)
        subprocess.run([self.tmp/'pd'],check=True)

if __name__=='__main__':
    import unittest
    unittest.main(verbosity=2)
