// MU3356 physical outputs. White is a separate PMIC emitter, never GPIO green.
const palette=['red','green','blue','white','off'];
function colour(value,fallback) {return value in palette?value:fallback;}
export function colours(registered,nr,band,settings) {
    settings??={};
    return {
        net:registered?colour(settings[nr?'signal_5g':'signal_4g'],nr?'white':'blue'):
                       colour(settings.signal_offline,'red'),
        wifi:band=='5g'?colour(settings.wifi_5g,'white'):
             band=='2g'?colour(settings.wifi_2g,'green'):'off'
    };
};
export function channels(bank) {
    return [bank+'_red',bank+'_green',bank+'_blue',bank=='wifi'?'sc27xx:red':'sc27xx:green'];
};
export function output(bank,value,brightness,enabled) {
    let number=match(''+brightness,/^\d+$/)?int(brightness):null;
    let level=number!=null && number>=0 && number<=255?number:(bank=='wifi'?127:255);
    let selected=enabled=='0' || level==0?-1:index(palette,colour(value,'off'));
    let values=[];
    for(let n,node in channels(bank))
        push(values,{node,brightness:selected==n?(n==3?level:1):0});
    return values;
};
export function boot_colours(step) {
    let sequence=['red','green','blue','white'];
    return {net:sequence[step%4],wifi:sequence[(step+2)%4]};
};
