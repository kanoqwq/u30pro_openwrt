'use strict';
// Real shared client: initial/changed data stack, manual override and no AT on
// discovery failure. No device, network or firmware writes.
const assert=require('assert'),fs=require('fs'),path=require('path');
const source=fs.readFileSync(path.join(__dirname,'../openwrt/luci-app-mu300/htdocs/luci-static/resources/mu300/common.js'),'utf8');
function fixture() {
 const storage=new Map([['mu300-view-slot','0']]),calls=[];
 let state={slots:2,saved_sim:0,actual_sim:1},pending=null,fail=false;
 const rpc={declare:o=>(...args)=>{
  calls.push([o.method,args]);
  if(o.method==='sim_get')return fail?Promise.reject(Error('unavailable')):pending || Promise.resolve({...state});
  return Promise.resolve({ok:1});
 }};
 const M=new Function('rpc','baseclass','L','sessionStorage',source)(rpc,{extend:o=>o},{env:{lang:'en'}},{
  getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)
 });
 return {M,calls,storage,set(v){state=v;},failure(v){fail=v;},defer(){let done;pending=new Promise(r=>done=r);return v=>{pending=null;done(v);};}};
}
(async()=>{
 const f=fixture(),{M}=f;
 let resolve=f.defer();
 const a=M.callAt('AT'),status=M.callStatus();
 assert.deepEqual(f.calls.map(x=>x[0]),['sim_get'],'parallel initial reads share one discovery');
 resolve({slots:2,saved_sim:0,actual_sim:1});await Promise.all([a,status]);
 assert.equal(M.selectedSlot(),'1','legacy implicit SIM1 default must not override actual data SIM');
 assert.deepEqual(f.calls.find(x=>x[0]==='at')[1],['AT','1']);
 assert.deepEqual(f.calls.find(x=>x[0]==='status')[1],['1']);
 f.set({slots:2,saved_sim:1,actual_sim:0});await M.callStatus();
 assert.equal(M.selectedSlot(),'0','automatic mode follows the actual, not saved stack');
 M.selectViewedSlot('1');f.calls.length=0;await M.callAt('AT+CSQ');
 assert.deepEqual(f.calls,[['at',['AT+CSQ','1']]],'explicit manual view remains independent and does not switch data');
 M.selectViewedSlot('auto');await M.callStatus();assert.equal(M.selectedSlot(),'0');
 M.selectViewedSlot('1',true);assert.equal(f.storage.get('mu300-view-choice'),'auto','successful data switch restores following');
 assert.equal(M.selectedSlot(),'1');
 f.set({slots:2,saved_sim:1,actual_sim:null});await M.callStatus();assert.equal(M.selectedSlot(),'1','saved intent is used while actual stack is not published');
 f.failure(true);f.calls.length=0;
 await assert.rejects(M.callAt('AT+CFUN?'),/unavailable/);
 assert.deepEqual(f.calls.map(x=>x[0]),['sim_get'],'failed discovery must not send an AT to an implicit SIM1');
 const single=fixture();single.set({slots:1,saved_sim:0,actual_sim:0});await single.M.callStatus();assert.equal(single.M.selectedSlot(),'0');
 const noSlot=fixture();noSlot.set({slots:2});await assert.rejects(noSlot.M.callAt('AT'),/temporarily unavailable/);
 assert(!noSlot.calls.some(x=>x[0]==='at'));
 const oneSource=fixture();oneSource.M.selectViewedSlot('1');
 oneSource.set({slots:2,saved_sim:0,actual_sim:0,physical:{model:'u30pro',supported:true,board_id:5,cards:[3],logical_cards:[3,null]}});
 await oneSource.M.callSimGet();
 assert.equal(oneSource.storage.get('mu300-view-choice'),'auto','a single-source board must not retain a nonexistent manual peer');
 assert.equal(oneSource.M.selectedSlot(),'0');
 console.log('PASS data SIM follow: initial SIM2, actual vs saved, concurrency, external change, manual view, restore auto, post-switch follow, failed discovery, single SIM');
})().catch(e=>{console.error(e);process.exitCode=1;});
