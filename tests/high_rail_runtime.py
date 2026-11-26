"""Offline Pro rail tests: actual ucode owner, private ubus and bridge protocol."""
import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from helpers import TOP, ucode, ucode_paths
from native_dashboard_fixture import Snapshot
from test_modemd import ModemdUbus, UBUS, wait_for


class StateTests(unittest.TestCase):
    def test_strict_events_and_no_replay(self):
        program = r'''
import { tracker } from 'mu300.high-rail';
let events=[],t=tracker(true,s=>push(events,s));
function check(known,active) {
    let s=t.snapshot();if(s.known!==known || s.active!==active)die(sprintf('%J',s));
}
check(false,false);
for(let channel in ['stty_nr3','stty_nr1'])t.ingest(channel,'+SPHIGHRAILINFO: 1');
for(let line in ['+SPHIGHRAILINFO: 2','+SPHIGHRAILINFO: -1','+SPHIGHRAILINFO: 1,0','x+SPHIGHRAILINFO: 1'])t.ingest('stty_nr0',line);
check(false,false);
t.ingest('stty_nr0','+SPHIGHRAILINFO: 1');check(true,true);
t.ingest('stty_nr0','+SPHIGHRAILINFO: 1');if(length(events)!=1)die('duplicate');
let copy=t.snapshot();copy.active=false;check(true,true);
t.ingest('stty_nr0','+SPHIGHRAILINFO: 0');check(true,false);
t.reset();check(false,false);
t=tracker(true,s=>{});check(false,false);
let unsupported=tracker(false,s=>die('unsupported event'));
unsupported.ingest('stty_nr0','+SPHIGHRAILINFO: 1');
if(unsupported.snapshot().supported || unsupported.snapshot().active)die('unsupported');
for(let i=0;i<20000;i++) {t.ingest('stty_nr0','+SPHIGHRAILINFO: 1');t.ingest('stty_nr0','+SPHIGHRAILINFO: 0');}
check(true,false);print('ok');
'''
        p=subprocess.run(ucode()+ucode_paths()+['-e',program],capture_output=True,text=True,timeout=30)
        self.assertEqual((p.returncode,p.stdout),(0,'ok'),p.stderr)

    def test_dashboard_whole_device_and_unavailable(self):
        with tempfile.TemporaryDirectory() as d:
            f=Snapshot(d);f.write('etc/mu300/platform','u30pro\n')
            for model in ['u30pro','f50pro']:
                f.write('etc/mu300/model',model+'\n')
                for active in [True,False]:
                    state={'supported':True,'known':True,'active':active}
                    f.responses['mu300.modem.high_rail']=state
                    for slot in ['0','1']:
                        self.assertEqual(f.run(slot=slot)['modem']['high_rail'],state)
            for state in [None,{}, {'supported':True,'known':False,'active':True},
                          {'supported':True,'known':True,'active':'1'}]:
                f.responses['mu300.modem.high_rail']=state
                self.assertFalse(f.run()['modem']['high_rail']['active'])
            f.write('etc/mu300/platform','mu300\n')
            f.responses['mu300.modem.high_rail']={'supported':True,'known':True,'active':True}
            self.assertFalse(f.run()['modem']['high_rail']['supported'])


