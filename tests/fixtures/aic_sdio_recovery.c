#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef unsigned char u8; typedef unsigned long long u64; typedef unsigned int uint;
#define HZ 1000UL
#define CMD_TX_TIMEOUT 5000
#define SDIO_CCCR_ABORT 6
#define PAGE_SIZE 4096
#define msecs_to_jiffies(n) (n)
#define time_after_eq(a,b) ((long)((a)-(b))>=0)
#define time_after(a,b) ((long)((a)-(b))>0)
#define scnprintf snprintf
#define module_param_cb(...)
#define MODULE_PARM_DESC(...)
typedef struct { long long value; } atomic64_t;
#define ATOMIC64_INIT(n) {n}
static void atomic64_inc(atomic64_t *v) { v->value++; }
static void atomic64_add(long long n,atomic64_t *v) { v->value+=n; }
static long long atomic64_read(atomic64_t *v) { return v->value; }
struct kernel_param {};
struct kernel_param_ops { int (*get)(char *,const struct kernel_param *); };
struct mmc_host { bool retune_crc_disable,need_retune;int hold; };
struct mmc_card { struct mmc_host *host;bool removed; };
struct sdio_func { struct mmc_card *card;unsigned num; };
struct aic_sdio_dev { struct sdio_func *func;unsigned long recovery_since;unsigned recovery_burst;
 struct { unsigned flow_ctrl_reg,wr_fifo_addr; } sdio_reg; };
static unsigned long jiffies;
static int errors[8],length,cursor,reads,requested,actual,aborts,slow,removed_after,claimed,writes;
static int consumed,abort_failure;
static u64 ktime_get_ns(void) { return jiffies*1000000ULL; }
static bool mmc_card_removed(struct mmc_card *c) { return c->removed; }
static void mmc_retune_needed(struct mmc_host *h) { assert(claimed);h->need_retune=true;requested++; }
static void sdio_claim_host(struct sdio_func *f) { (void)f;assert(!claimed);claimed=1; }
static void sdio_release_host(struct sdio_func *f) { (void)f;assert(claimed);claimed=0; }
static void sdio_retune_crc_disable(struct sdio_func *f) { assert(claimed);f->card->host->retune_crc_disable=true; }
static void sdio_retune_crc_enable(struct sdio_func *f) { assert(claimed);f->card->host->retune_crc_disable=false; }
static void sdio_retune_hold_now(struct sdio_func *f) { assert(claimed);f->card->host->hold++; }
static void sdio_retune_release(struct sdio_func *f) { assert(claimed && f->card->host->hold);f->card->host->hold--; }
static u8 sdio_readb(struct sdio_func *f,unsigned reg,int *ret) {
 (void)reg;assert(claimed);reads++;
 if(f->card->host->need_retune && !f->card->host->hold){actual++;f->card->host->need_retune=false;}
 if(slow)jiffies+=5000;
 *ret=cursor<length?errors[cursor++]:0;
 if(removed_after)f->card->removed=true;
 return *ret?255:42;
}
static void sdio_f0_writeb(struct sdio_func *f,u8 n,unsigned addr,int *ret) {
 assert(claimed && f->card->host->hold && n==f->num && addr==SDIO_CCCR_ABORT);aborts++;*ret=abort_failure;
}
static int sdio_writesb(struct sdio_func *f,unsigned addr,u8 *buf,unsigned count) {
 (void)f;(void)addr;(void)buf;assert(claimed && count>=5);writes++;consumed+=5;return -EILSEQ;
}
/* PRODUCTION_HEADER */
static atomic64_t st_wr=ATOMIC64_INIT(0),st_wr_ns=ATOMIC64_INIT(0),st_wr_err=ATOMIC64_INIT(0),st_bytes=ATOMIC64_INIT(0);
/* PRODUCTION_SEND */
static void reset(struct aic_sdio_dev *d) {
 reads=cursor=length=requested=actual=aborts=slow=removed_after=writes=consumed=abort_failure=0;
 jiffies=0;d->recovery_since=0;d->recovery_burst=0;d->func->card->removed=false;
 d->func->card->host->retune_crc_disable=false;d->func->card->host->need_retune=false;
}
int main(void) {
 struct mmc_host h={0};struct mmc_card card={&h,false};struct sdio_func func={&card,1};
 struct aic_sdio_dev d={.func=&func,.sdio_reg={.flow_ctrl_reg=10,.wr_fifo_addr=7}};u8 v,buffer[20]={0};
 reset(&d);sdio_claim_host(&func);assert(!aicwf_sdio_read_credit(&d,10,&v));sdio_release_host(&func);
 assert(reads==1 && v==42 && !h.retune_crc_disable);
 reset(&d);errors[0]=errors[1]=-EILSEQ;length=2;sdio_claim_host(&func);
 assert(!aicwf_sdio_read_credit(&d,10,&v));sdio_release_host(&func);assert(reads==3 && requested==1 && actual==1 && !h.retune_crc_disable);
 reset(&d);for(int i=0;i<4;i++)errors[i]=-ETIMEDOUT;length=4;sdio_claim_host(&func);
 assert(aicwf_sdio_read_credit(&d,10,&v)==-ETIMEDOUT);sdio_release_host(&func);assert(reads==4 && !h.retune_crc_disable);
 reset(&d);errors[0]=-EIO;length=1;sdio_claim_host(&func);assert(aicwf_sdio_read_credit(&d,10,&v)==-EIO);
 sdio_release_host(&func);assert(reads==1 && requested==0);
 reset(&d);slow=1;errors[0]=-EILSEQ;length=1;sdio_claim_host(&func);assert(aicwf_sdio_read_credit(&d,10,&v)==-EILSEQ);
 sdio_release_host(&func);assert(reads==1 && !h.retune_crc_disable);
 reset(&d);h.retune_crc_disable=true;sdio_claim_host(&func);assert(!aicwf_sdio_read_credit(&d,10,&v));sdio_release_host(&func);assert(h.retune_crc_disable);
 reset(&d);removed_after=1;errors[0]=-EILSEQ;length=1;sdio_claim_host(&func);assert(aicwf_sdio_read_credit(&d,10,&v)==-EILSEQ);
 sdio_release_host(&func);assert(reads==1 && !h.retune_crc_disable);
 reset(&d);for(int n=0;n<3;n++) {
  cursor=0;length=1;errors[0]=-EILSEQ;sdio_claim_host(&func);assert(!aicwf_sdio_read_credit(&d,10,&v));sdio_release_host(&func);
 }assert(requested==1 && d.recovery_burst==0);
 reset(&d);assert(aicwf_sdio_send_pkt(&d,buffer,sizeof(buffer))==-EILSEQ);
 assert(writes==1 && consumed==5 && aborts==1 && requested==1 && h.hold==0 && !claimed);
 reset(&d);sdio_claim_host(&func);aicwf_sdio_fifo_error(&func,-ETIMEDOUT);sdio_release_host(&func);assert(!aborts && requested==1);
 reset(&d);abort_failure=-EILSEQ;sdio_claim_host(&func);aicwf_sdio_fifo_error(&func,-EILSEQ);sdio_release_host(&func);assert(aborts==1 && h.hold==0);
 char report[PAGE_SIZE];assert(aicwf_bus_errors_get(report,0)>0);assert(strstr(report,"fifo_failed"));
 puts("Bounded credit reads, CRC policy, deadline/card loss, burst recovery and partial FIFO non-replay passed");
 return 0;
}
