'use strict';
const fs=require('fs'),path=require('path'),assert=require('assert');
const dir=path.resolve(__dirname,'../openwrt/luci-app-mu300/htdocs/luci-static/resources');
const store=new Map(), session={getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v)};
let called=[];
const common=new Function('rpc','baseclass','L','document','navigator','sessionStorage',fs.readFileSync(dir+'/mu300/common.js','utf8'))(
    {declare:o=>(...args)=>{called.push([o.method,args]); return Promise.resolve({});}},
    {extend:o=>o},{env:{lang:'en'}},{},{},session);
assert.equal(common.selectedSlot(),'0');
common.selectViewedSlot(1); assert.equal(common.selectedSlot(),'1');
assert.equal(common.selectViewedSlot(2),false); assert.equal(common.selectedSlot(),'1');
common.callAt('AT'); common.selectViewedSlot(0);
assert.deepEqual(called[0],['at',['AT','1']]);
for(const [routes,names] of [[[0,4],['Built-in SIM 1','External SIM 1']],[[3,4],['External SIM 2','External SIM 1']],[[0,1],['Built-in SIM 1','Built-in SIM 2']]]) {
    const info={physical:{model:'f50pro',ready:true,logical_cards:routes}};
    for(const slot of [0,1])assert.equal(common.slotName(slot,info),names[slot]);
}
assert.equal(common.slotName(1,{physical:{model:'u30pro',ready:true,logical_cards:[3,4]}}),'SIM 2');
assert.equal(common.slotName(0,{physical:{model:'u30pro',ready:false,logical_cards:[3,2]}}),'External SIM 1');
assert.equal(common.slotName(1,{physical:{model:'v50',ready:true,logical_cards:[3,2]}}),'Built-in SIM 3');
for(const [board,cards] of Object.entries(JSON.parse(fs.readFileSync(path.resolve(__dirname,'../devices/u30pro/board-topology.json'),'utf8')).board_cards)) {
    for(const chip of [0,1])for(const psim of [0,1]) {
        const routes=[psim?3:0,chip?2:1].map(id=>cards.includes(id)?id:null);
        const info={slots:2,physical:{model:'u30pro',supported:true,board_id:Number(board),cards,logical_cards:routes}};
        for(const slot of [0,1]) {
            const id=routes[slot];
            assert.equal(common.slotName(slot,info),id==null?'SIM '+(slot+1):id===3?'External SIM 1':'Built-in SIM '+(id+1));
            assert.equal(common.slotSupported(slot,info),cards.some(id=>(id===0||id===3?0:1)===slot));
        }
    }
}

