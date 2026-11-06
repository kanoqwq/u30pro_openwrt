/* Kernel scheduling shim for the unmodified production queue and packer. */
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <stdatomic.h>
typedef uint8_t u8;
typedef uint32_t u32;
#define GFP_KERNEL 0
#define READ_ONCE(x) __atomic_load_n(&(x), __ATOMIC_ACQUIRE)
#define WRITE_ONCE(x,v) __atomic_store_n(&(x),(v),__ATOMIC_RELEASE)
#define min(a,b) ((a)<(b)?(a):(b))
#define min_t(t,a,b) min((t)(a),(t)(b))
#define round_down(x,a) ((x)/(a)*(a))
#define roundup(x,a) (((x)+(a)-1)/(a)*(a))
#define TXPKT_BLOCKSIZE 512
#define TAIL_LEN 4
#define TX_ALIGNMENT 4
#define DATA_FLOW_CTRL_THRESH 2
#define CMD_TX_TIMEOUT 5000
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
static atomic_int allocs;
static int allocation, fail_at, thread_fail;
static void *kmalloc(size_t size, int flags) {
    if (++allocation == fail_at) return NULL;
    void *p = malloc(size);
    if (p) atomic_fetch_add(&allocs, 1);
    return p;
}
static void *kzalloc(size_t size, int flags) {
    void *p = kmalloc(size, flags);
    if (p) memset(p, 0, size);
    return p;
}
static void kfree(void *p) { if(p) {atomic_fetch_sub(&allocs,1);free(p);} }
typedef pthread_mutex_t spinlock_t;
#define spin_lock_init(p) assert(!pthread_mutex_init((p),NULL))
#define spin_lock_irqsave(p,f) do { (f)=0;assert(!pthread_mutex_lock(p)); } while(0)
#define spin_unlock_irqrestore(p,f) do { (void)(f);assert(!pthread_mutex_unlock(p)); } while(0)
#define spin_lock_bh(p) assert(!pthread_mutex_lock(p))
#define spin_unlock_bh(p) assert(!pthread_mutex_unlock(p))
typedef struct { pthread_mutex_t lock;pthread_cond_t cond; } wait_queue_head_t;
static void init_waitqueue_head(wait_queue_head_t *q) {
    pthread_mutex_init(&q->lock,NULL);pthread_cond_init(&q->cond,NULL);
}
static void wake_up_all(wait_queue_head_t *q) {
    pthread_mutex_lock(&q->lock);pthread_cond_broadcast(&q->cond);pthread_mutex_unlock(&q->lock);
}
/* Shorter fault timeouts in the shim; production uses CMD_TX_TIMEOUT. */
#define msecs_to_jiffies(ms) ((ms)/10)
#define wait_event_timeout(q,condition,ms) ({ \
    struct timespec ts;clock_gettime(CLOCK_REALTIME,&ts); \
    ts.tv_nsec += (long)(ms)*1000000L; \
    ts.tv_sec += ts.tv_nsec/1000000000L;ts.tv_nsec %=1000000000L; \
    long ready;pthread_mutex_lock(&(q).lock); \
    while(!(condition)) { \
        if(pthread_cond_timedwait(&(q).cond,&(q).lock,&ts)==ETIMEDOUT)break; \
    } \
    ready=(condition)?1:0;pthread_mutex_unlock(&(q).lock);ready; })
#define wait_event_interruptible(q,condition) ({ \
    pthread_mutex_lock(&(q).lock); \
    while(!(condition))pthread_cond_wait(&(q).cond,&(q).lock); \
    pthread_mutex_unlock(&(q).lock);0; })
struct task_struct { pthread_t id;atomic_bool stop;int(*fn)(void*);void *arg; };
static _Thread_local struct task_struct *self;
static bool kthread_should_stop(void) { return self && atomic_load(&self->stop); }
static void *entry(void *arg) { self=arg;self->fn(self->arg);return NULL; }
static struct task_struct *kthread_run(int(*fn)(void*),void *arg,const char *name) {
    if(thread_fail)return ERR_PTR(-EAGAIN);
    struct task_struct *t=calloc(1,sizeof(*t));assert(t);t->fn=fn;t->arg=arg;
    assert(!pthread_create(&t->id,NULL,entry,t));return t;
}
static void get_task_struct(struct task_struct *t) { (void)t; }
static void put_task_struct(struct task_struct *t) { free(t); }
static int kthread_stop(struct task_struct *t) {
    atomic_store(&t->stop,true);assert(!pthread_join(t->id,NULL));return 0;
}
struct skb_buff_pool { unsigned int size;u8 *data,*head,*tail,*end;unsigned int len; };
/* PRODUCTION_HEADER */

