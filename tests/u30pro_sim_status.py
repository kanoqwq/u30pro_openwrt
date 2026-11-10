"""Exercise real screen status conversion and native labels, without hardware."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from helpers import TOP, ucode

NATIVE=TOP/'devices/u30pro/native/tools'


class SimStatus(unittest.TestCase):
    def test_actual_screen_payload_uses_selected_sim_and_clears_removed_card(self):
        command=ucode()
        if not command:self.skipTest('ucode runtime required')
        source=(TOP/'devices/u30pro/overlay/usr/sbin/u30pro-ui-feed').read_text()
        helper=source[source.index('function cell_status('):source.index('function run()')]
        body=source[source.index('    let state=cell_status('):source.index('    for(let i=0;i<min(6,length(view.wifi.clients')]
        cases=[
            ('absent',0,False,True,True,'waiting-sim'),
            ('absent',1,True,True,True,'waiting-sim'),
            ('ready',0,False,True,True,'radio-off'),
            ('ready',1,False,False,True,'data-disabled'),
            ('ready',1,True,True,True,'connected'),
            ('ready',1,False,True,True,'dialing'),
            ('locked',1,False,True,True,'sim-locked'),
            ('unknown',1,False,True,True,'checking-sim'),
            ('unknown',None,False,True,False,'modem-unavailable'),
        ]
        program=helper+'''
const cases=CASES;
const fs={readfile:()=>'',writefile:()=>true,rename:()=>true};
const config={get:()=>''},carrier_name=x=>x ?? '';
for(let row in cases) for(let selected in [0,1]) {
 let slot=''+selected, wanted=row[3];
 let view={modem:{alive:row[4],sims:[{slot:0,state:'ready'},{slot:1,state:'ready'}]},
   wan:{up:row[2],ip4:'stale-ip',device:'sipa_eth0'},wifi:{},net:{},kernel:'fixture'};
 view.modem.sims[selected].state=row[0];
 let cell={cfun:row[1],lte:{band:3,rsrp:-90},nr:{band:78,rsrp:-80},operator:'stale-operator'};
 let sig={},relay={},charge={};
 BODY
 if(data.cell_state!==row[5] || data.cell_connected!==(row[5]=='connected'))
    die(sprintf('Bad selected SIM state: %J',data));
 if(row[0]=='absent' && (data.ip!='' || data.op!='' || data.have_sig!=0 || data.rat!=''))
    die(sprintf('Removed SIM leaked old link: %J',data));
}
print('PASS 18 selected-SIM screen payloads\\n');
'''.replace('CASES',json.dumps(cases)).replace('BODY',body)
        result=subprocess.run(command+['-e',program],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS 18',result.stdout)

    @unittest.skipUnless(os.name=='posix','native C simulator requires POSIX')
    def test_real_native_screen_text_does_not_call_all_disconnections_dialing(self):
        source=(NATIVE/'ui/pages.h').read_text()
        start=source.index('static const char *cell_text(')
        function=source[start:source.index('\n}\n',start)+3]
        tests=[('waiting-sim','无SIM卡'),('checking-sim','正在识别SIM卡'),('sim-locked','SIM卡已锁定'),
               ('radio-off','无线电已关'),('data-disabled','数据已关闭'),('modem-unavailable','基带无应答'),
               ('dialing','拨号中…')]
        program='#define _GNU_SOURCE\n#include <assert.h>\n#include "ui/data.h"\n'+function+'\nint main(void){char b[64];D.feed_ok=1;\n'
        for state,label in tests:
            program+=f'strcpy(D.cell_state,{json.dumps(state)});assert(!strcmp(cell_text(b,sizeof b),{json.dumps(label,ensure_ascii=False)}));\n'
        program+='D.cell_connected=1;strcpy(D.op,"carrier");assert(!strcmp(cell_text(b,sizeof b),"carrier"));return 0;}\n'
        with tempfile.TemporaryDirectory(prefix='u30pro-screen-sim-') as tmp:
            root=Path(tmp);path=root/'test.c';path.write_text(program)
            subprocess.run(['gcc','-std=gnu11','-O2','-Wno-unused-function','-I',str(NATIVE),str(path),'-lm','-o',str(root/'test')],check=True,capture_output=True)
            subprocess.run([str(root/'test')],check=True,timeout=5)


if __name__=='__main__':unittest.main(verbosity=2)
