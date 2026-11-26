"""Real target ucode, ubus, worker processes and LED owner on private files."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import time
import unittest

TOP=Path(__file__).resolve().parents[1]
OVERLAY=TOP/'devices/f50pro/overlay'

class Runtime(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='f50pro-feedback-')
        self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.procs=[]
        self.addCleanup(self.stop)
        self.socket=str(self.root/'ubus.sock')
        self.paths=['-L',str(OVERLAY/'usr/share/ucode/*.uc'),'-L',str(TOP/'rootfs/overlay/usr/share/ucode/*.uc')]
        self.log=self.root/'log';self.logfile=self.log.open('w');self.addCleanup(self.logfile.close)
        Path('/var/run/ubus').mkdir(parents=True,exist_ok=True)
        self.start(['/sbin/ubusd','-s',self.socket])
        self.wait(lambda:Path(self.socket).exists())
        (self.root/'config').mkdir();(self.root/'config/system').write_text("config leds 'mu300_leds'\n")
        (self.root/'config/unisoc_modem').write_text("config modem 'main'\n")
        (self.root/'model').write_text('f50pro\n')
        run=self.root/'run';(run/'mu300-registration').mkdir(parents=True)
        (run/'f50pro-led-ready').touch();(run/'mu300-data-sim-actual').write_text('1\n')
        self.registration(False)
        self.leds=self.root/'leds'
        for name in ['net_red','net_green','net_blue','sc27xx:green','wifi_red','wifi_green','wifi_blue','sc27xx:red']:
            p=self.leds/name;p.mkdir(parents=True);(p/'brightness').write_text('0\n');(p/'trigger').write_text('none\n')
        server=self.root/'server.uc'
        server.write_text("""import * as uloop from 'uloop';import * as ubus from 'ubus';
