// Whole-device, live NR0 indication. Never persist or infer a SIM from ingress.
export function tracker(supported, notify) {
    let known=false, active=false;
    function snapshot() { return {supported:!!supported,known,active}; }
    function set(next_known,next_active) {
        if(known==next_known && active==next_active)return;
        known=next_known;active=next_active;
        notify(snapshot());
    }
    return {
        snapshot,
        reset:()=>set(false,false),
        ingest:(channel,line)=>{
            if(!supported || channel!='stty_nr0')return;
            let m=match(line,/^\+SPHIGHRAILINFO:\s*([01])\s*$/);
            if(m)set(true,m[1]=='1');
        }
    };
};
