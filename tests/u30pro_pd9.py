"""Exercise the production PD admission/request code without hardware."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

TOP = Path(__file__).resolve().parents[1]
OVERLAY = TOP/'devices/u30pro/native/kernel/ums9632/overlay'


def function(source, name):
    match = re.search(r'^static int '+name+r'\([^;{}]*\)\s*\{', source, re.M)
    assert match
    start = source.index('{', match.start())
    end, depth = start+1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[match.start():end]


class PD9(unittest.TestCase):
    def test_real_iio_charge_voltage_return_contract(self):
        source = (OVERLAY/'drivers/power/supply/u30pro-ump965x-fgu.c').read_text()
        program = r'''
#include <assert.h>
#include <errno.h>
struct ump_fgu { void *charge; };
static int result, millivolts;
static int iio_read_channel_processed(void *ch, int *mv) {
 (void)ch; if (result >= 0) *mv=millivolts; return result;
}
FUNCTION
int main(void) {
 struct ump_fgu f={0}; int uv;
 result=1; millivolts=4474; uv=-1;
 assert(!ump_charge_voltage_uv(&f,&uv) && uv==4474000);
 result=0; millivolts=9000;
 assert(!ump_charge_voltage_uv(&f,&uv) && uv==9000000);
 result=-EIO; uv=-1;
 assert(ump_charge_voltage_uv(&f,&uv)==-EIO && uv==-1);
 result=1; millivolts=20001;
 assert(ump_charge_voltage_uv(&f,&uv)==-ERANGE && uv==-1);
 millivolts=-1;
 assert(ump_charge_voltage_uv(&f,&uv)==-ERANGE && uv==-1);
 return 0;
}
'''.replace('FUNCTION', function(source, 'ump_charge_voltage_uv'))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'iio.c'
            path.write_text(program)
            binary = Path(tmp)/'iio'
            subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', str(path), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_adapters_roles_preparation_and_restore(self):
        policy = (OVERLAY/'include/linux/power/u30pro-pd9.h').read_text()
        source = (OVERLAY/'drivers/unisoc_platform/sprd_charger/power_delivery/sprd_tcpm.c').read_text()
        program = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
#include <string.h>
#include "u30pro-pmic-typec.h"
#define min(a,b) ((a)<(b)?(a):(b))
#define SPRD_PDO_FIXED(v,a,f) (((v)/50<<10)|((a)/10)|(f))
#define SPRD_PDO_TYPE_FIXED 0
#define sprd_pdo_type(p) ((p)>>30)
#define sprd_pdo_fixed_voltage(p) ((((p)>>10)&1023)*50)
#define SNK_READY 1
#define SNK_NEGOTIATE_CAPABILITIES 2
#define SNK_NEGOTIATE_PPS_CAPABILITIES 3
#define TYPEC_SINK 0
#define TYPEC_SOURCE 1
#define TYPEC_DEVICE 0
#define TYPEC_HOST 1
#define POWER_SUPPLY_PROP_VOLTAGE_MAX 1
#define sprd_tcpm_log(...) ((void)0)
static unsigned long jiffies;
#define time_before(a,b) ((long)((a)-(b))<0)
#define msecs_to_jiffies(v) (v)
struct mutex {int unused;};
struct power_supply {int unused;};
union power_supply_propval {int intval;};
struct sprd_tcpm_port {
 struct mutex lock;
 int state,pwr_role,data_role,nr_source_caps,nr_snk_pdo,pps_status;
 bool explicit_contract,vbus_source,power_role_swap,data_role_swap;
 bool u30pro_pd9_active,u30pro_pd9_attempted;
 unsigned long u30pro_pd9_exit_retry;
 unsigned supply_voltage;
 unsigned source_caps[7],snk_pdo[7],snk_default_pdo[7];
 unsigned operating_snk_mw,operating_snk_default_mw;
 struct {unsigned req_out_volt,req_op_curr;} pps_data;
};
static int locks,prepares,queued,prepare_error,have_charger=1;
static int have_config=1,pps_allowed=1,fchg_allowed=1;
static unsigned fixed_budget=18000000;
static struct power_supply supply;
struct device_node {int unused;};
static struct device_node config;
static struct device_node *of_find_node_by_path(const char *p){(void)p;return have_config?&config:0;}
static int of_property_read_bool(struct device_node *p,const char *key){(void)p;return !strcmp(key,"sprd,support-pd-pps")?pps_allowed:fchg_allowed;}
static int of_property_read_u32(struct device_node *p,const char *key,uint32_t *value){(void)p;(void)key;*value=fixed_budget;return 0;}
static void of_node_put(struct device_node *p){(void)p;}
typedef uint32_t u32;
static void mutex_lock(struct mutex *m){(void)m;locks++;}
static void mutex_unlock(struct mutex *m){(void)m;locks--;}
static struct power_supply *power_supply_get_by_name(const char *name){(void)name;return have_charger?&supply:0;}
static void power_supply_put(struct power_supply *s){(void)s;}
static int power_supply_set_property(struct power_supply *s,int prop,const union power_supply_propval *v){
 (void)s;assert(prop==POWER_SUPPLY_PROP_VOLTAGE_MAX&&v->intval==9000000);
 assert(locks==1);prepares++;return prepare_error;
}
static void sprd_tcpm_set_state(struct sprd_tcpm_port *p,int state,int delay){
 assert(p->u30pro_pd9_active||state==SNK_NEGOTIATE_CAPABILITIES);
 assert(prepares&&!prepare_error&&delay==0);p->state=state;queued++;
}
POLICY
FUNCTION
static struct sprd_tcpm_port fresh(void){
 struct sprd_tcpm_port p={.state=SNK_READY,.explicit_contract=true,.nr_source_caps=2,
  .operating_snk_default_mw=10000};
 p.source_caps[0]=p.snk_default_pdo[0]=SPRD_PDO_FIXED(5000,3000,0);
 have_config=pps_allowed=fchg_allowed=1;fixed_budget=18000000;
 p.source_caps[1]=SPRD_PDO_FIXED(9000,3000,0);prepares=queued=prepare_error=0;have_charger=1;
 return p;
}
int main(void){
 struct sprd_tcpm_port p;
 struct u30pro_pd9_choice c;
 assert(u30pro_pmic_typec_base(0x300,0xa001,0x9651)==0x380);
 assert(u30pro_pmic_typec_base(0x380,0xa001,0x9651)==0x380);
 assert(u30pro_pmic_typec_base(0x380,0xb000,0x9360)==0x300);
 assert(u30pro_pmic_typec_base(0x300,0xa000,0x9651)==0x300);
 assert(u30pro_pmic_typec_base(0x300,0xa001,0x9650)==0x300);
 assert(u30pro_pmic_typec_base(0x400,0,0)==0x400);
 p=fresh();assert(!sprd_tcpm_u30pro_voltage_limit(&p,9000000));
 assert(prepares==1&&queued==1&&p.state==SNK_NEGOTIATE_CAPABILITIES);
 assert(p.u30pro_pd9_active&&p.u30pro_pd9_attempted&&p.operating_snk_mw==18000);
 assert(p.snk_pdo[1]==SPRD_PDO_FIXED(9000,2000,0));
 p.state=SNK_READY;assert(!sprd_tcpm_u30pro_voltage_limit(&p,9000000));assert(queued==1);
 assert(!sprd_tcpm_u30pro_voltage_limit(&p,5000000));
 assert(!p.u30pro_pd9_active&&!p.u30pro_pd9_attempted&&p.nr_snk_pdo==1);
 assert(p.snk_pdo[0]==p.snk_default_pdo[0]&&p.operating_snk_mw==10000);
 p.state=SNK_READY;p.supply_voltage=9000; /* Adapter rejected the first 5 V request. */
 assert(!sprd_tcpm_u30pro_voltage_limit(&p,5000000));assert(queued==2);
 jiffies=5000;assert(!sprd_tcpm_u30pro_voltage_limit(&p,5000000));assert(queued==3);
 p.state=SNK_READY;p.supply_voltage=5000;
 assert(!sprd_tcpm_u30pro_voltage_limit(&p,5000000));assert(queued==3);
 p=fresh();p.source_caps[1]=(3U<<30)|(110U<<17)|(33U<<8)|60;
 assert(!sprd_tcpm_u30pro_voltage_limit(&p,9000000));
 assert(p.state==SNK_NEGOTIATE_PPS_CAPABILITIES&&p.pps_data.req_out_volt==9000&&p.pps_data.req_op_curr==3000);
 p=fresh();p.source_caps[1]=SPRD_PDO_FIXED(9000,1500,0);
 assert(!sprd_tcpm_u30pro_voltage_limit(&p,9000000));assert(!prepares&&!queued);
 p=fresh();p.data_role=TYPEC_HOST;assert(!sprd_tcpm_u30pro_voltage_limit(&p,9000000));assert(!prepares&&!queued);
 p=fresh();p.pwr_role=TYPEC_SOURCE;assert(sprd_tcpm_u30pro_voltage_limit(&p,9000000)==-EAGAIN);assert(!prepares&&!queued);
 p=fresh();p.vbus_source=true;assert(sprd_tcpm_u30pro_voltage_limit(&p,9000000)==-EAGAIN);assert(!prepares);
 p=fresh();p.power_role_swap=true;assert(sprd_tcpm_u30pro_voltage_limit(&p,9000000)==-EAGAIN);assert(!prepares);
 p=fresh();p.data_role_swap=true;assert(sprd_tcpm_u30pro_voltage_limit(&p,9000000)==-EAGAIN);assert(!prepares);
 p=fresh();p.explicit_contract=false;assert(sprd_tcpm_u30pro_voltage_limit(&p,9000000)==-EAGAIN);assert(!prepares);
 p=fresh();p.source_caps[0]|=1U<<26;assert(!sprd_tcpm_u30pro_voltage_limit(&p,9000000));assert(!prepares&&!queued);
 p=fresh();p.source_caps[0]|=1U<<29;assert(!sprd_tcpm_u30pro_voltage_limit(&p,9000000));assert(!prepares&&!queued);
 p=fresh();prepare_error=-EPERM;assert(sprd_tcpm_u30pro_voltage_limit(&p,9000000)==-EPERM);assert(!queued&&!p.u30pro_pd9_active);
 p=fresh();have_charger=0;assert(sprd_tcpm_u30pro_voltage_limit(&p,9000000)==-ENODEV);assert(!prepares&&!queued);
 p=fresh();p.source_caps[1]=SPRD_PDO_FIXED(12000,3000,0);assert(!sprd_tcpm_u30pro_voltage_limit(&p,9000000));assert(!prepares&&!queued);
 p=fresh();p.source_caps[1]=(3U<<30)|(87U<<17)|(33U<<8)|60;
 c=u30pro_pd9_select(p.source_caps,2,1);assert(!c.kind);
 p.source_caps[1]=(3U<<30)|(110U<<17)|(100U<<8)|60;
 c=u30pro_pd9_select(p.source_caps,2,1);assert(!c.kind);
 p.source_caps[1]=(3U<<30)|(110U<<17)|(33U<<8)|10;
 c=u30pro_pd9_select(p.source_caps,2,1);assert(!c.kind);
 p=fresh();pps_allowed=0;p.source_caps[2]=(3U<<30)|(110U<<17)|(33U<<8)|60;p.nr_source_caps=3;
 assert(!sprd_tcpm_u30pro_voltage_limit(&p,9000000));assert(p.state==SNK_NEGOTIATE_CAPABILITIES);
 p=fresh();p.source_caps[2]=(3U<<30)|(110U<<17)|(33U<<8)|60;p.nr_source_caps=3;
 assert(!sprd_tcpm_u30pro_voltage_limit(&p,9000000));assert(p.state==SNK_NEGOTIATE_PPS_CAPABILITIES);
 p=fresh();fchg_allowed=0;assert(sprd_tcpm_u30pro_voltage_limit(&p,9000000)==-EOPNOTSUPP);assert(!prepares&&!queued);
 p=fresh();have_config=0;assert(sprd_tcpm_u30pro_voltage_limit(&p,9000000)==-ENODEV);assert(!prepares&&!queued);
 p=fresh();p.source_caps[1]=(3U<<30)|(210U<<17)|(33U<<8)|20;
 assert(sprd_tcpm_u30pro_voltage_limit(&p,9000000)==-EOPNOTSUPP);assert(!prepares&&!queued);
 assert(!locks);
 assert(!u30pro_pd9_start_eligible(3519999,2000000,2000000,1000000,4100000));
 assert(u30pro_pd9_start_eligible(3520000,0,1200000,1000000,4100000));
 assert(!u30pro_pd9_start_eligible(4100000,1199999,3000000,1000000,4100000));
 assert(u30pro_pd9_start_eligible(4200000,1200000,0,0,4100000));
 assert(!u30pro_pd9_stop_eligible(3400000,1000000,6500000));
 assert(u30pro_pd9_stop_eligible(3399999,1000000,6500000));
 assert(u30pro_pd9_stop_eligible(3400000,999999,6500000));
 assert(u30pro_pd9_stop_eligible(3400000,1000000,6499999));
 return 0;
}
'''
        program = program.replace('POLICY',policy).replace('FUNCTION',function(source,'sprd_tcpm_u30pro_voltage_limit'))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);(path/'test.c').write_text(program)
            subprocess.run(['cc','-Wall','-Wextra','-Werror','-std=gnu11',
                            '-I',str(OVERLAY/'include/linux/usb'),
                            str(path/'test.c'),'-o',str(path/'test')],check=True)
            subprocess.run([str(path/'test')],check=True,timeout=5)


if __name__ == '__main__':unittest.main(verbosity=2)
