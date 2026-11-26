// Choose a target only. The existing data-SIM owner retains the transaction.
export function current_state(state,slot) {
    if(!(slot in ['0','1']) || type(state?.logical_cards)!='array' || length(state.logical_cards)!=2)
        return {ok:0,error:'sim_read_failed'};
    let copy={};for(let key,value in state)copy[key]=value;
    copy.active_card=state.logical_cards[int(slot)];
    return copy;
};
export function plan(state,mode) {
    if(mode!='pair' && mode!='list')return {ok:0,error:'invalid_button_cycle'};
    let cards=state?.cards, current=state?.active_card;
    if(!state?.ok || !state.supported || !state.ready ||
       (state.model!='f50pro' && state.model!='u30pro') ||
       type(cards)!='array' || !length(cards))return {ok:0,error:'sim_unavailable'};
    let seen={};
    for(let card in cards) {
        if(type(card)!='int' || card<0 || card>(state.model=='f50pro'?4:3) || seen[''+card])return {ok:0,error:'sim_unavailable'};
        seen[''+card]=true;
    }
    if(type(current)!='int' || !seen[''+current])return {ok:0,error:'sim_read_failed'};
    let order;
    if(mode=='pair') {
        // These are the owner's live IMEI1/IMEI2 routes, including mixed sources.
        order=state.logical_cards;
        // U30 Pro's single-source form has one unrouted IMEI, not a second card.
        if(state.model=='u30pro' && length(cards)==1 && type(order)=='array' && length(order)==2 &&
           ((order[0]===current && order[1]===null) || (order[1]===current && order[0]===null)))
            return {ok:1,target:null};
        if(type(order)!='array' || length(order)!=2 || order[0]===order[1])
            return {ok:0,error:'sim_unavailable'};
        for(let card in order)if(type(card)!='int' || !seen[''+card])return {ok:0,error:'sim_unavailable'};
    } else {
        // Preserve SIM management's order: external 1 is native card 4.
        order=state.model=='f50pro'?
            sort(slice(cards,0), (a,b)=>(a==4?3:a==3?4:a)-(b==4?3:b==3?4:b)):
            sort(slice(cards,0), (a,b)=>a-b);
    }
    let position=index(order,current);
    if(position<0)return {ok:0,error:'sim_read_failed'};
    let next=(position+1)%length(order),card=order[next];
    return {ok:1,target:length(order)==1?null:state.model+'-card-'+card,
            ordinal:next+1,colour:card<3?'green':'white'};
};
export function target(state,mode) {
    let choice=plan(state,mode);
    return choice.ok?{ok:1,target:choice.target}:choice;
};