function element(tag) {return {tag,children:[],style:{},isConnected:true,append(...n){this.children.push(...n);}};}
function find(root,tag){return root.tag===tag?root:root.children.map(n=>find(n,tag)).find(Boolean);}
const tick=async()=>{for(let i=0;i<30;i++)await Promise.resolve();};
(async()=>{
    for(const outcome of ['cancel','error','done']) {
        common.selectViewedSlot('0'); let requests=0;
        const M={injectCss(){},localizeMenu(){},translate:s=>s,selectViewedSlot:common.selectViewedSlot,
            confirmBox:()=>Promise.resolve(outcome!=='cancel'),busy:(b,v)=>b.busy=v,toast:()=>({close(){}})};
        const rpc={declare:o=>()=>{
            if(o.method==='data_sim_set'){requests++;return Promise.resolve({ok:1,id:'abcdefghij'});}
            if(o.method==='data_sim_status')return Promise.resolve({id:'abcdefghij',state:outcome,ok:outcome==='done',error:'rejected'});
            return Promise.resolve({ok:1,saved_sim:1,actual_sim:1,data_connected:false});
        }};
        const view=new Function('view','rpc','poll','M','document','SimRadio',fs.readFileSync(dir+'/view/mu300/sim.js','utf8'))(
            {extend:o=>o},rpc,{add(){},remove(){}},M,{createElement:element},{attach:()=>({refresh:()=>Promise.resolve(),dispose(){}})});
        const root=view.render([{slots:2},{ok:1,ready:true,saved_sim:0,actual_sim:0}]);
        const section=find(root,'section'), row=find(section,'select');
        assert(root.className.includes('mud-sim-page'));
        assert(find(section,'h3'), 'heading belongs inside the card');
        assert.equal(find(section,'label').htmlFor,row.id);
        assert.equal(find(section,'button').type,'button');
        assert(find(root,'style').textContent.includes('@media(max-width:480px)'));
        find(root,'select').value='1';find(root,'button').onclick();await tick();
        assert.equal(common.selectedSlot(),outcome==='done'?'1':'0',outcome);
        assert.equal(requests,outcome==='cancel'?0:1);
        assert(!view.busy && !find(root,'button').busy,outcome+' left loading active');
        view.unload();
    }
    {
        common.selectViewedSlot('0');
        const state={ok:1,ready:false,saved_sim:0,actual_sim:0,data_connected:true};
        const requests=[];
        const M={injectCss(){},localizeMenu(){},translate:s=>s,
            selectViewedSlot:common.selectViewedSlot,
            confirmBox:()=>Promise.resolve(true),busy:(b,v)=>b.busy=v,toast:()=>({close(){}})};
        const rpc={declare:o=>(target)=>{
            if(o.method==='data_sim_get')return Promise.resolve({...state});
            if(o.method==='data_sim_set') {
                requests.push(target);
                state.actual_sim=Number(target);state.saved_sim=Number(target);
                return Promise.resolve({ok:1,id:'abcdefghij'});
            }
            return Promise.resolve({id:'abcdefghij',state:'done',ok:1});
        }};
        const view=new Function('view','rpc','poll','M','document','SimRadio',fs.readFileSync(dir+'/view/mu300/sim.js','utf8'))(
            {extend:o=>o},rpc,{add(){},remove(){}},M,{createElement:element},{attach:()=>({refresh:()=>Promise.resolve(),dispose(){}})});
        const root=view.render([{slots:2},{...state}]);
        function all(n,tag){return (n.tag===tag?[n]:[]).concat(...n.children.map(c=>all(c,tag)));}
        const buttons=all(root,'button');
        assert.equal(buttons.length,1,'U30 has no separate hot-switch policy controls');
        const switchButton=buttons[0], select=find(root,'select');
        assert(switchButton.disabled,'uninitialized dual stacks require cold boot');
        assert(!select.disabled);
        state.ready=true;await view.refresh();
        assert(!switchButton.disabled,'ready state must enable the live control without a page reload');
        select.value='1';switchButton.onclick();await tick();
        assert.deepEqual(requests,['1']);
        assert.equal(common.selectedSlot(),'1');
        view.unload();
    }
    for(const [model,board,cards,target] of [['v50',0,[0,1,2],2],['v50',1,[0,1,2,3],3],['v50',2,[0,1,3],3],['v50',3,[0,1],1],['u30pro',0,[0,1,2,3],3],['u30pro',1,[0,1,2],2],['u30pro',2,[0,1],1],['u30pro',3,[0,1,3],3],['u30pro',4,[0,1,2,3],2],['u30pro',5,[3],3],['u30pro',6,[0,2],2],['f50pro',0,[0,1,2],2],['f50pro',1,[0,1],1],['f50pro',2,[0,2],2],['f50pro',3,[0,2,3,4],4],['f50pro',4,[0,1,3,4],4],['f50pro',4,[0,1,3,4],3],['f50pro',5,[3,4],4],['f50pro',5,[3,4],3]]) {
        common.selectViewedSlot('0');const requests=[],confirmations=[];
        const physical={ok:1,supported:true,ready:true,model,board_id:board,cards,active_card:0,saved_card:0,logical_cards:model==='f50pro'?[cards.includes(0)?0:3,cards.includes(1)?1:cards.includes(2)?2:4]:[]};
        const M={injectCss(){},localizeMenu(){},translate:s=>s,selectViewedSlot:common.selectViewedSlot,
            confirmBox:(title,body)=>{confirmations.push(body);return Promise.resolve(true);},busy(){},toast:()=>({close(){}})};
        const rpc={declare:o=>arg=>{
            if(o.method==='physical_sim_get')return Promise.resolve({...physical});
            if(o.method==='data_sim_set') {
                requests.push(arg);physical.active_card=physical.saved_card=target;
                return Promise.resolve({ok:1,id:'abcdefghij'});
            }
            if(o.method==='data_sim_status')return Promise.resolve({id:'abcdefghij',state:'done',ok:1});
            return Promise.resolve({ok:1,ready:true,actual_sim:0,saved_sim:0});
        }};
        const view=new Function('view','rpc','poll','M','document','SimRadio',fs.readFileSync(dir+'/view/mu300/sim.js','utf8'))(
            {extend:o=>o},rpc,{add(){},remove(){}},M,{createElement:element},{attach:()=>({refresh:()=>Promise.resolve(),dispose(){}})});
        const root=view.render([{slots:2},{ok:1,ready:true,actual_sim:0,saved_sim:0},{...physical}]);
        function all(n,tag){return (n.tag===tag?[n]:[]).concat(...n.children.map(c=>all(c,tag)));}
        const select=all(root,'select').find(n=>n.id==='mud-v50-card');
        const expected=model==='f50pro'?cards.filter(n=>n<3).concat(cards.includes(4)?[4]:[],cards.includes(3)?[3]:[]):cards;
        assert.deepEqual(select.children.map(n=>Number(n.value)),expected,'board-specific physical choices');
        if(model==='f50pro')for(const [id,label] of [[4,'外置 SIM 1'],[3,'外置 SIM 2']]) {
            const option=select.children.find(n=>Number(n.value)===id);
            if(option)assert.equal(option.textContent,label,'official external numbering must not become a different AT stack');
        }
        if(model==='u30pro')for(const option of select.children)
            assert.equal(option.textContent,Number(option.value)===3?'外置 SIM 1':'内置 SIM '+(Number(option.value)+1));
        if(model==='f50pro') {
            const source0=all(root,'select').find(n=>n.id==='mud-f50-source0');
            const source1=all(root,'select').find(n=>n.id==='mud-f50-source1');
            assert.deepEqual(source0.children.map(n=>Number(n.value)),cards.filter(n=>n===0||n===3));
            assert.deepEqual(source1.children.map(n=>Number(n.value)),cards.filter(n=>n!==0&&n!==3));
        }
        const button=all(root,'button')[1];select.value=String(target);button.onclick();await tick();
        assert.deepEqual(requests,[model+'-card-'+target]);
        if(model==='f50pro' && target>=3)assert.deepEqual(confirmations,[target===4?'外置 SIM 1':'外置 SIM 2']);
        assert.equal(common.selectedSlot(),target===0||target===3?'0':'1','physical IDs never become AT slot IDs');
        if(model==='f50pro') {
            const source0=all(root,'select').find(n=>n.id==='mud-f50-source0');
            const source1=all(root,'select').find(n=>n.id==='mud-f50-source1');
            const first=cards.includes(3)?3:0,second=cards.includes(4)?4:cards.includes(1)?1:2;
            source0.value=String(first);source1.value=String(second);
            requests.length=0;
            all(root,'button').find(n=>n.id==='mud-f50-pair-apply').onclick();await tick();
            assert.deepEqual(requests,['f50pro-pair-'+first+'-'+second]);
            assert.equal(common.selectedSlot(),target===0||target===3?'0':'1','source combinations do not change the viewed/data slot');
        }
        physical.ready=false;await view.refresh();assert(button.disabled);
        view.unload();
    }
    console.log('SIM UI: scoped RPC, shared controls, V50/U30 Pro and all six F50 Pro hardware variants pass; reversed external labels retain native card IDs');
})().catch(e=>{console.error(e);process.exitCode=1;});
