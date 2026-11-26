#!/usr/bin/ucode
// A shortcut still uses the existing data-SIM transaction and AT owner.
import * as fs from 'fs';
import * as ubus from 'ubus';
import * as uloop from 'uloop';
import { plan, current_state } from 'mu300.button-cycle';

if(trim(fs.readfile('/etc/mu300/model') || '')!='f50pro')exit(2);
let pipe=fs.popen('/opt/mu300/bin/mu300-physical-sim status','r');
if(!pipe)die('sim_read_failed\n');
let text=pipe.read('all'),status=pipe.close();
if(status)die('sim_read_failed\n');
let state;
try { state=json(text); } catch(e) { die('sim_read_failed\n'); }
pipe=fs.popen('/opt/mu300/bin/mu300-data-sim current','r');
if(!pipe)die('sim_read_failed\n');
const actual=trim(pipe.read('all') || ''),code=pipe.close();
if(code)die('sim_read_failed\n');
state=current_state(state,actual);
if(!state.ok)die(state.error+'\n');
const choice=plan(state,ARGV[0]);
if(!choice.ok)die(choice.error+'\n');
if(choice.target==null)exit(0);

const id=trim(fs.readfile('/proc/sys/kernel/random/uuid') || '');
const bus=ubus.connect();
function notify(stage) {
    if(!bus || !bus.event('f50pro.sim-switch',
        {id,stage,ordinal:choice.ordinal,colour:choice.colour}))
        warn('F50 Pro shortcut: signal lamp notification failed\n');
}
uloop.init();
let child,result=1,cancelled=false;
function cancel() {
    cancelled=true;
    if(child)system(['/bin/kill','-TERM',''+child.pid()]);
}
const term=uloop.signal(15,cancel),intr=uloop.signal(2,cancel);
notify('start');
child=uloop.process('/usr/libexec/unisoc-modem/data-sim',['apply','data',choice.target],null,(code)=>{
    result=code || cancelled?1:0;
    notify(result?'failed':'done');
    child=null;uloop.end();
});
if(!child) {
    notify('failed');die('Cannot start data SIM transaction\n');
}
uloop.run();
exit(result);
