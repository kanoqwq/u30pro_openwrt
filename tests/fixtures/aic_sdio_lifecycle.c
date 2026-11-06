/* Exercise actual bus init/deinit with failed allocation and each worker start. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define AICWF_SDIO_SUPPORT
#define CONFIG_OOB
#define CMD_BUF_MAX 1536
#define GFP_KERNEL 0
#define LOGINFO 0
#define AICWFDBG(...) ((void)0)
#define txrx_err(...) ((void)0)
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define IS_ERR(p) ((uintptr_t)(p)>=(uintptr_t)-4095)
struct device { int unused; };
struct task_struct { bool live;int kind; };
struct rwnx_hw { int unused; };
struct aicwf_bus;
struct aic_sdio_dev {
    struct rwnx_hw *rwnx_hw;struct aicwf_bus *bus_if;
    void *rx_priv;bool oob_enable;int wslock;
};
struct aicwf_bus {
    struct { struct aic_sdio_dev *sdio; } bus_priv;
    void *cmd_buf;int bustx_trgg,busrx_trgg,busirq_trgg;
    struct task_struct *bustx_thread,*busrx_thread,*busirq_thread;
};
static struct {bool enabled;} platform={true}, *g_rwnx_plat=&platform;
static struct aicwf_bus bus;
static struct aic_sdio_dev sdio;
static struct device dev;
static struct rwnx_hw hw;
static struct task_struct tasks[3];
static int created,fail_at,allocated,platform_frees;
static bool stopped,fail_alloc;
static void *kzalloc(size_t size,int flags) {
    if(fail_alloc)return NULL;
    void *p=calloc(1,size);assert(p);allocated++;return p;
}
static void kfree(void *p) { if(p){allocated--;free(p);} }
static void *dev_get_drvdata(struct device *d) {assert(d==&dev);return &bus;}
static void aicwf_bus_stop(struct aicwf_bus *b) {assert(b==&bus);stopped=true;}
static void init_completion(int *p) {*p=0;}
static void complete_all(int *p) {*p=1;}
static void spin_lock_init(int *p) {*p=1;}
static int sdio_bustx_thread(void *p) {return 0;}
static int sdio_busrx_thread(void *p) {return 0;}
static int sdio_busirq_thread(void *p) {return 0;}
static struct task_struct *kthread_run(int(*fn)(void*),void *arg,const char *name) {
    if(++created==fail_at)return ERR_PTR(-EAGAIN);
    int kind=fn==sdio_bustx_thread?0:fn==sdio_busrx_thread?1:2;
    assert(!tasks[kind].live);tasks[kind].kind=kind;tasks[kind].live=true;
    return &tasks[kind];
}
static int kthread_stop(struct task_struct *t) {
    assert(stopped && !IS_ERR(t) && t->live);
    int *done=t->kind==0?&bus.bustx_trgg:t->kind==1?&bus.busrx_trgg:&bus.busirq_trgg;
    assert(*done==1);t->live=false;return 0;
}
static void rwnx_platform_deinit(struct rwnx_hw *h) {
    assert(h==&hw && stopped);
    for(int i=0;i<3;i++)assert(!tasks[i].live);
    assert(platform_frees++==0);
}
/* PRODUCTION_FUNCTIONS */
static void setup(void) {
    assert(!allocated);memset(&bus,0,sizeof(bus));memset(&sdio,0,sizeof(sdio));
    memset(tasks,0,sizeof(tasks));created=fail_at=platform_frees=0;
    stopped=fail_alloc=false;bus.bus_priv.sdio=&sdio;sdio.bus_if=&bus;
    sdio.rwnx_hw=&hw;sdio.oob_enable=true;
}
static void cleaned(void) {
    assert(!allocated && !bus.cmd_buf && !bus.bustx_thread && !bus.busrx_thread && !bus.busirq_thread);
    for(int i=0;i<3;i++)assert(!tasks[i].live);
    assert(platform_frees==1 && !sdio.rwnx_hw);
    aicwf_bus_deinit(&dev);assert(platform_frees==1); /* nested failure cleanup */
}
int main(void) {
    for(int i=1;i<=3;i++) {
        setup();fail_at=i;assert(aicwf_bus_init(0,&dev)==-EAGAIN);
        assert(created==i);cleaned();
    }
    setup();fail_alloc=true;assert(aicwf_bus_init(0,&dev)==-ENOMEM);assert(!created);cleaned();
    for(int oob=0;oob<=1;oob++) {
        setup();sdio.oob_enable=oob;assert(!aicwf_bus_init(0,&dev));
        assert(created==(oob?3:2) && allocated==1 && !stopped);
        aicwf_bus_deinit(&dev);cleaned();
    }
    aicwf_bus_deinit(NULL);return 0;
}
