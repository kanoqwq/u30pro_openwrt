/* Production OF selection/loader are inserted by u30pro_charge_profile.py. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <limits.h>
typedef uint32_t u32;
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define DIV_ROUND_CLOSEST(n,d) (((n)+(d)/2)/(d))
#define min_t(t,a,b) ((t)(a)<(t)(b)?(t)(a):(t)(b))
struct device_node { int kind, index; };
struct device { struct device_node *of_node; };
struct device_node owner={0,0},chosen={1,0},batteries[]={{2,0},{2,1}};
static int refs, missing=-1, incompatible=-1, broken_index=-1, count=2;
static int bad_cv, bad_jeita, have_ref;
static u32 ref_mv=1850, targets[]={47,121}, max_cv[]={4400000,4200000};
static const char *bootargs="bat.id=164";
static struct device_node *take(struct device_node *p) { if(p)refs++;return p; }
static struct device_node *of_find_node_by_path(const char *p) {
 assert(!strcmp(p,"/chosen"));return take(&chosen);
}
static void of_node_put(struct device_node *p) {if(p){refs--;assert(refs>=0);}}
static int of_property_read_string(struct device_node *p,const char *key,const char **out) {
 assert(p==&chosen&&!strcmp(key,"bootargs"));*out=bootargs;return 0;
}
static struct device_node *of_parse_phandle(struct device_node *p,const char *key,int n) {
 assert(p==&owner&&n==0);
 if(!strcmp(key,"monitored-battery-0"))return missing==0?NULL:take(&batteries[0]);
 if(!strcmp(key,"monitored-battery-1"))return missing==1?NULL:take(&batteries[1]);
 return NULL;
}
static int of_device_is_compatible(struct device_node *p,const char *compat) {
 assert(!strcmp(compat,"simple-battery"));return p->index!=incompatible;
}
static int kstrtoint(const char *s,unsigned base,int *out) {
 char *end;errno=0;long v=strtol(s,&end,base);
 if(errno||end==s||*end||v<INT_MIN||v>INT_MAX)return -EINVAL;
 *out=v;return 0;
}
static int of_property_read_u32(struct device_node *p,const char *key,u32 *v) {
 if(!strcmp(key,"batt-id-pullup-kohm"))return -ENOENT;
 if(!strcmp(key,"batt-id-ref-vol")) {if(!have_ref)return -ENOENT;*v=ref_mv;return 0;}
 if(!strcmp(key,"constant-charge-voltage-max-microvolt")) {
  if(bad_cv==1)return -ENOENT;
  *v=bad_cv==2?4700000:max_cv[p->index];return 0;
 }
 if(!strcmp(key,"fast-charge-threshold-microvolt")){*v=4100000;return 0;}
 assert(0);return -EINVAL;
}
static int of_property_count_u32_elems(struct device_node *p,const char *key) {
 (void)p;
 if(!strcmp(key,"batt-id-list"))return count;
 assert(!strcmp(key,"dcp-jeita-temp-table")||!strcmp(key,"fchg-jeita-temp-table"));return bad_jeita==1?7:20;
}
static int of_property_read_u32_index(struct device_node *p,const char *key,int i,u32 *v) {
 (void)p;
 static const u32 rows[]={1000,1030,0,4400000,1050,1080,490000,4400000,
  1150,1180,1400000,4400000,1450,1420,3400000,4400000,1500,1480,2400000,4100000};
 if(!strcmp(key,"batt-id-list")) {if(i==broken_index)return -EIO;*v=targets[i];return 0;}
 assert((!strcmp(key,"dcp-jeita-temp-table")||!strcmp(key,"fchg-jeita-temp-table"))&&i>=0&&i<20);
 *v=rows[i];if(bad_jeita==2&&i==4)*v=999;return 0;
}
static int of_property_read_u32_array(struct device_node *p,const char *key,u32 *v,int n) {
 assert(n==2&&strstr(key,"charge-")&&strstr(key,"-current-microamp"));
 if(!strcmp(key,"charge-fchg-current-microamp")) {
  v[0]=p->index?1500000:3400000;v[1]=p->index?1200000:2000000;return 0;
 }
 v[0]=p->index?1500000:2000000;v[1]=p->index?2000000:3000000;return 0;
}
struct sgm_jeita { int t_up,t_rec;u32 ichg,cv; };
struct u30_sgm {
 struct device *dev;int battery_index,battery_id_mv;
 u32 cv_max_uv,tbl_ichg[4],tbl_iin[4],fchg_iin,fchg_ichg,fchg_ocv_max;
 struct sgm_jeita jeita[8],fchg_jeita[8];int fchg_jeita_n;
 int jeita_n;bool policy_on;
};
/* PROFILE_HELPER */
/* TABLE_LOADER */
static void check_profile(int expected,int mv) {
 int index=-1,id=-1;
 struct device_node *p=u30pro_battery_profile(&owner,&index,&id);
 assert(!IS_ERR(p)&&index==expected&&id==mv&&p==&batteries[expected]);
 of_node_put(p);assert(!refs);
 struct device d={&owner};struct u30_sgm s={.dev=&d};
 assert(sgm_load_tables(&s)==0&&s.policy_on&&s.battery_index==expected);
 assert(s.cv_max_uv==max_cv[expected]&&s.tbl_iin[0]==(expected?2000000:3000000));
 assert(s.fchg_iin==(expected?1200000:2000000));
 assert(s.fchg_ichg==(expected?1500000:3000000));
 assert(s.jeita_n==5&&s.jeita[4].t_up==500&&s.jeita[4].t_rec==480&&!refs);
}
static void check_error(int expected) {
 int index=-1,id=-1;
 struct device_node *p=u30pro_battery_profile(&owner,&index,&id);
 assert(IS_ERR(p)&&PTR_ERR(p)==expected&&index==-1&&id==-1&&!refs);
}
int main(int argc,char **argv) {
 assert(argc==2);
 switch(atoi(argv[1])) {
 case 1:check_profile(0,164);break;
 case 2:bootargs="xbat.id=164 bat.id=376 more=1";check_profile(1,376);break;
 case 3:bootargs="bat.id=800";check_error(-ENODATA);break;
 case 4:
  bootargs="no.id=1";check_error(-ENODATA);
  bootargs="bat.id=";check_error(-EINVAL);
  bootargs="bat.id=-1";check_error(-EINVAL);
  bootargs="bat.id=1850";check_error(-EINVAL);
  bootargs="bat.id=oops";check_error(-EINVAL);
  bootargs="bat.id=12345678901234567890";check_error(-EINVAL);break;
 case 5:
  bootargs="bat.id=376";missing=1;check_error(-EINVAL);missing=-1;
  incompatible=1;check_error(-EINVAL);incompatible=-1;
  missing=0;check_error(-EINVAL);break;
 case 6:
  count=0;check_error(-EINVAL);count=17;check_error(-EINVAL);count=2;
  broken_index=0;check_error(-EIO);broken_index=-1;
  have_ref=1;ref_mv=0;check_error(-EINVAL);ref_mv=6000;check_error(-EINVAL);break;
 case 7:targets[0]=0;bootargs="bat.id=0";check_profile(0,0);break;
 case 8: {
  struct device d={&owner};struct u30_sgm s={.dev=&d};
  for(int i=1;i<=2;i++){bad_cv=i;assert(sgm_load_tables(&s)<0&&!s.policy_on&&!refs);}
  bad_cv=0;
  for(int i=1;i<=2;i++){bad_jeita=i;assert(sgm_load_tables(&s)<0&&!s.policy_on&&!refs);}
  break;
 }
 default:assert(0);
 }
 assert(!refs);return 0;
}
