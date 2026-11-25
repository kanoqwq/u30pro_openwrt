#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#define NOTIFY_DONE 0
#define NOTIFY_OK 1
#define NETDEV_REGISTER 1
#define NETDEV_UP 2
#define NETDEV_DOWN 3
#define NETDEV_UNREGISTER 4
#define fallthrough __attribute__((fallthrough))
#define pr_info(...) ((void)0)
static bool legacy_usb;
#define IS_ENABLED(option) legacy_usb
struct notifier_block { int unused; };
struct net_device { const char *name; };
static unsigned ups,downs;
static struct net_device *netdev_notifier_info_to_dev(void *p) { return p; }
static void sipa_dummy_netdev_join(struct net_device *d) {}
static void sipa_dummy_netdev_set_state(struct net_device *d,bool up) {}
static void sipa_nic_set_bypass_mode(bool bypass) { if(bypass)downs++;else ups++; }
/* PRODUCTION_FUNCTIONS */
int main(int argc,char **argv) {
    assert(argc==2);int test=atoi(argv[1]);legacy_usb=test!=0;
    const char *names[]={"usb0","usb00","usb0.1","wlan0","enx123"};
    for(unsigned i=0;i<sizeof(names)/sizeof(names[0]);i++) {
        struct net_device dev={names[i]};ups=downs=0;
        sipa_dummy_netdev_event_handler(NULL,NETDEV_REGISTER,&dev);
        for(unsigned n=0;n<100;n++) {
            sipa_dummy_netdev_event_handler(NULL,NETDEV_UP,&dev);
            sipa_dummy_netdev_event_handler(NULL,NETDEV_DOWN,&dev);
        }
        sipa_dummy_netdev_event_handler(NULL,NETDEV_UNREGISTER,&dev);
        assert(ups==(legacy_usb && i==0?100:0));assert(ups==downs);
    }
    return 0;
}
