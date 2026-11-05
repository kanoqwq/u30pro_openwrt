"""Real native SMS navigation/layout plus the production feeder's scoped reads."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

TOP=Path(__file__).resolve().parents[1]
NATIVE=TOP/'devices/u30pro/native/tools'
ROOT=Path('/home/kano/openwrt-build/package-work/u30pro-release/root')


@unittest.skipUnless(os.name=='posix','native screen simulator')
class Reader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='screen-sms-');cls.addClassCleanup(cls.temp.cleanup)
        base=Path(cls.temp.name)
        source=r'''#define UI_HOST
#define UI_RUN "TEST_RUN"
#define main simulator_main
#include "u30pro_ui.c"
#undef main
#include <assert.h>
static void start(void) {
 ui_init_canvases();g_ms=vclock=10000;last_act=g_ms;
 D.feed_ok=1;pin_mode=locked=asleep=lock_soft=power_menu=0;
 go_home();page=PG_SIGNAL;D.nsms=6;D.sms_slot=1;D.sms_unread=2;
 for(int i=0;i<6;i++) {
  snprintf(D.sms[i].id,sizeof D.sms[i].id,"%d",100+i);
  strcpy(D.sms[i].addr,"10086");strcpy(D.sms[i].text,"preview");D.sms[i].unread=i==4;
 }
 sheet=SH_SMS;sheet_pos=1;sheet_anim=0;sms_scroll=3;compose();
}
static void opened(void) {
 do_action(H_SMS_ROW+4);compose();assert(ov==OV_SMS && !strcmp(sms_detail.id,"104"));
 assert(D.sms_unread==2 && D.sms[4].unread==1); /* no optimistic read */
 FILE *f=fopen(UI_RUN "/sms.ack","r");char line[64];assert(f && fgets(line,sizeof line,f));fclose(f);
 assert(!strcmp(line,"1 104\n"));
}
static void in_list(void) {
 assert(ov==OV_NONE && sheet==SH_SMS && sheet_pos==1.f && !sheet_anim);
 assert(sms_scroll==3 && page==PG_SIGNAL);
}
int main(int argc,char **argv) {
 assert(argc==2);start();
 switch(atoi(argv[1])) {
 case 1: {
  go_home();
  const char *dates[]={"1月1日 一","12月31日 星期四","已运行 · 等待授时"};
  for(int i=0;i<3;i++) {
   Cv a=cv_new(240,240),b=cv_new(240,240);g_reg=1;nhits=0;D.sms_unread=0;
   home_date(&a,dates[i]);TXTC(&b,FN14,120,120,dates[i],C_DIM);
   assert(!memcmp(a.p,b.p,240*240*4) && nhits==0);
   free(a.p);free(b.p);
   D.sms_unread=1;D.charging=1;nhits=0;compose();
   int found=0;for(int j=0;j<nhits;j++)if(hits[j].id==H_OPEN_SMS) {
    assert(hits[j].y>=100 && hits[j].y+hits[j].h<=130);
    assert(hits[j].x>=20 && hits[j].x+hits[j].w<=220);found++;
   }
   assert(found==1); /* charging must not hide the unread icon */
  }
  break;
 }
 case 2: {
  opened();Sms selected=D.sms[4];strcpy(selected.text,"full body");selected.unread=0;
  strcpy(D.sms[4].id,"999");strcpy(D.sms[4].text,"new incoming");D.sms[0]=selected;
  compose();assert(!strcmp(sms_detail.id,"104") && !strcmp(sms_detail.text,"full body"));
  D.sms_slot=0;strcpy(D.sms[0].text,"wrong SIM");compose();
  assert(!strcmp(sms_detail.text,"full body"));break;
 }
 case 3:
  opened();ui_touch(T_DOWN,185,100,now_ms());vclock+=10;
  ui_touch(T_MOVE,70,100,now_ms());vclock+=10;ui_touch(T_UP,70,100,now_ms());
  in_list();break;
 case 4: {
  opened();ui_key(102,100);in_list();opened();compose();
  int back=-1;for(int i=0;i<nhits;i++)if(hits[i].id==H_BACK)back=i;
  assert(back>=0);Hit h=hits[back];int x=h.x+h.w/2,y=h.y+h.h/2;
  ui_touch(T_DOWN,x,y,now_ms());vclock+=10;ui_touch(T_UP,x,y,now_ms());in_list();break;
 }
 case 5: {
  char id[]="000041",slot[]="0",row[]="sender\ttime\t1\ttext";
  feed_set("sms_slot",slot);feed_set("sms_id.2",id);feed_set("sms.2",row);
  assert(D.sms_slot==0 && !strcmp(D.sms[2].id,"000041") && !strcmp(D.sms[2].text,"text"));break;
 }
 default:assert(0);
 }
 return 0;
}
'''.replace('TEST_RUN',str(base))
        (base/'test.c').write_text(source);cls.binary=base/'test'
        r=subprocess.run(['gcc','-std=gnu11','-O1','-Wall','-Wextra','-Werror','-I',str(NATIVE),
                          str(base/'test.c'),'-lm','-o',str(cls.binary)],capture_output=True,text=True)
        if r.returncode:raise RuntimeError(r.stderr)

    def test_real_reader_date_icon_stable_ids_and_all_back_paths(self):
        for case in range(1,6):
            with self.subTest(case=case):
                r=subprocess.run([str(self.binary),str(case)],capture_output=True,text=True,timeout=20)
                self.assertEqual(r.returncode,0,r.stdout+r.stderr)


@unittest.skipUnless(os.name=='posix' and ROOT.exists(),'prepared ARM64 target')
class Feeder(unittest.TestCase):
    def test_real_feeder_marks_only_opened_card_and_counts_after_ack(self):
        src=(TOP/'devices/u30pro/overlay/usr/sbin/u30pro-ui-feed').read_text()
        helpers=src[src.index('function clean('):src.index('function run()')]
        listener=src[src.index('const panel_events='):src.index('const modem_events=')]
        program=r'''
let requested={},sms_reads={},sms_open=null,sms_text=null,receive,shows=0,lists=0,fail=false;
const timer={set:()=>true};
let pool={
 '0':[{id:'12',status:'unread',peer:'A',time:'t',preview:'card0 preview'},
      {id:'13',status:'unread',peer:'B',time:'t',preview:'other preview'}],
 '1':[{id:'12',status:'unread',peer:'C',time:'t',preview:'card1 preview'},
      {id:'13',status:'unread',peer:'D',time:'t',preview:'last preview'}]
};
const bus={listener:(event,cb)=>{receive=cb;return {};},call:(object,method,args)=>{
 if(object!='mu300dash')die('unexpected owner');
 if(method=='sms_list') {
  lists++;return {total:2,unread:length(filter(pool[args.slot],m=>m.status=='unread')),
   msgs:map(pool[args.slot],m=>({id:m.id,status:m.status,peer:m.peer,time:m.time,preview:m.preview}))};
 }
 if(method!='sms_show')die('unexpected method');
 shows++;if(fail)return {ok:0};
 for(let msg in pool[args.slot])if(msg.id==args.id) {
  msg.status='read';return {ok:1,text:'id: '+msg.id+'\n---\nfull card'+args.slot+' body'};
 }
 return {ok:0};
}};
HELPERS
LISTENER
receive('u30pro.panel.request',{request:'sms_read',id:'12',slot:'1'});
let out=screen_sms('0',bus,false);
if(shows!=1 || lists!=2 || out.sms_unread!=2 || pool['0'][0].status!='unread' || pool['1'][0].status!='read')die('read wrong SIM/count');
out=screen_sms('1',bus,false);
if(out.sms_unread!=1 || out['sms.0']!='C\tt\t0\tfull card1 body')die('full body or unread not confirmed');
out=screen_sms('1',bus,false);
if(shows!=1 || out['sms.0']!='C\tt\t0\tfull card1 body')die('body reverted to preview or repeated ack');
fail=true;receive('u30pro.panel.request',{request:'sms_read',id:'13',slot:'1'});
out=screen_sms('1',bus,false);
if(out.sms_unread!=1 || !out.sms_error || pool['1'][1].status!='unread')die('failed read faked success');
fail=false;receive('u30pro.panel.request',{request:'sms_read',id:'13',slot:'1'});
out=screen_sms('1',bus,false);if(out.sms_unread!=0)die('last unread not cleared');
receive('u30pro.panel.request',{request:'sms_close'});
if(sms_open!=null || sms_text!=null)die('detail retained after close');
receive('u30pro.panel.request',{request:'sms_read',id:'invalid;AT',slot:'0'});
receive('u30pro.panel.request',{request:'sms_read',id:'12',slot:'2'});
if(length(keys(sms_reads)))die('invalid read accepted');
receive('u30pro.panel.request',{request:'sms_ack'});
out=screen_sms('0',bus,requested.sms_ack);if(out.sms_unread!=0)die('legacy ack contract lost');
for(let i=1;i<40;i++)receive('u30pro.panel.request',{request:'sms_read',id:''+i,slot:'0'});
if(length(keys(sms_reads))!=16)die('read queue not bounded');
print('PASS real feeder: scoped read, backend-confirmed counts, full body, failure/retry, close, legacy and bounded queue\n');
'''.replace('HELPERS',helpers).replace('LISTENER',listener)
        with tempfile.TemporaryDirectory(prefix='screen-sms-',dir=ROOT/'tmp') as directory:
            base=Path(directory);(base/'test.uc').write_text(program)
            r=subprocess.run(['docker','run','--rm','--platform','linux/arm64','-v',str(ROOT)+':/target',
                '--entrypoint','/bin/sh','u30pro-rootfs:25.12.5','-ec',
                'chroot /target /usr/bin/ucode /tmp/'+base.name+'/test.uc'],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertIn('PASS real feeder',r.stdout)


if __name__=='__main__':unittest.main(verbosity=2)