typedef atomic_int atomic_t;
static int atomic_read(atomic_t *a) { return atomic_load(a); }
static void atomic_set(atomic_t *a,int v) { atomic_store(a,v); }
static void atomic_inc(atomic_t *a) { atomic_fetch_add(a,1); }
static void atomic_dec(atomic_t *a) { atomic_fetch_sub(a,1); }
static atomic_long st_aggr,st_pkts,st_bounds;
#define atomic64_inc(a) atomic_fetch_add((a),1)
#define atomic64_add(v,a) atomic_fetch_add((a),(v))
#define sdio_err(...) ((void)0)
#define txrx_err(...) ((void)0)
struct kernel_param { void *arg; };
static int kstrtoint(const char *s,int base,int *result) {
    char *end;errno=0;long n=strtol(s,&end,base);
    if(errno || end==s || *end || n>INT_MAX || n<INT_MIN)return -EINVAL;
    *result=n;return 0;
}
static int tx_aggr_counter=AICWF_AGGR_MAX;
struct txdesc_api { u8 bytes[24]; };
struct rwnx_hw { void *sw_txhdr_cache; };
struct rwnx_vif { struct rwnx_hw *rwnx_hw; };
struct sw_hdr { unsigned int headroom;struct txdesc_api desc;
                struct rwnx_vif *rwnx_vif;bool need_cfm; };
struct rwnx_txhdr { struct sw_hdr *sw_hdr; };
struct sk_buff { u8 *data;unsigned int len;bool consumed;void *dev; };
static void kmem_cache_free(void *cache,void *p) { free(p); }
static void skb_pull(struct sk_buff *p,unsigned int n) { assert(n<=p->len);p->data+=n;p->len-=n; }
static void consume_skb(struct sk_buff *p) { assert(!p->consumed);p->consumed=true; }
struct frame_queue { struct sk_buff *next; };
struct aic_sdio_dev;
struct aicwf_tx_priv {
    struct aic_sdio_dev *sdiodev;int fw_avail_bufcnt;
    atomic_t aggr_count,tx_pktcnt;struct frame_queue txq;spinlock_t txqlock;
    u8 *head,*tail;struct skb_buff_pool *kmal_buf;struct aicwf_txpipe *tx_pipe;
    void *dev;
};
struct aic_sdio_dev { struct aicwf_tx_priv *tx_priv;void *dev;int chipid; };
#define PRODUCT_ID_AIC8801 0
#define PRODUCT_ID_AIC8800DC 1
#define PRODUCT_ID_AIC8800DW 2
#define PRODUCT_ID_AIC8800D80 3
#define PRODUCT_ID_AIC8800D80X2 4
static struct sk_buff *aicwf_frame_dequeue(struct frame_queue *q) {
    struct sk_buff *p=q->next;q->next=NULL;return p;
}
static unsigned int fc_calls;
static int aicwf_sdio_flow_ctrl(struct aic_sdio_dev *dev) {
    assert(!aicwf_txpipe_drain(dev->tx_priv->tx_pipe));fc_calls++;return 128;
}
static u8 crc8_ponl_107(u8 *p,int len) { return 0; }
static int aicwf_sdio_txpkt(struct aic_sdio_dev *dev,struct skb_buff_pool *pool);
/* PRODUCTION_FUNCTIONS */

