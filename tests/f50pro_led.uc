import { colours,output,boot_colours } from 'mu300.f50pro-led';
let count=0;
function check(value,message) { if(!value)die(message+'\n');count++; }
check(colours(true,false,'5g').net=='blue','LTE blue');
check(colours(true,true,'5g').net=='white','NR white');
check(colours(false,true,'2g').net=='red','no service red');
check(colours(true,false,'5g').wifi=='white','5GHz white');
check(colours(true,false,'2g').wifi=='green','2.4GHz green');
check(colours(true,false,null).wifi=='off','disabled AP indicator');
check(colours(true,true,'5g',{signal_5g:'green',wifi_5g:'red'}).net=='green','saved colour map');
check(colours(true,false,'2g',{signal_4g:'invalid',wifi_2g:'invalid'}).wifi=='green','invalid map defaults');
for(let bank in ['net','wifi'])for(let colour in ['white','blue','green','red','off']) {
    let values=output(bank,colour,'83','1'),active=0;
    for(let value in values)if(value.brightness>0)active++;
    check(active==(colour=='off'?0:1),'one physical emitter, no mixed colours');
    if(colour=='white')check(values[3].brightness==83 && values[3].node==(bank=='wifi'?'sc27xx:red':'sc27xx:green'),'white PMIC channel/brightness');
    check(output(bank,colour,'0','1')[3].brightness==0,'zero brightness');
    for(let value in output(bank,colour,'83','0'))check(value.brightness==0,'disabled lamp');
}
check(output('wifi','white','999','1')[3].brightness==127,'invalid brightness defaults');
for(let i=0;i<8;i++)check(boot_colours(i).net==['red','green','blue','white'][i%4],'boot sequence');
print('PASS '+count+' F50 Pro LED mapping/brightness/boot cases; no GPIO or AT access\n');
