/* Production tuning/work functions with fake registers and deterministic time. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <unistd.h>
typedef uint32_t u32; typedef uint8_t u8; typedef long long ktime_t;
#define HZ 1000UL
#define USEC_PER_MSEC 1000
#define MMC_TIMING_UHS_SDR104 6
#define SDHCI_USE_ADMA 1
#define SDHCI_USE_SDMA 2
#define SDHCI_RESET_CMD 1
#define SDHCI_RESET_DATA 2
#define SDHCI_SPRD_REG_32_DLL_CFG 0
#define SDHCI_SPRD_REG_32_DLL_DLY 1
#define SDHCI_SPRD_REG_32_DLL_STS0 2
#define SDHCI_PRESENT_STATE 3
#define SDHCI_DOING_READ 1
#define SDHCI_SPRD_CPST_EN (15U<<24)
#define SDHCI_SPRD_CMD_DLY_MASK (255U<<8)
#define SDHCI_SPRD_POSRD_DLY_MASK (255U<<16)
#define GFP_KERNEL 0
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define container_of(ptr,type,member) ((type *)((char *)(ptr)-offsetof(type,member)))
#define READ_ONCE(x) __atomic_load_n(&(x),__ATOMIC_RELAXED)
#define WRITE_ONCE(x,v) __atomic_store_n(&(x),(v),__ATOMIC_RELAXED)
#define xchg(p,v) __atomic_exchange_n((p),(v),__ATOMIC_RELAXED)
#define time_before(a,b) ((long)((a)-(b))<0)
#define time_after(a,b) time_before(b,a)
#define time_after_eq(a,b) (!time_before(a,b))
#define msecs_to_jiffies(n) ((unsigned long)(n))
#define dev_info(...) ((void)0)
#define dev_warn(...) ((void)0)
#define mmc_dev(m) ((void *)(m))
struct mutex { pthread_mutex_t value; };
static void mutex_init(struct mutex *m) { assert(!pthread_mutex_init(&m->value,0)); }
static void mutex_lock(struct mutex *m) { assert(!pthread_mutex_lock(&m->value)); }
static void mutex_unlock(struct mutex *m) { assert(!pthread_mutex_unlock(&m->value)); }
typedef pthread_mutex_t spinlock_t;
#define spin_lock_init(m) assert(!pthread_mutex_init(m,0))
#define spin_lock_irqsave(m,f) do { f=0; assert(!pthread_mutex_lock(m)); } while(0)
#define spin_unlock_irqrestore(m,f) do { (void)(f);assert(!pthread_mutex_unlock(m)); } while(0)
struct work_struct { void (*fn)(struct work_struct *); bool queued,spawned;pthread_t thread; };
static int queued,cancelled,async_work,thermal_block,thermal_entered;
static void *work_thread(void *arg) { struct work_struct *w=arg;WRITE_ONCE(w->queued,false);w->fn(w);return 0; }
#define INIT_WORK(w,f) do { (w)->fn=f;(w)->queued=false;(w)->spawned=false; } while(0)
static void schedule_work(struct work_struct *w) {
 if(!w->queued){w->queued=true;queued++;if(async_work){w->spawned=true;assert(!pthread_create(&w->thread,0,work_thread,w));}}
}
static void cancel_work_sync(struct work_struct *w) {
 if(w->spawned){assert(!pthread_join(w->thread,0));w->spawned=false;}
 w->queued=false;cancelled++;
}
static void run_work(struct work_struct *w) { assert(w->queued);w->queued=false;w->fn(w); }
struct mmc_host { struct sdhci_host *private; struct { unsigned timing,clock; } ios; bool doing_retune,need_retune,can_retune;unsigned actual_clock; };
struct sdhci_host { struct mmc_host *mmc;struct sdhci_sprd_host *private;unsigned flags;u32 regs[4]; };
/* PRODUCTION_STATE */
struct sdhci_sprd_host { bool sdio_host;u32 phy_delay[12];struct sdhci_sprd_sdio_tune tune; };
#define TO_SPRD_HOST(h) ((h)->private)
static struct sdhci_host *mmc_priv(struct mmc_host *m) { return m->private; }
#undef abs
#define abs(v) ((v)<0?-(v):(v))
static unsigned long jiffies;
static long long now_us;
static bool alloc_fail,all_fail,slow;
static unsigned window_start=8,window_width=60,tuning_calls,retunes;
static ktime_t ktime_get(void) { return now_us; }
static ktime_t ktime_add_ms(ktime_t t,int ms) { return t+ms*1000; }
static int ktime_compare(ktime_t a,ktime_t b) { return (a>b)-(a<b); }
static unsigned ktime_us_delta(ktime_t a,ktime_t b) { return a-b; }
static void *kcalloc(size_t n,size_t z,int g) { (void)g;return alloc_fail?0:calloc(n,z); }
#define kfree free
static u32 sdhci_readl(struct sdhci_host *h,int reg) { return h->regs[reg]; }
static void sdhci_writel(struct sdhci_host *h,u32 value,int reg) { h->regs[reg]=value; }
static void sdhci_reset(struct sdhci_host *h,int v) { (void)h;(void)v; }
#define read_poll_timeout(fn,v,cond,sleep,timeout,atomic,h,r) ((v)=fn(h,r),(void)(cond),0)
static int mmc_send_tuning(struct mmc_host *m,u32 opcode,void *unused) {
 (void)opcode;(void)unused;tuning_calls++;now_us+=slow?150000:10;
 struct sdhci_host *h=m->private;unsigned period=(h->regs[2]&255)*2;
 unsigned step=((h->regs[1]>>8)&255)%period;
 return all_fail || (step+period-window_start)%period>=window_width ? -EILSEQ:0;
}
static int sdhci_execute_tuning(struct mmc_host *m,u32 v) { (void)m;(void)v;return 19; }
static void mmc_retune_needed(struct mmc_host *m) { m->need_retune=true;retunes++; }
struct thermal_zone_device { int index; };
static struct thermal_zone_device zones[2]={{0},{1}};
static int temperatures[2]={35000,40000},thermal_reads,settle,unstable;
#define IS_ERR(p) ((intptr_t)(p)<0)
static struct thermal_zone_device *thermal_zone_get_zone_by_name(const char *n) { return &zones[!strcmp(n,"soc-thmzone")]; }
static int thermal_zone_get_temp(struct thermal_zone_device *t,int *out) {
 if(READ_ONCE(thermal_block)){WRITE_ONCE(thermal_entered,1);while(READ_ONCE(thermal_block))usleep(1000);}
 thermal_reads++;*out=temperatures[t->index];
 if(settle>0){*out+=settle*5000;settle--;}
 if(unstable){*out+=(thermal_reads&1)?1000:0;}
 return 0;
}
static unsigned int sdio_retune_mc=10000,sdio_retune_s=1800,sdio_retune_defer_ms=10000;
/* PRODUCTION_FUNCTIONS */
static void setup(struct sdhci_host *h,struct sdhci_sprd_host *p,struct mmc_host *m) {
 memset(h,0,sizeof(*h));memset(p,0,sizeof(*p));memset(m,0,sizeof(*m));
 h->private=p;h->mmc=m;m->private=h;p->sdio_host=true;
 m->can_retune=true;m->ios.timing=6;m->ios.clock=208000000;m->actual_clock=204800000;
 h->regs[0]=0xa7000011;h->regs[1]=0x44332211;h->regs[2]=40;
 p->phy_delay[6]=h->regs[1];h->flags=SDHCI_USE_ADMA;
 sdhci_sprd_sdio_tune_init(h);
}
static void *stop_thread(void *arg) { sdhci_sprd_sdio_tune_pause(arg,true);return 0; }
int main(void) {
 struct sdhci_host h,h2;struct sdhci_sprd_host p,p2;struct mmc_host m,m2;
 setup(&h,&p,&m);setup(&h2,&p2,&m2);
 unsigned cfg=h.regs[0],dly=h.regs[1];
 alloc_fail=true;assert(sdhci_sprd_sdio_execute_tuning(&m,19)==-ENOMEM);
 assert(h.regs[0]==cfg && h.regs[1]==dly && h.flags==SDHCI_USE_ADMA && !p.tune.valid);alloc_fail=false;
 h.regs[2]=0;assert(sdhci_sprd_sdio_execute_tuning(&m,19)==-EIO);assert(h.regs[0]==cfg);h.regs[2]=40;
 assert(!sdhci_sprd_sdio_execute_tuning(&m,19));assert(p.tune.valid && p.tune.width==60 && p.tune.hz==204800000);
 assert(!p2.tune.valid && thermal_reads==0);
 m.doing_retune=true;unsigned before=tuning_calls;
 assert(!sdhci_sprd_sdio_execute_tuning(&m,19));assert(p.tune.kept==1 && tuning_calls-before<=12);
 window_start=25;window_width=45;before=tuning_calls;
 assert(!sdhci_sprd_sdio_execute_tuning(&m,19));assert(tuning_calls-before>12 && p.tune.start==25);
 h.regs[2]=39;assert(!sdhci_sprd_sdio_execute_tuning(&m,19));assert(p.tune.dll_cnt==78);
 cfg=h.regs[0];dly=h.regs[1];unsigned width=p.tune.width;
 all_fail=true;slow=true;before=tuning_calls;
 assert(sdhci_sprd_sdio_execute_tuning(&m,19)==-EIO);
 assert(tuning_calls-before<=p.tune.dll_cnt*3/2+12 && h.regs[0]==cfg && h.regs[1]==dly && p.tune.width==width && h.flags==SDHCI_USE_ADMA);
 all_fail=false;window_start=36;window_width=30;before=tuning_calls;long long began=now_us;
 assert(!sdhci_sprd_sdio_execute_tuning(&m,19));
 assert(tuning_calls-before>12 && now_us-began>150000 && p.tune.width==30);
 cfg=h.regs[0];dly=h.regs[1];all_fail=true;slow=false;assert(sdhci_sprd_sdio_execute_tuning(&m,19)==-EIO);assert(h.regs[0]==cfg && h.regs[1]==dly);all_fail=false;
 assert(!p.tune.work.queued);jiffies=5001;settle=5;
 before=queued;m.can_retune=false;sdhci_sprd_sdio_activity(&m);assert(queued==before);
 m.can_retune=true;m.ios.timing=0;sdhci_sprd_sdio_activity(&m);assert(queued==before);m.ios.timing=6;
 sdhci_sprd_sdio_activity(&m);assert(p.tune.work.queued);run_work(&p.tune.work);
 assert(!p.tune.work.queued && p.tune.t_now[0]==35000 && thermal_reads>=8);
 temperatures[0]=46000;jiffies+=5000;sdhci_sprd_sdio_activity(&m);run_work(&p.tune.work);
 assert(p.tune.pending==SDIO_TUNE_TEMP);unsigned r=retunes;
 for(int n=0;n<5;n++){jiffies++;sdhci_sprd_sdio_activity(&m);}assert(retunes==r);
 jiffies+=10000;sdhci_sprd_sdio_activity(&m);assert(retunes==r+1 && p.tune.want==SDIO_TUNE_TEMP);
 assert(!sdhci_sprd_sdio_execute_tuning(&m,19));assert(p.tune.count[SDIO_TUNE_TEMP]==1);
 jiffies+=1800001;sdhci_sprd_sdio_activity(&m);run_work(&p.tune.work);assert(p.tune.pending==SDIO_TUNE_PERIOD);
 jiffies+=21;sdhci_sprd_sdio_activity(&m);assert(p.tune.want==SDIO_TUNE_PERIOD);
 unstable=1;jiffies+=5000;sdhci_sprd_sdio_activity(&m);run_work(&p.tune.work);assert(p.tune.t_now[0]==SDIO_T_NONE);unstable=0;
 sdhci_sprd_sdio_tune_pause(&h,false);assert(cancelled==1 && p.tune.suspended);
 jiffies+=10000;before=queued;sdhci_sprd_sdio_activity(&m);assert(queued==before);
 sdhci_sprd_sdio_tune_resume(&h);sdhci_sprd_sdio_activity(&m);assert(p.tune.work.queued);
 sdhci_sprd_sdio_tune_pause(&h,true);assert(!p.tune.work.queued && !p.tune.active);
 sdhci_sprd_sdio_tune_resume(&h);sdhci_sprd_sdio_activity(&m);assert(!p.tune.work.queued && !p.tune.active);
 assert(p2.tune.active && !p2.tune.valid && !p2.tune.work.queued);
 /* A worker already holds its own host while removal starts. Stop must
  * prevent requeue and join the blocked worker before the host can be freed. */
 assert(!sdhci_sprd_sdio_execute_tuning(&m2,19));
 jiffies+=5000;async_work=1;thermal_block=1;sdhci_sprd_sdio_activity(&m2);
 for(int n=0;!READ_ONCE(thermal_entered) && n<1000;n++)usleep(1000);
 assert(READ_ONCE(thermal_entered));pthread_t stopper;assert(!pthread_create(&stopper,0,stop_thread,&h2));
 for(int n=0;READ_ONCE(p2.tune.active) && n<1000;n++)usleep(1000);
 assert(!READ_ONCE(p2.tune.active));before=queued;sdhci_sprd_sdio_activity(&m2);assert(queued==before);
 WRITE_ONCE(thermal_block,0);assert(!pthread_join(stopper,0));
 assert(!p2.tune.work.spawned && !p2.tune.work.queued);
 puts("Production tuning/window/rollback, complete bounded probes, event/idle/suspend/remove and per-host isolation passed");
 return 0;
}
