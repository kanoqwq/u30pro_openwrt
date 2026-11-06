/* Compile the production SIPA flow and request functions with deterministic
 * resource completion and real threads. No device or modem access. */
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <unistd.h>
typedef pthread_mutex_t spinlock_t;
#define spin_lock_init(p) assert(!pthread_mutex_init(p, NULL))
#define spin_lock(p) assert(!pthread_mutex_lock(p))
#define spin_unlock(p) assert(!pthread_mutex_unlock(p))
#define spin_lock_irqsave(p,f) do { (f)=0; spin_lock(p); } while (0)
#define spin_unlock_irqrestore(p,f) do { (void)(f); spin_unlock(p); } while (0)
#define READ_ONCE(x) __atomic_load_n(&(x), __ATOMIC_RELAXED)
#define WRITE_ONCE(x,v) __atomic_store_n(&(x),(v),__ATOMIC_RELAXED)
#define NIC_OPEN 0
#define NIC_CLOSE 1
#define SIPA_ENTER_FLOWCTRL 1
#define SIPA_LEAVE_FLOWCTRL 2
#define atomic_read(p) atomic_load(p)
#define atomic_set(p,v) atomic_store(p,v)
#define pr_info(...) ((void)0)
struct work_struct { atomic_int queued; };
static void schedule_work(struct work_struct *w) { atomic_fetch_add(&w->queued,1); }
struct sipa_nic_cons_res {
 spinlock_t lock; bool resource_requested,need_request,request_in_progress,rm_flow_ctrl;
 int cons;
};
struct queue {
 atomic_int stopped,calls,inside,overlap,block,entered;
};
struct sipa_nic {
 spinlock_t flow_lock; struct sipa_nic_cons_res rm_res;
 atomic_int status; bool data_flowctrl,rm_flowctrl;
 void (*cb)(void *,int,unsigned long);void *cb_priv;
 struct work_struct tx_again_work;
};
struct sipa_skb_sender { bool fifo_flowctrl; };
struct device { void *pm_domain; };
struct sipa_plat_drv_cfg { struct device *dev; struct sipa_skb_sender *sender; };
static struct device device={.pm_domain=(void *)1};
static struct sipa_skb_sender sender;
static struct sipa_plat_drv_cfg ipa={.dev=&device,.sender=&sender};
static struct sipa_plat_drv_cfg *sipa_get_ctrl_pointer(void) { return &ipa; }
static void pm_stay_awake(struct device *d) { (void)d; }
static struct sipa_nic *request_nic;
static int request_result,early_grant;
static void grant(struct sipa_nic *nic);
static int sipa_rm_request_resource(int cons) {
 (void)cons;if(early_grant)grant(request_nic);return request_result;
}
/* PRODUCTION_FUNCTIONS */
static void grant(struct sipa_nic *nic) {
 if(sipa_nic_rm_res_granted(nic))sipa_nic_sync_flow_ctrl(nic);
}
static void callback(void *priv,int event,unsigned long unused) {
 (void)unused;struct queue *q=priv;
 if(atomic_fetch_add(&q->inside,1))atomic_store(&q->overlap,1);
 atomic_fetch_add(&q->calls,1);
 if(event==SIPA_ENTER_FLOWCTRL && atomic_load(&q->block)) {
  atomic_store(&q->entered,1);while(atomic_load(&q->block))usleep(100);
 }
 atomic_store(&q->stopped,event==SIPA_ENTER_FLOWCTRL);
 atomic_fetch_sub(&q->inside,1);
}
static void setup(struct sipa_nic *nic,struct queue *q) {
 memset(nic,0,sizeof(*nic));memset(q,0,sizeof(*q));
 spin_lock_init(&nic->flow_lock);spin_lock_init(&nic->rm_res.lock);
 nic->cb=callback;nic->cb_priv=q;atomic_set(&nic->status,NIC_OPEN);
 nic->rm_res.need_request=true;
}
static void pending(struct sipa_nic *nic,bool waiting) {
 spin_lock(&nic->rm_res.lock);nic->rm_res.rm_flow_ctrl=waiting;
 nic->rm_res.request_in_progress=waiting;spin_unlock(&nic->rm_res.lock);
}
static void *sync_thread(void *nic) { sipa_nic_sync_flow_ctrl(nic);return NULL; }
static void *stress_thread(void *arg) {
 struct sipa_nic *nic=arg;
 for(int n=0;n<5000;n++){pending(nic,true);sipa_nic_sync_flow_ctrl(nic);grant(nic);}
 return NULL;
}
int main(int argc,char **argv) {
 assert(argc==2);int which=atoi(argv[1]);
 struct sipa_nic nic,other;struct queue q,q2;setup(&nic,&q);setup(&other,&q2);
 switch(which) {
 case 0: /* A delayed ENTER must not stop an already granted resource. */
  pending(&nic,true);grant(&nic);sipa_nic_sync_flow_ctrl(&nic);
  assert(!atomic_load(&q.stopped) && !nic.rm_flowctrl);break;
 case 1:
  pending(&nic,true);sipa_nic_sync_flow_ctrl(&nic);assert(atomic_load(&q.stopped));
  grant(&nic);assert(!atomic_load(&q.stopped));break;
 case 2: { /* Leave races a paused enter callback on another CPU. */
  pending(&nic,true);atomic_store(&q.block,1);pthread_t a,b;
  assert(!pthread_create(&a,NULL,sync_thread,&nic));
  for(int n=0;!atomic_load(&q.entered) && n<10000;n++)usleep(100);
  assert(atomic_load(&q.entered));assert(sipa_nic_rm_res_granted(&nic));
  assert(!pthread_create(&b,NULL,sync_thread,&nic));usleep(10000);
  assert(atomic_load(&q.calls)==1);atomic_store(&q.block,0);
  assert(!pthread_join(a,NULL));assert(!pthread_join(b,NULL));
  assert(!atomic_load(&q.stopped) && !atomic_load(&q.overlap));break;
 }
 case 3:
  pending(&nic,true);WRITE_ONCE(sender.fifo_flowctrl,true);sipa_nic_sync_flow_ctrl(&nic);
  grant(&nic);assert(atomic_load(&q.stopped));
  WRITE_ONCE(sender.fifo_flowctrl,false);sipa_nic_sync_flow_ctrl(&nic);
  assert(!atomic_load(&q.stopped));
  /* A stale FIFO-enter worker reads the latest IRQ state, not its name. */
  sipa_nic_sync_flow_ctrl(&nic);assert(!atomic_load(&q.stopped));break;
 case 4:
 case 5:
 case 6:
 case 7:
  request_nic=&nic;request_result=which==4?0:which==7?-EIO:-EINPROGRESS;
  early_grant=which==5;
  { int r=sipa_nic_rm_res_request(&nic);
   if(which==6)assert(r==-EINPROGRESS && nic.rm_res.request_in_progress && nic.rm_res.rm_flow_ctrl);
   else if(which==7)assert(r==-EIO && nic.rm_res.need_request && !nic.rm_res.rm_flow_ctrl);
   else assert(r==0 && !nic.rm_res.request_in_progress && !nic.rm_res.rm_flow_ctrl);
  }break;
 case 8:
  atomic_set(&nic.status,NIC_CLOSE);pending(&nic,true);sipa_nic_sync_flow_ctrl(&nic);
  grant(&nic);assert(!atomic_load(&q.calls));
  atomic_set(&nic.status,NIC_OPEN);pending(&nic,false);sipa_nic_sync_flow_ctrl(&nic);
  assert(!atomic_load(&q.stopped));break;
 case 9:
  pending(&nic,true);sipa_nic_sync_flow_ctrl(&nic);sipa_nic_sync_flow_ctrl(&other);
  assert(atomic_load(&q.stopped) && !atomic_load(&q2.stopped));grant(&nic);
  assert(!atomic_load(&q.stopped));break;
 case 10: {
  pthread_t a,b;assert(!pthread_create(&a,NULL,stress_thread,&nic));
  assert(!pthread_create(&b,NULL,stress_thread,&nic));assert(!pthread_join(a,NULL));assert(!pthread_join(b,NULL));
  pending(&nic,false);sipa_nic_sync_flow_ctrl(&nic);
  assert(!atomic_load(&q.stopped) && !atomic_load(&q.overlap));break;
 }
 default:assert(0);
 }
 puts("production SIPA flow-control scenario passed");return 0;
}
