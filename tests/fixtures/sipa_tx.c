#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
typedef int netdev_tx_t;
#define NETDEV_TX_OK 0
#define NETDEV_TX_BUSY 16
#define DEV_ON 1
#define ETH_HLEN 14
#define likely(x) (x)
#define unlikely(x) (x)
#define pr_err(...) ((void)0)
#define pr_debug(...) ((void)0)
#define pr_err_ratelimited(...) ((void)0)
struct sk_buff { unsigned char bytes[512], *head, *data; unsigned len, mac_header, network_header; bool freed, cloned; };
struct net_device_stats { unsigned tx_packets, tx_bytes, tx_dropped, tx_errors; };
struct sipa_eth_init_data { int src_id, netid; };
struct sipa_eth { int state, nic_id; struct sipa_eth_init_data *pdata; struct net_device_stats *stats; };
struct net_device { const char *name; struct sipa_eth *priv; };
struct sipa_plat_drv_cfg { struct { unsigned send_bytes, bytes_threshold, persec_bytes; } ul_threshold; };
static struct sipa_plat_drv_cfg ipa;
static unsigned frees, calls;
static int linear_error, cow_error, send_result;
static unsigned char payload[100];
static void *netdev_priv(struct net_device *d) { return d->priv; }
static struct sipa_plat_drv_cfg *sipa_get_ctrl_pointer(void) { return &ipa; }
static int skb_linearize(struct sk_buff *s) { assert(!s->freed); return linear_error; }
static void dev_kfree_skb_any(struct sk_buff *s) { assert(!s->freed); s->freed=true; ++frees; }
static unsigned skb_headroom(struct sk_buff *s) { return s->data-s->head; }
static int skb_cow_head(struct sk_buff *s, unsigned n) {
    if(cow_error) return cow_error;
    if(skb_headroom(s)<n) {
        unsigned delta=n-skb_headroom(s);
        memmove(s->data+delta,s->data,s->len);
        s->data+=delta;s->mac_header+=delta;s->network_header+=delta;
    }
    s->cloned=false;return 0;
}
static void skb_push(struct sk_buff *s,unsigned n) { assert(skb_headroom(s)>=n);s->data-=n;s->len+=n; }
static void __skb_pull(struct sk_buff *s,unsigned n) { assert(s->len>=n);s->data+=n;s->len-=n; }
static void skb_pull_inline(struct sk_buff *s,unsigned n) { __skb_pull(s,n); }
static void sipa_eth_wakeup_cp(struct sk_buff *s) { assert(!s->freed); }
static int sipa_nic_tx(int nic,int src,int netid,struct sk_buff *s) {
    bool raw=s->mac_header==s->network_header;
    assert(!s->freed);assert(s->len==sizeof(payload)+(raw?ETH_HLEN:0));
    assert(memcmp(s->data+(raw?ETH_HLEN:0),payload,sizeof(payload))==0);
    if(raw)assert(!s->cloned);
    ++calls;return send_result;
}
/* PRODUCTION_FUNCTIONS */
int main(int argc,char **argv) {
    assert(argc==2);int test=atoi(argv[1]);
    for(unsigned i=0;i<sizeof(payload);i++)payload[i]=(unsigned char)(i^0xa5);
    for(unsigned headroom=0;headroom<64;headroom++)for(int raw=0;raw<2;raw++)for(int clone=0;clone<2;clone++) {
        struct sk_buff s={0};s.head=s.bytes;s.data=s.head+headroom;s.len=sizeof(payload);
        s.mac_header=headroom;s.network_header=headroom+(raw?0:14);s.cloned=clone;
        memcpy(s.data,payload,sizeof(payload));
        struct net_device_stats stats={0};struct sipa_eth_init_data pd={0};
        struct sipa_eth eth={.state=test==4?0:DEV_ON,.pdata=&pd,.stats=&stats};
        struct net_device dev={.name="sipa_eth0",.priv=&eth};
        frees=calls=0;linear_error=test==1?-ENOMEM:0;cow_error=test==2?-ENOMEM:0;
        if(test==0) {
            for(int retry=0;retry<16;retry++) {
                send_result=retry%2?-EAGAIN:-EINPROGRESS;
                assert(sipa_eth_start_xmit(&s,&dev)==NETDEV_TX_BUSY);
                assert(!s.freed && !frees && s.len==sizeof(payload));
                assert(memcmp(s.data,payload,sizeof(payload))==0);
            }
            send_result=0;assert(sipa_eth_start_xmit(&s,&dev)==NETDEV_TX_OK);
            assert(!s.freed && stats.tx_packets==1 && stats.tx_bytes==sizeof(payload));
        } else {
            send_result=test==3?-EIO:0;
            assert(sipa_eth_start_xmit(&s,&dev)==NETDEV_TX_OK);
            if(test==2 && !raw)assert(!s.freed && stats.tx_packets==1);
            else assert(s.freed && frees==1 && stats.tx_dropped==1 && !stats.tx_packets);
        }
    }
    return 0;
}
