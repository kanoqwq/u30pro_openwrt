"""Execute MU300's actual key dispatch block with deterministic command results."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

TOP=Path(__file__).resolve().parents[1]
SOURCE=TOP/'rootfs/overlay/opt/mu300/bin/mu300-sysd'


@unittest.skipUnless(os.name=='posix' and os.environ.get('MU300_TEST_RUNTIME_IMAGE'),
                     'select a prepared ARM64 OpenWrt image with ucode/socket via MU300_TEST_RUNTIME_IMAGE')
class ButtonEvents(unittest.TestCase):
    def test_entire_service_compiles_with_target_ucode(self):
        result=subprocess.run(['docker','run','--rm','--pull','never','--platform','linux/arm64','--network','none',
            '-v',str(SOURCE)+':/service.uc:ro','--entrypoint','/usr/bin/ucode',
            os.environ['MU300_TEST_RUNTIME_IMAGE'],'-c','/service.uc','-o','/tmp/service.ucb'],
            capture_output=True,text=True,timeout=45)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_double_settings_use_real_uci_and_follow_saved_changes(self):
        source=SOURCE.read_text()
        block=source[source.index('let button_config = null;'):source.index('let button_clicks = {};')]
        prefix="""
import {writefile} from 'fs';
const R='',KEY_POWER=116;
let model='u30air';
function button_model(){return model;}
function check(ok,message){if(!ok)die(message);}
"""
        suffix="""
check(!button_double_enabled(138),'explicit none was active');
check(button_double_enabled(116),'configured power double missing');
model='v50';check(!button_double_enabled(464),'V50 default should be inactive');
model='f50pro';check(button_double_enabled(102),'F50 Pro action missing');
writefile('/etc/config/unisoc_modem',"config modem main\\n option u30air_button_double default\\n option f50pro_button_double none\\n");
model='u30air';check(button_double_enabled(138),'U30 Air default band action missing');
check(!button_double_enabled(116),'missing power double should be inactive');
model='f50pro';check(!button_double_enabled(102),'saved setting change was cached');
print('PASS real UCI: model defaults, configured actions and live settings changes');
"""
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);config=base/'config';config.mkdir()
            (config/'unisoc_modem').write_text("config modem main\n option u30air_button_double none\n option u30air_button_power_double custom\n option v50_button_double default\n option f50pro_button_double data-switch\n")
            test=base/'real.uc';test.write_text(prefix+block+suffix)
            result=subprocess.run(['docker','run','--rm','--pull','never','--platform','linux/arm64','--network','none',
                '-v',str(config)+':/etc/config','-v',str(test)+':/test.uc:ro','--entrypoint','/usr/bin/ucode',
                os.environ['MU300_TEST_RUNTIME_IMAGE'],'/test.uc'],capture_output=True,text=True,timeout=45)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_default_custom_and_power_hold_use_the_original_owner(self):
        source=SOURCE.read_text()
        block=source[source.index('const KEY_POWER'):source.index('// The existing LED helper owns')]
        prefix="""
const R='', BIN='/opt/mu300/bin',parts={};
let calls=[],custom_result=0,timers=[],settings={};
const uloop={timer:(ms,cb)=>{let t={ms:ms,run:cb,cancelled:false};t.cancel=()=>{t.cancelled=true;};push(timers,t);return t;}};
function flush(){let pending=timers;timers=[];for(let t in pending)if(!t.cancelled)t.run();}
function require(name){if(name!='uci')die('unexpected module');return {cursor:p=>({get:(config,section,key)=>settings[key],unload:()=>{}})};}
function num(k,v){return v;}
function readfile(p){return 'f50pro';}
function which(name){return '/opt/mu300/bin/'+name;}
function shq(s){return s;}
function popen(cmd,mode){return {read:()=> 'u30pro',close:()=>{}};}
function exists(p){return p=='/etc/openwrt_release';}
function rd(p){return '10.00';}
function digits(s){return true;}
function deadline(s,p){return null;}
function idle_check(){}
function log(tag,text){}
function spawn(argv,cb){
 push(calls,argv);if(cb)cb(argv[0]=='/usr/libexec/unisoc-modem/buttons'?custom_result:0);
 return null;
}
"""
        suffix="""
function check(yes,msg){if(!yes)die(msg);}
check(button_model()=='f50pro','shared platform masked F50 Pro product');
press(KEY_WIFI,'short');check(length(calls)==0,'fixed F50 Pro single invoked custom handler');
flush();check(length(calls)==0,'F50 Pro single was delayed');
press(KEY_WIFI,'short');press(KEY_WIFI,'short');check(length(calls)==0&&length(timers)==0,'unconfigured F50 double captured repeats');
settings.f50pro_button_double='data-switch';press(KEY_WIFI,'short');
check(timers[length(timers)-1].ms==250,'wrong double window');press(KEY_WIFI,'short');
check(length(calls)==1&&calls[0][1]=='double','double lost');
flush();calls=[];press(KEY_WIFI,'long');
check(length(calls)==1&&calls[0][1]=='long','hold lost');
calls=[];press(KEY_POWER,'long');check(length(calls)==0,'inherited power policy');
settings.f50pro_button_double='none';button_click_cancel();calls=[];press(KEY_WIFI,'short');press(KEY_WIFI,'short');
check(length(calls)==0,'disabled double still dispatched');
print('PASS F50 Pro fixed single and mapped double/hold');
"""
        with tempfile.TemporaryDirectory() as folder:
            test=Path(folder)/'events.uc';test.write_text(prefix+block+suffix)
            result=subprocess.run(['docker','run','--rm','--pull','never','--platform','linux/arm64','--network','none',
                '-v',str(test)+':/test.uc:ro','--entrypoint','/usr/bin/ucode',
                os.environ['MU300_TEST_RUNTIME_IMAGE'],'/test.uc'],capture_output=True,text=True,timeout=45)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':unittest.main()