uloop.init();const bus=ubus.connect(ARGV[0]);let events=[];
const ap=bus.publish('hostapd.wlan0',{get_status:{call:req=>req.reply({status:'ENABLED',freq:5180})}});
const test=bus.publish('test.events',{get:{call:req=>req.reply({events})}});
const listener=bus.listener('f50pro.sim-switch',(event,message)=>push(events,message));
uloop.run();""")
        self.start(['ucode',str(server),self.socket]);self.wait(lambda:self.rpc('test.events','get') is not None)
        daemon=(OVERLAY/'usr/sbin/f50pro-leds').read_text()
        daemon=daemon.replace("'/etc/mu300/model'",repr(str(self.root/'model')))
        daemon=daemon.replace("'/sys/class/leds/'",repr(str(self.leds)+'/'))
        daemon=daemon.replace("'/run/","'"+str(run)+'/')
        daemon=daemon.replace('ubus.connect()',f'ubus.connect({json.dumps(self.socket)})')
        daemon=daemon.replace('uci.cursor()',f'uci.cursor({json.dumps(str(self.root/"config"))})')
        daemon=daemon.replace('=>shortcut.event(message)',
            "=>{warn(sprintf('FEEDBACK event %J type=%s ordinal=%s\\n',message,type(message),type(message?.ordinal)));shortcut.event(message);}")
        (self.root/'daemon.uc').write_text(daemon)
        self.daemon=self.start(['ucode',*self.paths,str(self.root/'daemon.uc')])
        self.wait(lambda:self.level('net_blue')==1)
        state=dict(ok=1,supported=True,ready=True,model='f50pro',cards=[0,1,3,4],logical_cards=[0,1],active_card=0)
        (self.root/'state.json').write_text(json.dumps(state))
        source=self.root/'owner';source.write_text('#!/bin/sh\ncat '+shlex.quote(str(self.root/'state.json'))+'\n');source.chmod(0o755)
        apply=self.root/'apply';apply.write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$FEEDBACK_ROOT/applied"
if [ "$(cat "$FEEDBACK_ROOT/outcome")" = fail ]; then echo sim_not_ready >&2; exit 1; fi
''');apply.chmod(0o755)
        worker=(OVERLAY/'usr/libexec/unisoc-modem/f50pro-sim-key.uc').read_text()
        worker=worker.replace("'/etc/mu300/model'",repr(str(self.root/'model')))
        worker=worker.replace("'/opt/mu300/bin/mu300-physical-sim status'",json.dumps(shlex.quote(str(source))))
        # The modem's live data stack is authoritative over stale active_card.
        worker=worker.replace("'/opt/mu300/bin/mu300-data-sim current'","'printf 1'")
        worker=worker.replace("'/usr/libexec/unisoc-modem/data-sim'",repr(str(apply)))
        worker=worker.replace("'/proc/sys/kernel/random/uuid'",repr(str(self.root/'uuid')))
        worker=worker.replace('ubus.connect()',f'ubus.connect({json.dumps(self.socket)})')
        (self.root/'worker.uc').write_text(worker)

    def start(self,args,**kwargs):
        p=subprocess.Popen(args,stdout=self.logfile,stderr=self.logfile,**kwargs);self.procs.append(p);return p

    def stop(self):
        for p in reversed(self.procs):
            if p.poll() is None:p.terminate()
        for p in reversed(self.procs):
            try:p.wait(timeout=3)
            except subprocess.TimeoutExpired:p.kill();p.wait()

    def wait(self,predicate,timeout=8):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if predicate():return
            time.sleep(.01)
        self.fail('Fixture deadline: '+self.log.read_text())

    def rpc(self,obj,method,data=None):
        p=subprocess.run(['ubus','-s',self.socket,'-t','2','call',obj,method,json.dumps(data or {})],capture_output=True,text=True)
        return json.loads(p.stdout) if p.returncode==0 else None

    def event(self,name,data):
        self.events([(name,data)])

    def events(self,messages):
        # One sender avoids ARM emulator startup time consuming an entire burst.
        program="import {connect} from 'ubus';const bus=connect(ARGV[0]);for(let row in json(ARGV[1]))bus.event(row[0],row[1]);"
        subprocess.run(['ucode','-e',program,self.socket,json.dumps(messages)],check=True)

    def level(self,name):
        raw=(self.leds/name/'brightness').read_text().strip();return int(raw or 0)

    def registration(self,nr):
        (self.root/'run/mu300-registration/slot1.json').write_text(json.dumps(dict(slot=1,stat=1,rat=13 if nr else 7)))

    def monitor(self,seconds=3):
        counts={name:0 for name in ['net_red','net_green','sc27xx:green']};previous={}
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            for name in counts:
                on=self.level(name)>0
                if on and not previous.get(name):counts[name]+=1
                previous[name]=on
            time.sleep(.008)
        return counts

    def worker(self,outcome='ok',mode='list'):
        import uuid
        (self.root/'uuid').write_text(str(uuid.uuid4()))
        (self.root/'outcome').write_text(outcome)
        p=subprocess.Popen(['ucode',*self.paths,str(self.root/'worker.uc'),mode],env=dict(os.environ,FEEDBACK_ROOT=str(self.root)),
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.procs.append(p);return p

    def test_real_worker_success_and_refusal_events(self):
        for outcome,colour in [('ok','sc27xx:green'),('fail','net_red')]:
            with self.subTest(outcome=outcome):
                p=self.worker(outcome);counts=self.monitor()
                out,err=p.communicate(timeout=5)
                self.assertEqual(p.returncode,0 if outcome=='ok' else 1,out+err)
                self.assertEqual(counts[colour],3,str(counts)+'\n'+self.log.read_text())
                self.assertEqual(self.level('net_blue'),1)
                self.assertEqual(self.level('sc27xx:red'),127,'Wi-Fi bank unchanged')
                events=self.rpc('test.events','get')['events'][-2:]
                self.assertEqual([e['stage'] for e in events],['start','done' if outcome=='ok' else 'failed'])
                self.assertEqual(events[0]['ordinal'],3);self.assertEqual(events[0]['colour'],'white')
                self.assertEqual(events[0]['id'],events[1]['id'])
                if outcome=='fail':self.assertIn('sim_not_ready',err)
        self.assertEqual((self.root/'applied').read_text().splitlines(),['apply data f50pro-card-4']*2)

    def test_latest_request_preserves_events_and_restores_new_registration(self):
        self.events([('f50pro.sim-switch',dict(id='old',stage='start',ordinal=4,colour='white')),
                     ('f50pro.sim-switch',dict(id='new',stage='start',ordinal=2,colour='green')),
                     ('f50pro.sim-switch',dict(id='old',stage='failed'))])
        counts=self.monitor(1.8)
        self.assertEqual(counts['net_green'],2,str(counts)+'\n'+self.log.read_text());self.assertEqual(counts['net_red'],0,counts)
        self.registration(True)
        self.events([('f50pro.sim-switch',dict(id='latest',stage='start',ordinal=2,colour='green')),
                     ('mu300.registration',{})])
        counts=self.monitor(1.8)
        self.assertEqual(counts['net_green'],2,counts)
        self.assertEqual(self.level('sc27xx:green'),255,'latest NR signal restored')
        self.assertEqual(self.level('sc27xx:red'),127,'Wi-Fi stayed active')

    def test_disabled_lamp_and_invalid_state_do_not_gain_side_effects(self):
        (self.root/'config/system').write_text("config leds 'mu300_leds'\n option signal '0'\n")
        self.event('f50pro.config',{});self.wait(lambda:self.level('net_blue')==0)
        self.event('f50pro.sim-switch',dict(id='off',stage='start',ordinal=2,colour='green'))
        self.assertEqual(sum(self.monitor(1.6).values()),0)
        state=json.loads((self.root/'state.json').read_text());state['ready']=False
        (self.root/'state.json').write_text(json.dumps(state))
        p=self.worker();out,err=p.communicate(timeout=5)
        self.assertNotEqual(p.returncode,0);self.assertFalse((self.root/'applied').exists())

    def test_existing_boot_wifi_and_config_lifecycles(self):
        daemon=(OVERLAY/'usr/sbin/f50pro-leds').read_text()
        daemon='\n'.join(line for line in daemon.splitlines() if not line.startswith(('#!','import ')))
        program=self.root/'legacy.uc'
        program.write_text("import { colours,output,boot_colours } from 'mu300.f50pro-led';\n"+
                           "import { feedback } from 'mu300.f50pro-feedback';\n"+
                           (TOP/'tests/f50pro_led_lifecycle.uc').read_text()+'\n'+daemon+'\n')
        for case in ['boot','ready','disabled','race','wireless']:
            p=subprocess.run(['ucode',*self.paths,str(program),case],capture_output=True,text=True,timeout=6)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)

    def test_launch_failure_and_owner_stop_restore(self):
        (self.root/'apply').unlink()
        p=self.worker();counts=self.monitor()
        out,err=p.communicate(timeout=5)
        self.assertEqual(p.returncode,1,out+err);self.assertEqual(counts['net_red'],3,counts)
        self.event('f50pro.sim-switch',dict(id='stop-owner',stage='start',ordinal=5,colour='white'))
        self.wait(lambda:self.level('sc27xx:green')>0)
        self.daemon.terminate();self.daemon.wait(timeout=5)
        self.assertEqual(self.level('net_blue'),1,'owner stop restores signal')
        self.assertEqual(self.level('sc27xx:red'),127,'owner stop preserves Wi-Fi')

    def test_cancel_reaches_original_transaction_before_failure_feedback(self):
        script=self.root/'apply'
        body=script.read_text().split('\n',1)[1]
        script.write_text('''#!/bin/sh
trap 'echo cancelled > "$FEEDBACK_ROOT/cancelled"; exit 143' TERM
'''+body+'sleep 1\n')
        p=self.worker();self.wait(lambda:(self.root/'applied').exists())
        p.terminate();counts=self.monitor(3)
        out,err=p.communicate(timeout=5)
        self.assertEqual(p.returncode,1,out+err)
        self.assertTrue((self.root/'cancelled').exists(),err)
        self.assertEqual(counts['net_red'],3,counts)
        self.assertEqual(self.level('net_blue'),1)

if __name__=='__main__':
    import sys
    paths=['-L',str(OVERLAY/'usr/share/ucode/*.uc'),'-L',str(TOP/'rootfs/overlay/usr/share/ucode/*.uc')]
    subprocess.run(['ucode',*paths,str(TOP/'tests/f50pro_feedback.uc')],check=True)
    result=unittest.main(verbosity=2,exit=False)
    if not result.result.wasSuccessful():sys.exit(1)
    subprocess.run([sys.executable,'-m','unittest','-v','test_button_cycle',
        'test_configurable_buttons.Buttons.test_physical_button_cycles_every_form_option_through_existing_apply',
        'test_configurable_buttons.Buttons.test_f50pro_selected_pair_policy_keeps_both_sources'],
        cwd=TOP/'tests',env=dict(os.environ,MU300_TEST_UCODE='/usr/bin/ucode'),check=True)
