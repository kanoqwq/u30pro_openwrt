"""Run production SGM policy with synthetic PHY/PD/temperature/register inputs."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

TOP = Path(__file__).resolve().parents[1]
DRIVER = TOP/'devices/u30pro/native/kernel/ums9632/overlay/drivers/power/supply'
SOURCE = (DRIVER/'u30pro-sgm41513.c').read_text()


def declaration(pattern):
    match = re.search(pattern, SOURCE, re.M)
    assert match, pattern
    start = SOURCE.index('{', match.start())
    pos, depth = start + 1, 1
    while depth:
        depth += (SOURCE[pos] == '{') - (SOURCE[pos] == '}')
        pos += 1
    return SOURCE[match.start():pos] + '\n'


@unittest.skipUnless(os.name == 'posix', 'host C compiler')
class ChargeSources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(); cls.addClassCleanup(cls.temp.cleanup)
        base = Path(cls.temp.name)
        model = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <limits.h>
#include <string.h>
#include <stdlib.h>
#include <errno.h>
#include "u30pro-sgm41513-values.h"
#include "u30pro-pd9.h"
typedef uint32_t u32; typedef uint8_t u8;
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define BIT(x) (1U<<(x))
#define SGM_STATUS 8
#define SGM_CONTROL 1
#define SGM_OTG BIT(5)
#define min_t(t,a,b) ((t)(a)<(t)(b)?(t)(a):(t)(b))
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
enum {UNKNOWN_TYPE,SDP_TYPE,DCP_TYPE,CDP_TYPE,ACA_TYPE};
enum {USB_CHARGER_DEFAULT,USB_CHARGER_PRESENT,USB_CHARGER_ABSENT};
enum {POWER_SUPPLY_USB_TYPE_UNKNOWN,POWER_SUPPLY_USB_TYPE_SDP,
 POWER_SUPPLY_USB_TYPE_DCP,POWER_SUPPLY_USB_TYPE_CDP,POWER_SUPPLY_USB_TYPE_C,
 POWER_SUPPLY_USB_TYPE_PD,POWER_SUPPLY_USB_TYPE_PD_PPS};
enum power_supply_property {POWER_SUPPLY_PROP_ONLINE,POWER_SUPPLY_PROP_VOLTAGE_NOW,
 POWER_SUPPLY_PROP_CURRENT_MAX,POWER_SUPPLY_PROP_TEMP,POWER_SUPPLY_PROP_VOLTAGE_MAX,
 POWER_SUPPLY_PROP_CHARGE_BEHAVIOUR,POWER_SUPPLY_PROP_INPUT_CURRENT_LIMIT,
 POWER_SUPPLY_PROP_CONSTANT_CHARGE_CURRENT,POWER_SUPPLY_PROP_USB_TYPE,
 POWER_SUPPLY_PROP_VOLTAGE_OCV,POWER_SUPPLY_PROP_CURRENT_NOW,
 POWER_SUPPLY_PROP_CONSTANT_CHARGE_VOLTAGE};
enum {POWER_SUPPLY_CHARGE_BEHAVIOUR_AUTO,POWER_SUPPLY_CHARGE_BEHAVIOUR_INHIBIT_CHARGE};
enum {NOTIFY_DONE,NOTIFY_OK};
struct mutex {int unused;};struct work_struct {int unused;};
struct delayed_work {int unused;};struct notifier_block {int unused;};
struct power_supply_desc {int unused;};struct regulator_desc {int unused;};
struct usb_phy {int chg_state,chg_type;};
struct power_supply {int kind;};union power_supply_propval {int intval;};
STRUCTS
static unsigned regs[16],reads,writes,queued,notifications,locks,cancelled;
static int pd_online,pd_uv=5000000,pd_ua=3000000,temp=320,have_temp=1;
static struct power_supply pd={1},battery={2};
static bool battery_present=true;
static int pd_usb_type=POWER_SUPPLY_USB_TYPE_PD;
static int ocv=3800000,ibat=1500000,vbat=3900000,vbus=5000000;
static struct u30_sgm *fixture_charger;
static int fail_read_reg=-1;
static bool fail_ovp_write;
static void *power_supply_get_drvdata(struct power_supply *s){(void)s;return fixture_charger;}
static int sgm_read(struct u30_sgm *s,int reg){(void)s;reads++;return reg==fail_read_reg?-EIO:(int)regs[reg];}
static int sgm_update_reg(struct u30_sgm *s,int reg,int mask,int value){
 (void)s;writes++;regs[reg]=(regs[reg]&~mask)|value;
 return reg==6&&fail_ovp_write?-EIO:0;
}
static struct power_supply *power_supply_get_by_name(const char *n){
 return strstr(n,"tcpm")?&pd:(have_temp?&battery:NULL);
}
static int power_supply_get_property(struct power_supply *s,int p,union power_supply_propval *v){
 if(s->kind==2) {
  if(p==POWER_SUPPLY_PROP_VOLTAGE_OCV)v->intval=ocv;
  else if(p==POWER_SUPPLY_PROP_CURRENT_NOW)v->intval=ibat;
  else if(p==POWER_SUPPLY_PROP_VOLTAGE_NOW)v->intval=vbat;
  else if(p==POWER_SUPPLY_PROP_CONSTANT_CHARGE_VOLTAGE)v->intval=vbus;
  else v->intval=temp;
 }
 else if(p==POWER_SUPPLY_PROP_ONLINE)v->intval=pd_online;
 else if(p==POWER_SUPPLY_PROP_VOLTAGE_NOW||p==POWER_SUPPLY_PROP_VOLTAGE_MAX)v->intval=pd_uv;
 else if(p==POWER_SUPPLY_PROP_USB_TYPE)v->intval=pd_usb_type;
 else v->intval=pd_ua;
 return 0;
}
static void power_supply_put(struct power_supply *s){(void)s;}
static int power_supply_set_property(struct power_supply *s,int p,union power_supply_propval *v){
 (void)s;(void)p;(void)v;return 0;
}
static void power_supply_changed(struct power_supply *s){(void)s;notifications++;}
static void mutex_lock(struct mutex *m){(void)m;locks++;}
static void mutex_unlock(struct mutex *m){(void)m;locks--;}
static void schedule_work(struct work_struct *w){(void)w;queued++;}
static int system_wq;
static unsigned long jiffies;
#define msecs_to_jiffies(v) (v)
#define time_before(a,b) ((long)((a)-(b))<0)
static void mod_delayed_work(int q,struct delayed_work *w,int d){(void)q;(void)w;assert(d==500);}
static void cancel_work_sync(struct work_struct *w){(void)w;cancelled++;}
static void cancel_delayed_work_sync(struct delayed_work *w){(void)w;cancelled++;}
FUNCTIONS
int main(int argc,char **argv){
 assert(argc==2);struct usb_phy phy={USB_CHARGER_PRESENT,SDP_TYPE};
 struct u30_sgm s={.usb_phy=&phy,.psy=&battery,.policy_on=true,.boot_vreg=0x88,.cv_max_uv=4400000,
  .jeita_n=1,.jeita_idx=-1,.tbl_iin={500000,3000000,1500000,1000000},
  .tbl_ichg={700000,2000000,1500000,1000000}};
 s.jeita[0]=(struct sgm_jeita){.t_up=1000,.t_rec=970,.ichg=3000000,.cv=4400000};
 regs[SGM_STATUS]=0x34; // Chip PSEL still says SDP even when PMIC finds DCP.
 fixture_charger=&s;
 switch(atoi(argv[1])){
 case 1:
  sgm_policy(&s);assert(s.pol_iin==500000 && s.pol_ichg==700000 && s.pol_type==0);
  phy.chg_type=DCP_TYPE;sgm_policy(&s);
  assert(s.pol_iin==3000000 && s.pol_ichg==2000000 && sgm_usb_type(&s)==POWER_SUPPLY_USB_TYPE_DCP);
  assert(sgm41513_iin_ua(regs[0])==3000000);
  phy.chg_type=CDP_TYPE;sgm_policy(&s);assert(s.pol_iin==1500000 && s.pol_ichg==1500000);
  assert(sgm_usb_type(&s)==POWER_SUPPLY_USB_TYPE_CDP);
  phy.chg_type=SDP_TYPE;sgm_policy(&s);assert(s.pol_iin==500000);
  assert(sgm_usb_type(&s)==POWER_SUPPLY_USB_TYPE_SDP);break;
 case 2:
  phy.chg_type=UNKNOWN_TYPE;sgm_policy(&s);assert(s.pol_type==3 && s.pol_iin==1000000);
  phy.chg_type=DCP_TYPE;phy.chg_state=USB_CHARGER_ABSENT;
  assert(sgm_usb_type(&s)==POWER_SUPPLY_USB_TYPE_UNKNOWN);
  regs[SGM_STATUS]=0;sgm_policy(&s);assert(writes==4);
  regs[SGM_STATUS]=0x34;regs[SGM_CONTROL]=SGM_OTG;sgm_policy(&s);assert(writes==4);break;
 case 3:
  pd_online=1;sgm_policy(&s);assert(s.pol_pd_ma==3000 && s.pol_iin==3000000 && s.pol_ichg==3000000);
  s.user_iin=1200000;s.user_ichg=900000;sgm_policy(&s);
  assert(s.pol_iin==1200000 && s.pol_ichg==900000);
  pd_online=0;s.user_iin=s.user_ichg=0;sgm_policy(&s);assert(s.pol_iin==500000);break;
 case 4:
  phy.chg_type=DCP_TYPE;s.behaviour=POWER_SUPPLY_CHARGE_BEHAVIOUR_INHIBIT_CHARGE;
  sgm_policy(&s);assert(!s.pol_charge && !(regs[1]&BIT(4)) && s.pol_cv==4400000);
  s.behaviour=POWER_SUPPLY_CHARGE_BEHAVIOUR_AUTO;have_temp=0;
  sgm_policy(&s);assert(s.pol_ichg==1000000);
  have_temp=1;temp=1100;sgm_policy(&s);assert(!s.pol_charge && !s.pol_ichg);break;
 case 5:
  phy.chg_type=DCP_TYPE;
  assert(sgm_source_notify(&s.usb_nb,3000,&phy)==NOTIFY_OK);
  assert(queued==1 && !reads && !writes && !locks);
  sgm_source_work(&s.source_work);assert(s.pol_iin==3000000 && notifications==1 && !locks);
  assert(sgm_source_notify(&s.usb_nb,0,NULL)==NOTIFY_DONE && queued==1);
  s.stopping=true;assert(sgm_source_notify(&s.usb_nb,0,&phy)==NOTIFY_DONE && queued==1);
  sgm_source_work(&s.source_work);assert(notifications==1);break;
 case 6:
  sgm_cancel_poll(&s);assert(s.stopping && cancelled==2);
  assert(sgm_source_notify(&s.usb_nb,0,&phy)==NOTIFY_DONE && !queued);break;
 case 7:
  for (unsigned uv=3856000;uv<=4624000;uv+=1000) {
   unsigned code=sgm_cv_code(uv),actual=sgm41513_cv_uv(code<<3);
   assert(actual<=uv);
   for (unsigned candidate=0;candidate<=24;candidate++)
    assert(sgm41513_cv_uv(candidate<<3)>uv || sgm41513_cv_uv(candidate<<3)<=actual);
  }
  for (int code=0;code<=24;code++)
   assert(sgm_cv_code(sgm41513_cv_uv(code<<3))==code);
  break;
 case 8:
  phy.chg_type=DCP_TYPE;
  s.boot_vreg=0x38; // Previous warm CV was 4.08 V; current stock profile is 4.4 V.
  sgm_policy(&s);assert(s.pol_cv==4400000 && sgm41513_cv_uv(regs[4])==4400000);
  s.cv_max_uv=4200000;sgm_policy(&s);
  assert(s.pol_cv==4200000 && sgm41513_cv_uv(regs[4])<=4200000);
  s.cv_max_uv=4350000;sgm_policy(&s);
  assert(sgm41513_cv_uv(regs[4])==4350000);
  break;
 case 9:
  phy.chg_type=DCP_TYPE;s.jeita_n=5;
  s.jeita[0]=(struct sgm_jeita){0,30,0,4400000};
  s.jeita[1]=(struct sgm_jeita){50,80,490000,4400000};
  s.jeita[2]=(struct sgm_jeita){150,180,1400000,4400000};
  s.jeita[3]=(struct sgm_jeita){450,420,3400000,4400000};
  s.jeita[4]=(struct sgm_jeita){500,480,2400000,4100000};
  temp=460;sgm_policy(&s);assert(s.jeita_idx==4 && s.pol_cv==4100000);
  temp=430;sgm_policy(&s);assert(s.jeita_idx==4 && s.pol_cv==4100000);
  temp=420;sgm_policy(&s);assert(s.jeita_idx==3 && s.pol_cv==4400000);
  temp=501;sgm_policy(&s);assert(s.jeita_idx==5 && !s.pol_charge);
  temp=481;sgm_policy(&s);assert(s.jeita_idx==5 && !s.pol_charge);
  temp=480;sgm_policy(&s);assert(s.jeita_idx==4 && s.pol_charge && s.pol_cv==4100000);
  temp=330;sgm_policy(&s);assert(s.jeita_idx==3 && s.pol_cv==4400000);
  temp=-1;sgm_policy(&s);assert(s.jeita_idx==0 && !s.pol_charge);
  temp=29;sgm_policy(&s);assert(s.jeita_idx==0 && !s.pol_charge);
  temp=30;sgm_policy(&s);assert(s.jeita_idx==1 && s.pol_ichg==490000);
  temp=79;sgm_policy(&s);assert(s.jeita_idx==1);
  temp=80;sgm_policy(&s);assert(s.jeita_idx==2 && s.pol_ichg==1400000);
  temp=179;sgm_policy(&s);assert(s.jeita_idx==2);
  temp=180;sgm_policy(&s);assert(s.jeita_idx==3);
  temp=149;sgm_policy(&s);assert(s.jeita_idx==2);
  s.jeita_idx=5;temp=440;sgm_policy(&s);
  assert(s.jeita_idx==4 && s.pol_charge); // Cross two boundaries, only one recovered.
  break;
 case 10: {
  union power_supply_propval request={.intval=9000000};
  phy.chg_type=DCP_TYPE;s.fchg_iin=2000000;s.fchg_ichg=2000000;
  s.fchg_ocv_max=4100000;s.pd_poll_ms=15000;s.fchg_jeita[0]=s.jeita[0];s.fchg_jeita_n=1;
  s.pd_wanted=true;
  sgm_policy(&s);regs[6]=0x58;
  assert(!sgm_set_property(&battery,POWER_SUPPLY_PROP_VOLTAGE_MAX,&request));
  assert(s.pd_ovp_ready&&s.pd_saved_ovp==0x40&&regs[6]==0x98);
  assert(sgm41513_iin_ua(regs[0])==1500000);
  pd_online=2;pd_uv=9000000;pd_ua=2000000;vbus=9000000;sgm_policy(&s);
  assert(s.pol_iin==2000000&&s.pol_ichg==2000000&&s.pol_cv==4400000);
  pd_usb_type=POWER_SUPPLY_USB_TYPE_C;pd_uv=5000000;pd_ua=500000;vbus=5000000;sgm_policy(&s);
  assert(s.pol_iin==3000000); /* Preserve the already-fixed A-C DCP path. */
  pd_usb_type=POWER_SUPPLY_USB_TYPE_PD;sgm_policy(&s);assert(s.pol_iin==500000);
  s.user_iin=100000;sgm_policy(&s);
  assert(!sgm_set_property(&battery,POWER_SUPPLY_PROP_VOLTAGE_MAX,&request));
  assert(sgm41513_iin_ua(regs[0])==100000);
  battery_present=false;unsigned before=writes;
  assert(sgm_set_property(&battery,POWER_SUPPLY_PROP_VOLTAGE_MAX,&request)==-EPERM);
  assert(writes==before);battery_present=true;
  regs[SGM_CONTROL]|=SGM_OTG;before=writes;
  assert(sgm_set_property(&battery,POWER_SUPPLY_PROP_VOLTAGE_MAX,&request)==-EBUSY);
  assert(writes==before);regs[SGM_CONTROL]&=~SGM_OTG;
  s.behaviour=POWER_SUPPLY_CHARGE_BEHAVIOUR_INHIBIT_CHARGE;
  assert(sgm_set_property(&battery,POWER_SUPPLY_PROP_VOLTAGE_MAX,&request)==-EPERM);
  s.behaviour=POWER_SUPPLY_CHARGE_BEHAVIOUR_AUTO;s.pd_ovp_ready=false;
  fail_read_reg=6;before=writes;
  assert(sgm_set_property(&battery,POWER_SUPPLY_PROP_VOLTAGE_MAX,&request)==-EIO);
  assert(writes==before&&!s.pd_ovp_ready);fail_read_reg=-1;
  s.pd_ovp_touched=s.pd_ovp_ready=true;s.pd_saved_ovp=0x40;regs[6]=0x98;
  pd_online=0;sgm_request_pd_voltage(&s);assert(regs[6]==0x58&&!s.pd_ovp_ready);
  break;
 }
 case 11:
  phy.chg_type=DCP_TYPE;s.fchg_iin=s.fchg_ichg=2000000;s.fchg_ocv_max=4100000;s.pd_poll_ms=15000;
  s.fchg_jeita[0]=s.jeita[0];s.fchg_jeita_n=1;
  sgm_policy(&s);sgm_pd_check(&s);assert(!s.pd_wanted&&s.pd_enable_count==1);
  sgm_pd_check(&s);assert(!s.pd_wanted&&s.pd_enable_count==2);
  sgm_pd_check(&s);assert(s.pd_wanted&&s.pd_enable_count==3);
  pd_online=2;pd_uv=vbus=9000000;pd_ua=2000000;s.pd_ovp_ready=true;
  sgm_policy(&s);sgm_pd_check(&s);assert(s.pd_fast_active&&s.pd_wanted);
  ibat=999999;sgm_policy(&s);sgm_pd_check(&s);assert(s.pd_wanted&&s.pd_disable_count==0);
  jiffies=15000;sgm_pd_check(&s);assert(s.pd_wanted&&s.pd_disable_count==1);
  jiffies=19999;sgm_pd_check(&s);assert(s.pd_wanted&&s.pd_disable_count==1);
  jiffies=20000;sgm_pd_check(&s);assert(!s.pd_wanted&&s.pd_disable_count==0);
  ocv=4200000;sgm_policy(&s);sgm_pd_check(&s);assert(!s.pd_wanted);
  s.pd_wanted=true;s.behaviour=POWER_SUPPLY_CHARGE_BEHAVIOUR_INHIBIT_CHARGE;
  sgm_policy(&s);sgm_pd_check(&s);assert(!s.pd_wanted&&!s.pol_charge);
  break;
 case 12:
  phy.chg_type=DCP_TYPE;s.fchg_iin=s.fchg_ichg=2000000;s.fchg_ocv_max=4100000;s.pd_poll_ms=15000;
  s.fchg_jeita[0]=(struct sgm_jeita){1000,970,600000,4100000};s.fchg_jeita_n=1;
  s.pd_wanted=s.pd_ovp_ready=true;pd_online=2;pd_uv=vbus=9000000;pd_ua=2000000;
  sgm_policy(&s);assert(s.pd_fast_active&&s.pol_cv==4100000&&s.pol_ichg==600000);
  assert(sgm_pd9_allowed(&s)); /* No invented warm-CV gate; stock low-current exit applies. */
  s.pd_wanted=false;pd_uv=vbus=5000000;sgm_policy(&s);
  assert(!s.pd_fast_active&&s.pol_cv==4400000);
  break;
 case 13: {
  union power_supply_propval request={.intval=9000000};
  phy.chg_type=DCP_TYPE;s.fchg_iin=s.fchg_ichg=2000000;s.fchg_ocv_max=4100000;
  s.pd_poll_ms=15000;s.fchg_jeita[0]=s.jeita[0];s.fchg_jeita_n=1;
  s.pd_wanted=true;sgm_policy(&s);regs[6]=0x58;fail_ovp_write=true;
  assert(sgm_set_property(&battery,POWER_SUPPLY_PROP_VOLTAGE_MAX,&request)==-EIO);
  assert(s.pd_ovp_touched&&!s.pd_ovp_ready&&regs[6]==0x98);
  fail_ovp_write=false;s.pd_wanted=false;pd_online=1;pd_uv=5000000;vbus=9000000;
  sgm_request_pd_voltage(&s);assert(regs[6]==0x98&&s.pd_ovp_touched);
  vbus=5000000;sgm_request_pd_voltage(&s);
  assert(regs[6]==0x58&&!s.pd_ovp_touched&&!s.pd_ovp_ready);
  s.pd_ovp_touched=s.pd_ovp_ready=true;regs[6]=0x98;
  pd_online=0;have_temp=0; /* An unreadable ADC is not proof that VBUS is low. */
  sgm_request_pd_voltage(&s);assert(regs[6]==0x98&&s.pd_ovp_ready);
  have_temp=1;sgm_request_pd_voltage(&s);assert(regs[6]==0x58&&!s.pd_ovp_ready);
  break;
 }
 default:assert(0);
 }
 return 0;
}
'''
        structs = '\n'.join(declaration(r'^struct '+name+r'\s*\{')+';'
                            for name in ('sgm_jeita','u30_sgm'))
        functions = '\n'.join(declaration(r'^static (?:int|void) '+name+r'\([^;{}]*\)\s*\{')
            for name in ('sgm_ichg_code','sgm_cv_code','sgm_band','sgm_jeita_band','sgm_source_type',
                         'sgm_usb_type','sgm_policy','sgm_request_pd_voltage','sgm_source_work','sgm_source_notify','sgm_cancel_poll',
                         'sgm_set_property','sgm_pd_check'))
        functions = '\n'.join(declaration(r'^static bool '+name+r'\([^;{}]*\)\s*\{')
                    for name in ('sgm_pd9_allowed','sgm_pd_can_start')) + functions
        (base/'test.c').write_text(model.replace('STRUCTS',structs).replace('FUNCTIONS',functions))
        cls.binary=base/'sources'
        r=subprocess.run(['gcc','-std=gnu11','-O2','-Wall','-Wextra','-Werror','-I',str(DRIVER),
                          '-I',str(TOP/'devices/u30pro/native/kernel/ums9632/overlay/include/linux/power'),
                          str(base/'test.c'),'-o',str(cls.binary)],capture_output=True,text=True)
        if r.returncode:raise RuntimeError(r.stderr)

    def case(self,n):
        r=subprocess.run([str(self.binary),str(n)],capture_output=True,text=True,timeout=5)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)

    def test_bc12_dcp_and_cdp_override_chip_psel_but_sdp_stays_sdp(self):self.case(1)
    def test_unknown_absent_and_otg_never_become_dcp(self):self.case(2)
    def test_pd_and_explicit_user_limits_are_preserved(self):self.case(3)
    def test_bypass_jeita_and_factory_voltage_remain_in_force(self):self.case(4)
    def test_atomic_notification_only_queues_process_context_policy(self):self.case(5)
    def test_shutdown_cancels_both_workers_and_blocks_further_events(self):self.case(6)
    def test_every_cv_code_and_special_4350_value_roundtrip_without_overshoot(self):self.case(7)
    def test_selected_profile_recovers_from_inherited_warm_cv_and_preserves_lower_cv(self):self.case(8)
    def test_stock_jeita_recovery_edges_and_multiband_transitions(self):self.case(9)
    def test_pd9_ovp_current_limits_failures_bypass_otg_and_restore(self):self.case(10)
    def test_stock_start_delay_taper_hysteresis_and_pause(self):self.case(11)
    def test_fast_charge_uses_its_own_selected_stock_jeita_table(self):self.case(12)
    def test_uncertain_ovp_write_and_actual_vbus_guard_cleanup(self):self.case(13)


if __name__=='__main__':unittest.main(verbosity=2)
