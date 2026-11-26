// The existing LED owner alone writes emitters. Timers run only for a burst.
export function feedback(timer,paint,restore) {
    let job=null,burst=null,clock=null;
    function tick() {
        if(!burst)return;
        if(!burst.remaining) {
            burst=null;clock=null;restore();return;
        }
        burst.on=!burst.on;
        paint(burst.on?burst.colour:'off');
        burst.remaining--;
        clock.set(180);
    }
    function flash(colour,count) {
        if(clock)clock.cancel();
        burst={colour,remaining:count*2,on:false};
        // A dark lead-in makes the first pulse visible even on a lit lamp.
        paint('off');
        clock=timer(180,tick);
    }
    return {
        active:()=>burst!=null,
        event:(message)=>{
            if(type(message)!='object' || type(message.id)!='string' ||
               !match(message.id,/^[a-zA-Z0-9:-]{1,80}$/))return;
            if(message.stage=='start') {
                if(job?.id==message.id || type(message.ordinal)!='int' ||
                   message.ordinal<1 || message.ordinal>5 ||
                   !(message.colour in ['green','white']))return;
                job={id:message.id,ordinal:message.ordinal,colour:message.colour,done:false};
                flash(job.colour,job.ordinal);
            } else if(job?.id==message.id && !job.done && message.stage in ['done','failed']) {
                job.done=true;
                if(message.stage=='failed')flash('red',job.ordinal);
            }
        },
        stop:()=>{
            if(clock)clock.cancel();
            clock=null;
            let active=burst!=null;
            burst=null;job=null;
            if(active)restore();
        }
    };
};
