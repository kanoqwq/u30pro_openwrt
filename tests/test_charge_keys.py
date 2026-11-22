"""Native tests of the production charger event wait using pipes, never evdev."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

TOP=Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name=='posix' and shutil.which('gcc'), 'native POSIX gcc required')
class ChargerKeys(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='charge-keys-')
        cls.path=Path(cls.temp.name)
        cls.addClassCleanup(cls.temp.cleanup)
        source=cls.path/'test.c'
        source.write_text(r'''
#include <sys/socket.h>
#include <linux/netlink.h>
static ssize_t fixture_recvfrom(int, void *, size_t, int, struct sockaddr *, socklen_t *);
#define recvfrom fixture_recvfrom
#define main keys_program
#include "mu300-keys.c"
#undef main
#undef recvfrom
#include <signal.h>
#include <sys/wait.h>
static ssize_t fixture_recvfrom(int fd, void *buf, size_t size, int flags,
                               struct sockaddr *addr, socklen_t *len) {
    ssize_t n=recv(fd,buf,size,flags);
    if(n>=0 && *len>=sizeof(struct sockaddr_nl)) {
        struct sockaddr_nl *nl=(void *)addr;
        memset(nl,0,sizeof(*nl));nl->nl_family=AF_NETLINK;
        *len=sizeof(*nl);
    }
    return n;
}
static void value(const char *path, const char *text) {
    FILE *f=fopen(path,"w");if(!f) _exit(9);
    fputs(text,f);if(fclose(f)) _exit(9);
}
static void key(int fd, int code, int value) {
    struct input_event e={.type=EV_KEY,.code=code,.value=value};
    if(write(fd,&e,sizeof(e))!=sizeof(e)) _exit(9);
}
int main(int argc, char **argv) {
    char event[]="change@/devices/test\0SUBSYSTEM=power_supply\0ONLINE=0\0";
    if(!charge_event(event,sizeof(event)) || charge_event("SUBSYSTEM=power_supply",22) ||
       charge_event("SUBSYSTEM=usb\0",14)) return 9;
    int p[2],events[2];if(pipe(p) || socketpair(AF_UNIX,SOCK_DGRAM,0,events)) return 9;
    pid_t child=fork();if(child<0) return 9;
    if(!child) {
        usleep(20000);
        if(!strcmp(argv[2],"short")) {
            key(p[1],KEY_POWER,1);usleep(20000);key(p[1],KEY_POWER,0);
            usleep(140000);key(p[1],KEY_POWER,1);
        } else if(!strcmp(argv[2],"other")) {
            key(p[1],KEY_HELP,1);usleep(180000);key(p[1],KEY_POWER,1);
        } else if(!strcmp(argv[2],"power")) key(p[1],KEY_POWER,1);
        else if(!strcmp(argv[2],"pd-recover")) {
            usleep(1925000);value(argv[1],"1\n");
            key(p[1],KEY_POWER,1);
        } else if(!strcmp(argv[2],"detach")) {
            usleep(200000);value(argv[1],"0\n");value(argv[3],"0\n");
            char change[]="change@/devices/typec\0SUBSYSTEM=extcon\0";
            if(send(events[1],change,sizeof(change),0)<0) _exit(9);
        }
        sleep(3);_exit(0);
    }
    struct pollfd fd={.fd=p[0],.events=POLLIN};
    int result=charge_wait(&fd,1,events[0],argv[1],argc>3?argv[3]:NULL,80);
    kill(child,SIGTERM);waitpid(child,NULL,0);close(p[0]);close(p[1]);
    return result;
}
''')
        cls.binary=cls.path/'test'
        subprocess.run(['gcc','-Wall','-Wextra','-Werror','-O2','-I',str(TOP/'tools/keys'),
                        str(source),'-o',str(cls.binary)],check=True,capture_output=True)

    def wait(self,value,mode,sink=None):
        path=self.path/'online';path.write_text(value)
        import time
        start=time.monotonic()
        args=[str(self.binary),str(path),mode]
        if sink is not None:
            cc=self.path/'sink';cc.write_text(sink);args.append(str(cc))
        r=subprocess.run(args,timeout=4)
        return r.returncode,time.monotonic()-start

    def test_long_power_starts(self):
        code,elapsed=self.wait('1\n','power')
        self.assertEqual(code,0);self.assertLess(elapsed,1)

    def test_short_power_and_wifi_key_do_not_start(self):
        for mode in ('short','other'):
            code,elapsed=self.wait('1\n',mode)
            self.assertEqual(code,0);self.assertGreater(elapsed,.23)

    def test_unplug_debounced_and_invalid_supply_fails_open(self):
        code,elapsed=self.wait('0\n','idle')
        self.assertEqual(code,3);self.assertGreaterEqual(elapsed,.49)
        self.assertEqual(self.wait('invalid\n','idle')[0],1)

    def test_pd_power_good_gap_keeps_gate_until_long_power(self):
        code,elapsed=self.wait('0\n','pd-recover','1\n')
        self.assertEqual(code,0)
        self.assertGreater(elapsed,1.9)

    def test_previous_online_only_path_mistakes_same_gap_for_unplug(self):
        code,elapsed=self.wait('0\n','pd-recover')
        self.assertEqual(code,3)
        self.assertLess(elapsed,1.5)

    def test_extcon_detach_wakes_wait_and_powers_off(self):
        code,elapsed=self.wait('1\n','detach','1\n')
        self.assertEqual(code,3)
        self.assertGreater(elapsed,.69)
        self.assertLess(elapsed,1.5)

    def test_confirmed_unplug_and_bad_typec_signal(self):
        self.assertEqual(self.wait('0\n','idle','0\n')[0],3)
        self.assertEqual(self.wait('0\n','idle','invalid\n')[0],1)
