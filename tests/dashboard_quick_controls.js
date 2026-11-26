'use strict';
const assert = require('assert'), fs = require('fs'), path = require('path');
const source = fs.readFileSync(process.argv[2] || path.join(__dirname, '../openwrt/luci-app-mu300/htdocs/luci-static/resources/view/mu300/home.js'), 'utf8');
const tick = async () => { for (let i=0; i<20; i++) await Promise.resolve(); };
function fixture(on) {
    const buttons = {}, requests = [], dialogs = [];
    let decide, complete, finishJob, rejectJob;
    const jobs=[], toasts=[];
    const element = id => buttons[id] || (buttons[id] = {disabled:false, style:{}, addEventListener(){}});
    const root = {isConnected:true, querySelectorAll(){return [];}, querySelector:element};
    const M = {
        v(id) { return element('#mud-'+id); },
        set(id,text) { element('#mud-'+id).textContent=text; },
        translate(text) { return text; },
        confirmBox(title,body,options) { dialogs.push({title,body,options}); return new Promise(resolve => { decide=resolve; }); },
        choiceBox(title,body,choices) { dialogs.push({title,body,choices}); return new Promise(resolve => { decide=resolve; }); },
        callAct(op,arg) { requests.push([op,arg]); return new Promise(resolve => { complete=resolve; }); },
        busy(btn,on) { btn.busy=on; }, toast(message,options){toasts.push({message,options});}
    };
    const view = new Function('view','uci','R','M','L','SimRadio',source)(
        {extend:o=>o},{},{},M,{resolveDefault:p=>p.catch(()=>undefined)},
        {wait:(job,active)=>{jobs.push(job);return new Promise((resolve,reject)=>{finishJob=()=>resolve(active()?{ok:1,state:'done'}:null);rejectJob=reject;});}});
    view.refreshLock = () => {};
    view.wire(root);
    view.lastInfo = {wan:{up:on},wifi:{available:1,up:on,pending:false}};
    view.lastCell = {cfun:on?1:0};
    return {view,root,buttons,requests,dialogs,decide:v=>decide(v),complete:(r)=>complete(r||{ok:1}),jobs,toasts,finishJob:()=>finishJob(),rejectJob:e=>rejectJob(e)};
}
(async()=>{
    const cases = [
        ['data',true,'data','down'], ['data',false,'data','up'],
        ['radio',true,'radio','off'], ['radio',false,'radio','on'],
        ['wifi',true,'wifi','off'], ['wifi',false,'wifi','on'],
        ['modem',true,'modem-reset',null], ['android',true,'os','android'],
        ['pro-default',true,'os','linux-default']
    ];
    for (const [id,on,op,arg] of cases) {
        for (const decision of ['cancel','confirm','unload','detach']) {
            const f=fixture(on), button=f.buttons['#mud-btn-'+id];
            button.onclick();
            assert.equal(f.dialogs.length,1,id);
            assert.equal(f.requests.length,0,id+' executed before confirmation');
            button.onclick(); f.buttons['#mud-btn-reboot'].onclick();
            assert.equal(f.dialogs.length,1,'duplicate confirmation');
            if (decision==='unload') f.view.unload();
            if (decision==='detach') f.root.isConnected=false;
            // Even if polling changes state, send only the explicit confirmed target.
            f.view.lastInfo.wan.up=!on; f.view.lastCell.cfun=on?0:1;
            f.view.lastInfo.wifi.up=!on;
            f.decide(decision!=='cancel'); await tick();
            if (decision==='confirm') {
                assert.deepEqual(f.requests,[[op,arg]],id);
                button.onclick(); assert.equal(f.requests.length,1,'duplicate in-flight request');
                assert(button.busy);
                f.complete(); await tick();
                assert(!button.busy && !button.disabled,id+' left busy');
            } else assert.equal(f.requests.length,0,id+' must not execute after '+decision);
            assert(!f.view._quickPending,id+' left confirmation locked');
        }
    }
    for (const op of ['poweroff','reboot']) {
        for (const decision of ['cancel','confirm','unload','detach','error']) {
            const f=fixture(true), button=f.buttons['#mud-btn-reboot'];
            button.onclick();
            assert.equal(f.dialogs.length,1);
            assert.deepEqual(f.dialogs[0].choices.map(c=>c.value),[undefined,'poweroff','reboot']);
            assert.equal(f.requests.length,0,'power request before choosing');
            button.onclick();f.buttons['#mud-btn-data'].onclick();
            assert.equal(f.dialogs.length,1,'duplicate power chooser');
            if(decision==='unload') f.view.unload();
            if(decision==='detach') f.root.isConnected=false;
            f.decide(decision==='cancel'?undefined:op);await tick();
            if(decision==='confirm'||decision==='error') {
                assert.deepEqual(f.requests,[[op,null]],'wrong power operation');
                button.onclick();assert.equal(f.requests.length,1);
                assert(button.busy && f.view._quickPending);
                f.complete(decision==='error'?{ok:0,error:'unavailable'}:{ok:1,started:1,op});await tick();
                assert(!button.busy && !f.view._quickPending,'power action left busy');
                assert.equal(f.toasts.at(-1).options.type,decision==='error'?'error':'success');
            } else {
                assert.equal(f.requests.length,0,'power executed after '+decision);
                assert(!f.view._quickPending);
            }
        }
    }
    for(const outcome of ['done','error','leave']) {
        const f=fixture(true),b=f.buttons['#mud-btn-radio'];
        b.onclick();f.decide(true);await tick();
        f.complete({ok:1,id:'rf-job'});await tick();
        assert(b.busy && f.view._quickPending,'RF submission released controls before completion');
        assert.equal(f.jobs.length,1);
        const before=f.toasts.length;
        if(outcome==='leave')f.view.unload();
        if(outcome==='error')f.rejectJob(new Error('modem_busy'));else f.finishJob();
        await tick();
        assert(!b.busy && !f.view._quickPending);
        if(outcome==='leave')assert.equal(f.toasts.length,before,'late RF toast after leaving');
        else assert.equal(f.toasts.at(-1).options.type,outcome==='done'?'success':'error');
    }
    for(const state of ['pending','unavailable','busy']) {
        const f=fixture(true);
        if(state==='pending')f.view.lastInfo.wifi.pending=true;
        if(state==='unavailable')f.view.lastInfo.wifi.available=0;
        if(state==='busy')f.view._wifiBusy=true;
        f.buttons['#mud-btn-wifi'].onclick(); assert.equal(f.dialogs.length,0,state);
    }
    const f=fixture(true), node=id=>f.root.querySelector('#mud-'+id);
    const markup=f.view.html();
    const androidIndex=markup.indexOf('id="mud-btn-android"');
    const defaultIndex=markup.indexOf('id="mud-btn-pro-default"');
    const statusIndex=markup.indexOf('id="mud-boot-switch"');
    assert(0<=androidIndex && androidIndex<defaultIndex && defaultIndex<statusIndex);
    assert(markup.indexOf('快捷控制')<androidIndex && statusIndex<markup.indexOf('<h3>邻区'));
    const boot={system_switch:'u30pro',default:'android',next:'linux',temporary:true,can_set_default:true};
    const paint=()=>{
        f.view.lastInfo={boot,capabilities:{dualboot:1}};
        f.view.paintBoot(f.view.lastInfo);
    };
    paint();
    assert(!node('boot-switch').hidden && node('boot-notice').hidden);
    assert.equal(node('btn-android').style.display,'');
    assert.equal(node('boot-current-label').textContent,'当前系统 / 下次启动');
    assert.equal(node('boot-default').textContent,'原厂 Android');
    assert(!node('boot-default-row').hidden && node('boot-next-row').hidden);
    assert.equal(node('boot-temporary').textContent,'是');
    assert.equal(node('boot-control').textContent,'可写入');
    assert(!node('btn-pro-default').hidden && !node('btn-pro-default').disabled);
    node('btn-android').onclick();
    assert.equal(f.requests.length,0);
    assert.match(f.dialogs[0].body,/USB.*临时启动已安装的 OpenWrt/);
    f.decide(true); await tick();
    assert.deepEqual(f.requests,[['os','android']]);
    f.complete(); await tick();
    boot.next='android'; paint();
    assert.equal(node('boot-default-label').textContent,'默认启动 / 下次启动');
    assert(!node('boot-default-row').hidden && node('boot-next-row').hidden);
    boot.default='linux'; boot.next='linux'; boot.temporary=false; paint();
    assert(node('btn-pro-default').hidden && node('btn-pro-default').disabled);
    assert.equal(node('boot-current-label').textContent,'当前系统 / 默认启动 / 下次启动');
    assert(node('boot-default-row').hidden && node('boot-next-row').hidden);
    boot.next='android'; paint();
    assert(!node('btn-pro-default').hidden && !node('btn-pro-default').disabled);
    boot.next=null; boot.can_set_default=false; paint();
    assert.equal(node('boot-next').textContent,'未确认');
    assert(!node('boot-next-row').hidden && node('btn-android').disabled);
    assert(node('btn-pro-default').hidden && node('btn-pro-default').disabled);
    f.view.paintBoot({boot:{temporary:true,can_set_default:true},capabilities:{dualboot:1}});
    assert(node('boot-switch').hidden && !node('boot-notice').hidden);
    assert(node('btn-pro-default').hidden && !node('btn-android').disabled);
    console.log('PASS: quick controls, power chooser and U30 Pro boot dashboard');
})().catch(e=>{console.error(e);process.exitCode=1;});
