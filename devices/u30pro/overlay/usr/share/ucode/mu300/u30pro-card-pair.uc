// U30 Pro source selection only; the existing RF owner performs each route.
import * as fs from 'fs';
import * as uloop from 'uloop';

const BIN=getenv('MU300_BIN') || '/opt/mu300/bin';
const RUN=getenv('MU300_U30PRO_RUN') || '/run';
const CONTROL=BIN+'/mu300-u30pro-sim';
const MARKER=RUN+'/mu300/u30pro-switch-incomplete';
function text(path) { return trim(fs.readfile(path) || ''); }
function quote(s) { return "'"+replace(''+s,/'/g,"'\\''")+"'"; }
function read(argv,optional) {
    let pipe=fs.popen(join(' ',map(argv,quote))+' 2>/dev/null','r');
    if(!pipe)die('sim_read_failed');
    let result=trim(pipe.read('all') || ''),code=pipe.close();
    if(code && !optional)die('sim_read_failed');
    return code?null:result;
}
function cfg(key) { let value=read(['uci','-q','get','unisoc_modem.main.'+key],true); return value===''?null:value; }
function status() { return json(read([CONTROL,'status'])); }
function valid(state,first,second) {
    if(!state?.ok || !state.supported || state.model!='u30pro' || type(state.cards)!='array')
        die('physical_card_unsupported');
    if(!(first in state.cards) || !(second in state.cards) ||
       !(first in [0,3]) || !(second in [1,2]))die('physical_card_unavailable');
}

let child=null,cancelled=false,restoring=false;
uloop.init();
function cancel() {
    if(restoring)return;
    cancelled=true;
    if(child)system(['/bin/kill','-TERM',''+child.pid()]);
}
const term=uloop.signal(15,cancel),intr=uloop.signal(2,cancel);
function run(argv) {
    if(cancelled && !restoring)return false;
    // Resolve PATH before exec so BusyBox's standalone applets cannot bypass it.
    argv=slice(argv,0);
    if(index(argv[0],'/')<0) {
        for(let dir in split(getenv('PATH') || '/usr/sbin:/usr/bin:/sbin:/bin',':')) {
            let path=(dir || '.')+'/'+argv[0];
            if(fs.stat(path)?.mode & 73){argv[0]=path;break;}
        }
    }
    let code=1;
    child=uloop.process('/bin/sh',['-c','exec '+join(' ',map(argv,quote))],null,result=>{
        code=result;child=null;uloop.end();
    });
    if(!child)return false;
    uloop.run();
    return code==0 && (!cancelled || restoring);
}
function checked(argv,error) { if(!run(argv))die(error); }
function route(card) { return run([BIN+'/mobile-data','radio-locked',CONTROL,'--pair-route',''+card]); }
function set(key,value) {
    let full='unisoc_modem.main.'+key;
    return value==null?cfg(key)==null || run(['uci','-q','delete',full]):
        run(['uci','-q','set',full+'='+value]);
}

let result=0,disrupted=false,marked=false,autostart=false,wan=null,previous=null,old=null;
try {
    if(text((getenv('MU300_SYSROOT') || '')+'/etc/mu300/model')!='u30pro')die('physical_card_unsupported');
    if(!(ARGV[0] in ['validate','apply']) || length(ARGV)!=3 ||
       !match(ARGV[1],/^[0-3]$/) || !match(ARGV[2],/^[0-3]$/))die('physical_card_unavailable');
    let first=int(ARGV[1]),second=int(ARGV[2]),state=status();
    valid(state,first,second);
    checked([CONTROL,'validate',''+first],'physical_mux_unavailable');
    checked([CONTROL,'validate',''+second],'physical_mux_unavailable');
    if(ARGV[0]=='apply') {
        if(!state.ready || fs.stat(RUN+'/unisoc-modem-lock-apply'))die('modem_busy');
        previous=state.logical_cards;
        if(type(previous)!='array' || length(previous)!=2)die('sim_read_failed');
        valid(state,previous[0],previous[1]);
        let saved=cfg('data_sim'),actual=read([BIN+'/mu300-data-sim','current']);
        if(!(saved in ['0','1']) || !(actual in ['0','1']))die('sim_read_failed');
        wan=cfg('data_interface') || 'wan';
        if(!match(wan,/^[A-Za-z0-9_]+$/))die('sim_read_failed');
        old={u30pro_route0:cfg('u30pro_route0'),u30pro_route1:cfg('u30pro_route1'),u30pro_card:cfg('u30pro_card')};
        let requested=[first,second];
        if(previous[int(actual)]!=requested[int(actual)]) {
            let network=json(read(['ubus','-t','3','call','network.interface.'+wan,'status']));
            if(type(network?.autostart)!='bool')die('sim_read_failed');
            autostart=network.autostart;disrupted=true;
            checked(['ifdown',wan],'data_disconnect_failed');
            // ifdown is asynchronous; use the same bounded completion wait as the existing owner.
            let done=false;
            for(let n=0;n<=10;n++) {
                network=json(read(['ubus','-t','3','call','network.interface.'+wan,'status']));
                if(type(network?.up)!='bool' || type(network?.pending)!='bool')die('sim_read_failed');
                if(!network.up && !network.pending){done=true;break;}
                if(n<10)checked(['sleep','1'],'data_disconnect_failed');
            }
            if(!done)die('data_disconnect_failed');
        }
        if(fs.writefile(MARKER,'')===null)die('storage_failed');
        marked=true;
        if(!route(first) || !route(second))die('physical_card_power_failed');
        for(let key,value in {u30pro_route0:first,u30pro_route1:second,u30pro_card:requested[int(saved)]})
            if(!set(key,value))die('storage_failed');
        checked(['uci','-q','commit','unisoc_modem'],'storage_failed');
        fs.unlink(MARKER);marked=false;
        restoring=true; // Finish restoring WAN intent even if the caller closes now.
        if(disrupted && autostart && !run(['ifup',wan]))warn('Sources saved; netifd start failed\n');
    }
} catch(error) {
    warn(''+error+'\n');result=1;restoring=true;
    let restored=true;
    if(marked) {
        restored=route(previous[1]) && route(previous[0]);
        if(restored) {
            for(let key,value in old)if(!set(key,value))restored=false;
            if(!run(['uci','-q','commit','unisoc_modem']))restored=false;
        }
        if(restored)fs.unlink(MARKER);
    }
    if(restored && disrupted && autostart)restored=run(['ifup',wan]);
    if(marked)warn(restored?'sim_switch_failed_restored\n':'sim_rollback_failed\n');
}
exit(result);
