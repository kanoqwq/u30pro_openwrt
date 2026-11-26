"""Compile the production C feed callback with real ARM64 blobmsg encoding."""
import json
from pathlib import Path
import runpy
import subprocess
import tempfile

TOP=Path(__file__).resolve().parents[1]

if __name__=='__main__':
    _,workspace,layout=runpy.run_path(str(TOP/'tools/build-settings.py'))['settings']()
    compiler=runpy.run_path(str(TOP/'tools/u30pro-compiler.py'))
    native=TOP/'devices/u30pro/native/tools'
    bus=(native/'ui/bus.h').read_text()
    callback=bus[bus.index('enum { F_DATA,'):bus.index('static int m_reload(')]
    code=r'''
#define _GNU_SOURCE
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>
#include <libubus.h>
#include <libubox/blobmsg.h>
#include "ui/data.h"
static int asleep,dirty;
static void toast_show(const char *s,uint32_t c,int ms){(void)s;(void)c;(void)ms;assert(0);}
''' + callback + r'''
static void call_feed(int partial,const char *value) {
 struct blob_buf b={0};blob_buf_init(&b,0);
 if(partial>=0)blobmsg_add_u8(&b,"partial",partial);
 void *t=blobmsg_open_table(&b,"data");blobmsg_add_string(&b,"high_rail",value);blobmsg_close_table(&b,t);
 assert(m_feed(NULL,NULL,NULL,"feed",b.head)==0);blob_buf_free(&b);
}
int main(void) {
 memset(&D,0,sizeof D);D.feed_ok=1;D.nsms=2;strcpy(D.sms[0].id,"saved-message");
 D.sinr_ok=D.nr=D.nr_idle=D.nr_rsrp_ok=D.nr_sinr_ok=1;D.sinr=17.5;D.nr_bw=100;
 D.bw_idx=5;strcpy(D.lte_bw,"20+20 MHz");memset(D.cl,42,sizeof D.cl);
 for(int asleep_now=0;asleep_now<2;asleep_now++)for(int active=0;active<2;active++) {
   Data expected=D;expected.high_rail=active;asleep=asleep_now;dirty=0;
   call_feed(1,active?"1":"0");assert(!memcmp(&D,&expected,sizeof D));assert(dirty==!asleep);
 }
 call_feed(1,"2");assert(!D.high_rail);
 for(int mode=-1;mode<=0;mode++) {
   D.nsms=1;strcpy(D.sms[0].id,"old");D.nr=1;D.nr_bw=80;D.bw_idx=5;
   strcpy(D.lte_bw,"20 MHz");memset(D.cl,42,sizeof D.cl);call_feed(mode,"0");
   assert(!D.nsms && !D.sms[0].id[0] && !D.nr && !D.nr_bw && D.bw_idx==-1 && !D.lte_bw[0]);
   Client empty[6]={0};assert(!memcmp(D.cl,empty,sizeof empty));
 }
 puts("PASS actual C callback: partial rail preserves all other Data bytes; full feed clearing and sleeping behavior retained");
 return 0;
}
'''
    with tempfile.TemporaryDirectory() as d:
        d=Path(d);source=d/'test.c';source.write_text(code)
        libs=workspace/'artifacts/u30pro-dev/lib'
        compiler['execute']([compiler['prefix'](layout)+'gcc','-O2','-I'+str(native),'-I'+layout['headers'],
            str(source),'-L'+str(libs),'-Wl,-rpath-link,'+str(libs),'-l:libubox.so.20260213','-lm','-o',str(d/'test')],layout,workspace)
        root=workspace/'package-work/u30pro-release/root'
        subprocess.run(['docker','run','--rm','--platform','linux/arm64',
            '--mount',f'type=bind,source={root},target=/target,readonly',
            '--mount',f'type=bind,source={d},target=/target/mnt,readonly',
            '--entrypoint','/usr/sbin/chroot','u30pro-rootfs:25.12.5','/target','/mnt/test'],check=True)
