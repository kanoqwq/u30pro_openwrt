import { feedback } from 'mu300.f50pro-feedback';
import { plan } from 'mu300.button-cycle';
import { output } from 'mu300.f50pro-led';
let checks=0;
function check(ok,text){if(!ok)die(text+'\n');checks++;}
let clock=null,allocations=0,writes=[],normal='blue',restores=0;
const owner=feedback((ms,callback)=>{
    check(!clock?.active,'at most one active burst timer');
    allocations++;clock={active:true,callback,set:()=>{clock.active=true;},cancel:()=>{clock.active=false;}};
    return clock;
},colour=>push(writes,colour),()=>{restores++;push(writes,normal);});
function drain(){let ticks=0;while(clock?.active){clock.active=false;clock.callback();check(++ticks<=11,'bounded burst');}}
check(clock==null,'idle creates no timer');
const state={ok:1,supported:true,ready:true,model:'f50pro',cards:[0,1,3,4],logical_cards:[0,4],active_card:1};
let choice=plan(state,'list');
check(choice.target=='f50pro-card-4' && choice.ordinal==3 && choice.colour=='white','native card 4 is external1, third in list');
state.active_card=4;choice=plan(state,'pair');
check(choice.target=='f50pro-card-0' && choice.ordinal==1 && choice.colour=='green','pair uses current IMEI1 source');
state.logical_cards=[3,1];state.active_card=3;choice=plan(state,'pair');
check(choice.target=='f50pro-card-1' && choice.ordinal==2 && choice.colour=='green','mixed current pair uses logical order');
for(let colour in ['green','white'])for(let n=1;n<=5;n++) {
    writes=[];owner.event({id:colour+n,stage:'start',ordinal:n,colour});
    check(owner.active() && writes[0]=='off','dark lead-in');
    owner.event({id:colour+n,stage:'done'});drain();
    check(length(filter(writes,v=>v==colour))==n,'exact requested pulse count');
    check(!owner.active() && writes[-1]=='blue','restore current signal state');
}
writes=[];owner.event({id:'refused',stage:'start',ordinal:4,colour:'white'});
owner.event({id:'refused',stage:'failed'});drain();
check(length(filter(writes,v=>v=='red'))==4,'refused external card: four red pulses');
check(length(filter(writes,v=>v=='white'))==0,'immediate refusal replaces pending white');
writes=[];owner.event({id:'old',stage:'start',ordinal:4,colour:'white'});
owner.event({id:'new',stage:'start',ordinal:2,colour:'green'});
owner.event({id:'old',stage:'failed'});normal='white';drain();
check(length(filter(writes,v=>v=='green'))==2,'newest request retains its count');
check(length(filter(writes,v=>v=='red'))==0 && writes[-1]=='white','late result ignored, restore latest registration');
let before=restores;
for(let message in [null,{},[],{id:'bad',stage:'start',ordinal:0,colour:'white'},
    {id:'bad',stage:'start',ordinal:6,colour:'green'},
    {id:'bad',stage:'start',ordinal:1,colour:'red'}])owner.event(message);
check(!owner.active() && restores==before,'invalid events cannot animate');
for(let colour in ['green','white','red'])for(let setting in ['0','1']) {
    let values=output('net',colour,'0',setting);
    check(!length(filter(values,v=>v.brightness>0)),'zero brightness remains off');
    values=output('net',colour,'150','0');
    check(!length(filter(values,v=>v.brightness>0)),'disabled signal lamp remains off');
}
for(let i=0;i<10000;i++) {
    owner.event({id:'stress'+i,stage:'start',ordinal:i%5+1,colour:i%2?'green':'white'});
    owner.event({id:'stress'+i,stage:i%3?'done':'failed'});drain();
}
check(!clock.active && !owner.active(),'sustained traffic leaves no active timer');
owner.event({id:'stop',stage:'start',ordinal:5,colour:'white'});owner.stop();
check(!clock.active && !owner.active(),'shutdown cancels animation and restores');
print('PASS '+checks+' selector/feedback/fault/stress checks; no hardware access\n');