struct sink {
    pthread_mutex_t lock;pthread_cond_t cond;bool block,released,entered;
    unsigned int count,expected;int error;bool check_sequence;
    u8 captured[65536];unsigned int captured_len;
};
static void sink_init(struct sink *s) {
    memset(s,0,sizeof(*s));pthread_mutex_init(&s->lock,NULL);pthread_cond_init(&s->cond,NULL);
}
static int send_pool(void *context,struct skb_buff_pool *pool) {
    struct sink *s=context;
    unsigned int n=0;memcpy(&n,pool->data,sizeof(n));
    pthread_mutex_lock(&s->lock);s->entered=true;pthread_cond_broadcast(&s->cond);
    while(s->block && !s->released)pthread_cond_wait(&s->cond,&s->lock);
    if(s->check_sequence)assert(n==s->expected++);
    s->count++;s->captured_len=roundup(pool->len,512);
    assert(s->captured_len<=sizeof(s->captured));
    memcpy(s->captured,pool->data,s->captured_len);
    int error=s->error;pthread_mutex_unlock(&s->lock);
    if(s->check_sequence) {
        usleep(5);unsigned int after=0;memcpy(&after,pool->data,sizeof(after));assert(n==after);
    }
    return error;
}
static struct sink *direct_sink;
static int aicwf_sdio_txpkt(struct aic_sdio_dev *dev,struct skb_buff_pool *pool) {
    return send_pool(direct_sink,pool);
}
static struct skb_buff_pool original(void) {
    struct skb_buff_pool p={.size=1600*32};p.data=malloc(p.size);assert(p.data);
    memset(p.data,0xa5,p.size);p.head=p.tail=p.data;p.end=p.data+p.size;return p;
}
static void enqueue(struct aicwf_txpipe *p,unsigned int value) {
    struct skb_buff_pool *b=p->pool[p->fill];b->len=512;
    memcpy(b->data,&value,sizeof(value));assert(!aicwf_txpipe_submit(p));
}
static void wait_entered(struct sink *s) {
    pthread_mutex_lock(&s->lock);while(!s->entered)pthread_cond_wait(&s->cond,&s->lock);
    pthread_mutex_unlock(&s->lock);
}
static void release_sink(struct sink *s) {
    pthread_mutex_lock(&s->lock);s->released=true;pthread_cond_broadcast(&s->cond);pthread_mutex_unlock(&s->lock);
}
static void order(void) {
    struct skb_buff_pool orig=original();struct sink s;sink_init(&s);s.check_sequence=true;
    struct aicwf_txpipe *p=aicwf_txpipe_create(&orig,&s,send_pool);assert(!IS_ERR(p));
    for(unsigned int i=0;i<5000;i++)enqueue(p,i);
    assert(!aicwf_txpipe_drain(p));assert(s.count==5000);
    aicwf_txpipe_destroy(p);assert(!atomic_load(&allocs));free(orig.data);
}
struct blocked_submit { struct aicwf_txpipe *p;atomic_bool done;int result; };
static void *submitter(void *arg) {
    struct blocked_submit *b=arg;b->result=aicwf_txpipe_submit(b->p);atomic_store(&b->done,true);return NULL;
}
static void blocked(const char *mode) {
    struct skb_buff_pool orig=original();struct sink s;sink_init(&s);s.block=true;
    struct aicwf_txpipe *p=aicwf_txpipe_create(&orig,&s,send_pool);assert(!IS_ERR(p));
    enqueue(p,1);wait_entered(&s);
    struct blocked_submit b={.p=p};pthread_t producer;
    if(strcmp(mode,"drain-timeout")) {
        enqueue(p,2);assert(READ_ONCE(p->queued)==2);
        pthread_create(&producer,NULL,submitter,&b);usleep(20000);assert(!atomic_load(&b.done));
    }
    if(!strcmp(mode,"cancel")) {
        aicwf_txpipe_cancel(p);pthread_join(producer,NULL);assert(b.result==-ESHUTDOWN);
    } else if(!strcmp(mode,"queue-timeout")) {
        pthread_join(producer,NULL);assert(b.result==-ETIMEDOUT);
    } else assert(aicwf_txpipe_drain(p)==-ETIMEDOUT);
    assert(atomic_load(&allocs)==3);assert(aicwf_txpipe_error(p));
    release_sink(&s);aicwf_txpipe_destroy(p);assert(s.count==1);
    assert(!atomic_load(&allocs));free(orig.data);
}
static void io_error(void) {
    struct skb_buff_pool orig=original();struct sink s;sink_init(&s);s.error=-EIO;
    struct aicwf_txpipe *p=aicwf_txpipe_create(&orig,&s,send_pool);assert(!IS_ERR(p));
    enqueue(p,1);assert(aicwf_txpipe_drain(p)==-EIO);
    assert(aicwf_txpipe_submit(p)==-EIO);aicwf_txpipe_cancel(p);
    assert(aicwf_txpipe_error(p)==-EIO);aicwf_txpipe_destroy(p);
    assert(s.count==1 && !atomic_load(&allocs));free(orig.data);
}
static void init_fail(void) {
    struct skb_buff_pool orig=original();struct sink s;sink_init(&s);
    for(int i=1;i<=4;i++) {
        allocation=0;fail_at=i;thread_fail=(i==4);
        struct aicwf_txpipe *p=aicwf_txpipe_create(&orig,&s,send_pool);
        assert(IS_ERR(p));assert(PTR_ERR(p)==(i==4?-EAGAIN:-ENOMEM));
        assert(orig.data[0]==0xa5 && !atomic_load(&allocs));
    }
    thread_fail=fail_at=0;allocation=0;
    struct aicwf_txpipe *p=aicwf_txpipe_create(&orig,&s,send_pool);assert(!IS_ERR(p));
    aicwf_txpipe_destroy(p);assert(!atomic_load(&allocs));free(orig.data);
}
static void two_devices(void) {
    struct skb_buff_pool orig[2]={original(),original()};struct sink s[2];
    struct aicwf_txpipe *p[2];
    for(int i=0;i<2;i++){sink_init(&s[i]);s[i].check_sequence=true;p[i]=aicwf_txpipe_create(&orig[i],&s[i],send_pool);assert(!IS_ERR(p[i]));}
    for(int i=0;i<300;i++){enqueue(p[0],i);enqueue(p[1],i);}
    for(int i=0;i<2;i++)assert(!aicwf_txpipe_drain(p[i]));
    usleep(30000);
    for(int i=0;i<2;i++){assert(s[i].count==300);aicwf_txpipe_destroy(p[i]);free(orig[i].data);}
    assert(!atomic_load(&allocs));
}
static void bounds(void) {
    struct skb_buff_pool p=original();
    assert(aicwf_aggr_fits(&p,0,p.size-4));assert(!aicwf_aggr_fits(&p,0,p.size-3));
    assert(!aicwf_aggr_fits(&p,SIZE_MAX,1));assert(!aicwf_aggr_fits(&p,1,SIZE_MAX));
    p.end=p.data+1023;assert(aicwf_aggr_fits(&p,0,508));assert(!aicwf_aggr_fits(&p,0,509));
    struct kernel_param kp={&tx_aggr_counter};
    const char *invalid[]={"0","-1","1","2","33","64","no","9999999999999"};
    for(unsigned int i=0;i<sizeof(invalid)/sizeof(*invalid);i++) {
        assert(tx_aggr_set(invalid[i],&kp)<0);assert(tx_aggr_counter==32);
    }
    assert(!tx_aggr_set("3",&kp));assert(tx_aggr_counter==3);
    assert(!tx_aggr_set("32",&kp));free(p.data);
}
static void packing(void) {
    struct skb_buff_pool orig=original();struct sink s;sink_init(&s);
    struct aicwf_txpipe *p=aicwf_txpipe_create(&orig,&s,send_pool);assert(!IS_ERR(p));
    struct aicwf_tx_priv tx={.kmal_buf=&orig,.head=orig.data,.tx_pipe=p};
    for(int i=0;i<70;i++) {
        memset(tx.head,0x7a,100);tx.tail=tx.head+100;atomic_set(&tx.aggr_count,3);
        assert(!aicwf_sdio_aggr_send(&tx));assert(!aicwf_txpipe_drain(p));
        assert(tx.tail==tx.head && !atomic_read(&tx.aggr_count));
        assert(s.captured_len==512);
        for(int j=0;j<512;j++)assert(s.captured[j]==(j<100?0x7a:0));
    }
    aicwf_txpipe_destroy(p);assert(!atomic_load(&allocs));free(orig.data);
}
static void producer(void) {
    struct skb_buff_pool orig=original();struct sink s;sink_init(&s);direct_sink=&s;
    struct aicwf_txpipe *p=aicwf_txpipe_create(&orig,&s,send_pool);assert(!IS_ERR(p));
    struct aicwf_tx_priv tx={.kmal_buf=&orig,.head=orig.data,.tail=orig.data,
                            .tx_pipe=p,.fw_avail_bufcnt=128};
    struct aic_sdio_dev dev={.tx_priv=&tx,.chipid=PRODUCT_ID_AIC8801};tx.sdiodev=&dev;
    spin_lock_init(&tx.txqlock);struct rwnx_hw hw={0};struct rwnx_vif vif={&hw};
    u8 *data=malloc(5000);assert(data);
    for(int i=0;i<35;i++) {
        struct sw_hdr *sw=calloc(1,sizeof(*sw));sw->headroom=sizeof(struct rwnx_txhdr);sw->rwnx_vif=&vif;
        struct rwnx_txhdr h={sw};memcpy(data,&h,sizeof(h));memset(data+sizeof(h),0x17,3000);
        struct sk_buff pkt={.data=data,.len=3000+sizeof(h)};
        tx.txq.next=&pkt;atomic_set(&tx.tx_pktcnt,2);
        assert(!aicwf_sdio_send(&tx,0));assert(pkt.consumed);
    }
    /* 3 KiB packets hit the byte limit before the 30-packet cap. */
    assert(fc_calls>0);tx.fw_avail_bufcnt-=atomic_read(&tx.aggr_count);
    assert(!aicwf_sdio_aggr_send(&tx));assert(!aicwf_txpipe_drain(p));
    assert(s.count>=3 && tx.fw_avail_bufcnt<128);
    /* Reject an impossible frame before touching or consuming its bytes. */
    struct sw_hdr *sw=calloc(1,sizeof(*sw));sw->headroom=sizeof(struct rwnx_txhdr);sw->rwnx_vif=&vif;
    struct rwnx_txhdr h={sw};memcpy(data,&h,sizeof(h));struct sk_buff pkt={.data=data,.len=5000};
    u8 before[64];memcpy(before,tx.head,64);assert(aicwf_sdio_aggr(&tx,&pkt)==-EMSGSIZE);
    assert(!memcmp(before,tx.head,64) && !pkt.consumed);free(sw);
    aicwf_txpipe_destroy(p);assert(!atomic_load(&allocs));free(orig.data);free(data);
}
static void lower_limit(void) {
    struct skb_buff_pool orig=original();struct sink s;sink_init(&s);direct_sink=&s;
    struct aicwf_txpipe *p=aicwf_txpipe_create(&orig,&s,send_pool);assert(!IS_ERR(p));
    struct aicwf_tx_priv tx={.kmal_buf=&orig,.head=orig.data,.tail=orig.data+100,
                            .tx_pipe=p,.fw_avail_bufcnt=100};
    struct aic_sdio_dev dev={.tx_priv=&tx};tx.sdiodev=&dev;
    atomic_set(&tx.aggr_count,10);atomic_set(&tx.tx_pktcnt,2);
    struct kernel_param kp={&tx_aggr_counter};assert(!tx_aggr_set("3",&kp));
    /* Flush the ten already packed frames even though count != new limit.
     * No new packet is dequeued by this call, and credits are deducted once.
     */
    assert(!aicwf_sdio_send(&tx,0));assert(!aicwf_txpipe_drain(p));
    assert(s.count==1 && tx.fw_avail_bufcnt==90);
    assert(!atomic_read(&tx.aggr_count) && atomic_read(&tx.tx_pktcnt)==2);
    aicwf_txpipe_destroy(p);assert(!atomic_load(&allocs));free(orig.data);
}
static void invalid_aggregate(void) {
    struct skb_buff_pool orig=original();struct sink s;sink_init(&s);
    struct aicwf_txpipe *p=aicwf_txpipe_create(&orig,&s,send_pool);assert(!IS_ERR(p));
    struct aicwf_tx_priv tx={.kmal_buf=&orig,.head=orig.data,.tail=orig.end-1,.tx_pipe=p};
    atomic_set(&tx.aggr_count,1);
    assert(aicwf_sdio_aggr_send(&tx)==-EMSGSIZE);
    assert(aicwf_txpipe_drain(p)==-EMSGSIZE && s.count==0);
    assert(atomic_load(&st_bounds)==1);
    aicwf_txpipe_destroy(p);assert(!atomic_load(&allocs));free(orig.data);
}
int main(int argc,char **argv) {
    assert(argc==2);
    if(!strcmp(argv[1],"order"))order();
    else if(!strcmp(argv[1],"cancel") || !strcmp(argv[1],"queue-timeout") || !strcmp(argv[1],"drain-timeout"))blocked(argv[1]);
    else if(!strcmp(argv[1],"io-error"))io_error();
    else if(!strcmp(argv[1],"init-fail"))init_fail();
    else if(!strcmp(argv[1],"two-devices"))two_devices();
    else if(!strcmp(argv[1],"bounds"))bounds();
    else if(!strcmp(argv[1],"packing"))packing();
    else if(!strcmp(argv[1],"producer"))producer();
    else if(!strcmp(argv[1],"lower-limit"))lower_limit();
    else if(!strcmp(argv[1],"invalid-aggregate"))invalid_aggregate();
    else abort();
    puts("PASS");return 0;
}
