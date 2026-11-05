// Prepended to the actual daemon with only fs/UCI/ubus/uloop imports replaced.
// Isolated device model: no host /sys, physical bus, AT or kernel calls.
let checks=0;
function check(ok,text) {if(!ok)die(text+'\n');checks++;}
let mode=ARGV[0] || 'boot',marker_reads=0;
let levels={},handlers={},ready_marker=mode in ['ready','wireless'],nr_test=false,timer_test=null;
let settings_test=mode=='disabled'?{boot_animation:'0'}:{};
let ap_up=true,ap_freq=5180,link_callback=null,ap_reads=0;
const fs={
    stat:(path)=>{
        if(path!='/run/f50pro-led-ready')return {};
        if(mode=='race' && ++marker_reads==2)ready_marker=true;
        return ready_marker?{}:null;
    },
    readfile:(path)=>{
        if(path=='/etc/mu300/model')return 'f50pro\n';
        if(path=='/run/mu300-data-sim-actual')return '1\n';
        if(path=='/run/mu300-registration/slot1.json')return sprintf('%J',{slot:1,stat:1,rat:nr_test?13:7});
        return null;
    },
    writefile:(path,text)=>{if(match(path,/\/brightness$/))levels[path]=int(text);return length(text);}
};
const uci={cursor:()=>({unload:()=>{},get:(config,section,key)=>config=='system'?settings_test[key]:null})};
const ubus={connect:()=>({
    listener:(name,callback)=>{handlers[name]=callback;return {};},
    call:(object)=>{
        check(object=='hostapd.wlan0','Wi-Fi lamp queries the actual AP, not early netifd radio.up');ap_reads++;
        return {status:ap_up?'ENABLED':'DISABLED',freq:ap_freq};
    }
})};
const rtnl={const:{RTM_NEWLINK:16,RTM_DELLINK:17,RTNLGRP_LINK:1},
    listener:(callback,commands,groups)=>{
        check(commands[0]==16 && commands[1]==17 && groups[0]==1,'kernel link notifications selected');
        link_callback=callback;return {};
    }};
function level(name) {return levels['/sys/class/leds/'+name+'/brightness']??0;}
const uloop={
    init:()=>{},end:()=>{},signal:()=>({}),
    timer:(ms,callback)=>{
        timer_test={active:true,callback,set:()=>{timer_test.active=true;},cancel:()=>{timer_test.active=false;}};
        return timer_test;
    },
    run:()=>{
        if(mode=='wireless') {
            check(!timer_test,'normal Wi-Fi state has no polling timer');
            let before=ap_reads;link_callback({msg:{dev:'usb0'}});
            check(ap_reads==before,'unrelated links do not query Wi-Fi');
            ap_up=false;link_callback({msg:{dev:'wlan0'}});
            check(level('sc27xx:red')==0 && level('wifi_green')==0,'AP down turns the Wi-Fi bank off');
            ap_up=true;ap_freq=2437;link_callback({msg:{dev:'wlan0'}});
            check(level('wifi_green')==1 && level('sc27xx:red')==0,'AP ready at 2.4 GHz lights green');
            ap_up=false;link_callback({msg:{dev:'wlan0'}});
            ap_up=true;ap_freq=5180;link_callback({msg:{dev:'wlan0'}});
            check(level('sc27xx:red')==127 && level('wifi_green')==0,'AP ready at 5 GHz restores white without a later registration event');
            check(!timer_test,'band switches do not start a polling timer');
            print('PASS '+checks+' Wi-Fi link-event lifecycle checks; no hardware access\n');return;
        }
        if(mode!='boot') {
            check(!timer_test || !timer_test.active,'late start/disabled/race does not animate');
            check(level('net_blue')==1 && level('sc27xx:red')==127,'normal state shown immediately');
            handlers['f50pro.config']();
            check(!timer_test || !timer_test.active,'configuration reload does not restart animation');
            print('PASS '+checks+' LED lifecycle '+mode+' checks; no hardware access\n');
            return;
        }
        check(timer_test.active && level('net_red')==1,'early boot starts animation');
        for(let i=0;i<3;i++)timer_test.callback();
        check(level('sc27xx:green')==255 && level('net_green')==0,'boot white uses PMIC, not GPIO green');
        ready_marker=true;handlers['f50pro.boot']();
        check(!timer_test.active,'boot complete cancels the timer');
        check(level('net_blue')==1 && level('sc27xx:red')==127 && level('wifi_green')==0,'normal LTE and 5GHz takeover');
        nr_test=true;handlers['mu300.registration']();
        check(level('net_blue')==0 && level('sc27xx:green')==255,'NR registration event updates signal lamp');
        settings_test.wifi_5g='blue';settings_test.wifi_brightness='42';handlers['f50pro.config']();
        check(level('wifi_blue')==1 && level('sc27xx:red')==0,'saved mapping applies without polling');
        settings_test.signal_brightness='61';handlers['f50pro.config']();
        check(level('sc27xx:green')==61,'white brightness applies on reload');
        settings_test.wifi='0';handlers['f50pro.config']();
        check(level('wifi_blue')==0 && level('sc27xx:red')==0,'disabled Wi-Fi lamp stays dark');
        check(!timer_test.active,'normal events do not restart the boot timer');
        print('PASS '+checks+' production LED lifecycle checks: boot, ready, NR, reload, disable; no hardware access\n');
    }
};