class OwnerTests(ModemdUbus):
    def rail_start(self):
        self.start(f'name=nr0,dev=/dev/stty_nr0,dir={self.run_root}/mu300-at2',
                   f'name=nr3,dev=/dev/stty_nr3,dir={self.run_root}/mu300-at5')
        self.ready('stty_nr0');self.wait_object()

    def state(self):
        return self.ubus('call','mu300.modem','high_rail')

    def active(self,value):
        self.bridge.rx('stty_nr0','+SPHIGHRAILINFO: '+str(int(value)))
        self.assertTrue(wait_for(lambda:self.state()==dict(supported=True,known=True,active=value)))

    def test_live_dispatch_and_commands(self):
        self.rail_start()
        self.assertEqual(self.state(),dict(supported=True,known=False,active=False))
        listen=subprocess.Popen([UBUS,'-s',str(self.ubus_sock),'listen','mu300.modem.high_rail'],stdout=subprocess.PIPE,text=True)
        try:
            time.sleep(.2)
            self.active(True)
            self.bridge.rx('stty_nr3','+SPHIGHRAILINFO: 0')
            self.bridge.send('DROPPED stty_nr3 1')
            time.sleep(.1);self.assertTrue(self.state()['active'])
            self.table['AT+CSQ']=['+SPHIGHRAILINFO: 0','+CSQ: 20,99','OK']
            reply=self.ubus('call','mu300.modem','at',json.dumps({'channel':'nr0','cmd':'AT+CSQ','timeout':2}))
            self.assertEqual(reply['ok'],1)
            self.assertIn('+CSQ: 20,99',reply['reply'])
            self.assertTrue(wait_for(lambda:not self.state()['active']))
            # The indication does not generate a query or change command selection.
            self.assertEqual(self.bridge.tx[-1],('stty_nr0','AT+CSQ\r'))
        finally:
            listen.terminate();out=listen.communicate(timeout=5)[0]
        events=[json.loads(l)['mu300.modem.high_rail'] for l in out.splitlines() if l.strip()]
        self.assertEqual([e['active'] for e in events],[True,False])

    def test_transport_faults_invalidate(self):
        self.rail_start()
        for record in ['EOF stty_nr0','OPENFAIL stty_nr0 5','DROPPED stty_nr0 1',
                       'STATE stty_nr0 /dev/stty_nr0 closed','HELLO 1 123']:
            self.active(True);self.bridge.send(record)
            self.assertTrue(wait_for(lambda:self.state()==dict(supported=True,known=False,active=False)),record)
        self.active(True)
        self.bridge.conn.shutdown(2)
        self.assertTrue(wait_for(lambda:self.bridge.connections>=2))
        self.assertTrue(wait_for(lambda:self.state()==dict(supported=True,known=False,active=False)))

    def test_sustained_events_without_commands(self):
        self.rail_start();self.bridge.tx.clear()
        for i in range(1000):
            self.bridge.rx('stty_nr0','+SPHIGHRAILINFO: '+str(i%2))
        self.assertTrue(wait_for(lambda:self.state()['active'] is True))
        self.active(False)
        self.assertEqual(self.bridge.tx,[])

    def test_screen_feed_live_events_and_owner_loss(self):
        self.rail_start();owner=self.procs[-1]
        received=self.tmp/'feeds.jsonl'
        server=self.tmp/'panel.uc'
        server.write_text('''import * as fs from 'fs';import * as loop from 'uloop';import {connect} from 'ubus';
loop.init();const bus=connect(getenv('MU300_UBUS_SOCKET')),output=ARGV[0];
const panel=bus.publish('u30pro.panel',{
 status:{call:req=>req.reply({screen_on:true})},
 feed:{args:{data:{},partial:false},call:(req,msg)=>{
   msg ??= req.args;
   let f=fs.open(output,'a');if(!f)die('Cannot open panel fixture output: '+output);
   if(!msg.data.cell_state && msg.partial!==true)die('Event feed must preserve other panel fields');
   f.write(sprintf('%J\\n',msg.data));f.close();req.reply({ok:true});}}
});
const dash=bus.publish('mu300dash',{
 sim_get:{call:req=>req.reply({})},
 sms_list:{args:{page:'',slot:''},call:req=>req.reply({msgs:[]})}
});
let pending;
const charge=bus.publish('mu300-charge',{get:{call:req=>{
 if(fs.stat(output+'.race')) {
   fs.unlink(output+'.race');fs.writefile(output+'.requested','1');req.defer();
   pending=loop.timer(800,()=>{req.reply({});pending=null;});
 } else req.reply({});
}}});
loop.run();''')
        (self.tmp/'dash.uc').write_text('''export function info(slot,bus,cfg) {
return {modem:{alive:1,data_sim:0,high_rail:bus.call('mu300.modem','high_rail',{})},
wan:{up:false,device:'sipa_eth0'},wifi:{clients:[]},net:{}};};
export function status(slot,cells,bus,cfg) {return {};};''')
        (self.tmp/'wifi.uc').write_text('export function status(cfg,bus){return {};};')
        (self.tmp/'carrier.uc').write_text('export function carrier_name(op){return op;};')
        source=(TOP/'devices/u30pro/overlay/usr/sbin/u30pro-ui-feed').read_text()
        source=source.replace("from 'mu300.dash'","from './dash.uc'").replace("from 'mu300.wifi-native'","from './wifi.uc'")
        source=source.replace("from 'mu300.carrier'","from './carrier.uc'")
        source=source.replace('connect(null,3)',"connect(getenv('MU300_UBUS_SOCKET'),3)")
        source=source.replace('/run/u30pro-cellular',str(self.tmp/'cellular'))
        feeder=self.tmp/'feed.uc';feeder.write_text(source)
        env=dict(self.env,MU300_UBUS_SOCKET=str(self.ubus_sock))
        def spawn(path,*args):
            p=subprocess.Popen(ucode()+ucode_paths()[2:]+[str(path),*map(str,args)],env=env,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            self.procs.append(p);return p
        spawn(server,received)
        self.assertTrue(wait_for(lambda:self.ubus('call','u30pro.panel','status')=={'screen_on':True}))
        spawn(feeder)
        def last():
            if received.exists():
                rows=received.read_text().splitlines()
                if rows:return json.loads(rows[-1]).get('high_rail')
        self.assertTrue(wait_for(lambda:last()=='0'))
        self.active(True);self.assertTrue(wait_for(lambda:last()=='1'))
        self.active(False);self.assertTrue(wait_for(lambda:last()=='0'))
        self.active(True);self.assertTrue(wait_for(lambda:last()=='1'))
        # Exit while a full feed is waiting on another RPC: the old true
        # snapshot must not be allowed to resurrect the icon afterwards.
        start=len(received.read_text().splitlines())
        Path(str(received)+'.race').write_text('1')
        self.assertTrue(wait_for(lambda:Path(str(received)+'.requested').exists()))
        self.active(False)
        def race_rows():
            return [json.loads(row) for row in received.read_text().splitlines()[start:]]
        self.assertTrue(wait_for(lambda:any('cell_connected' in row and row.get('high_rail')=='0' for row in race_rows())))
        rows=race_rows();exit_index=next(i for i,row in enumerate(rows) if row.get('high_rail')=='0')
        self.assertTrue(all(row.get('high_rail')!='1' for row in rows[exit_index:]))
        self.active(True);self.assertTrue(wait_for(lambda:last()=='1'))
        owner.terminate();owner.wait(5)
        self.assertTrue(wait_for(lambda:last()=='0'))


if __name__=='__main__':
    unittest.main(defaultTest=['StateTests','OwnerTests.test_live_dispatch_and_commands',
        'OwnerTests.test_transport_faults_invalidate','OwnerTests.test_sustained_events_without_commands',
        'OwnerTests.test_screen_feed_live_events_and_owner_loss'],verbosity=2)
