"""Run the production ucode selector; no modem access or hardware writes."""
import copy
import json
import subprocess
import unittest
from helpers import TOP, ucode, ucode_paths

CLI=TOP/'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/button-cycle.uc'

@unittest.skipUnless(ucode(),'requires target ucode')
class Cycle(unittest.TestCase):
    def select(self,state,mode='pair',actual=None):
        if actual is None:actual='0' if state.get('active_card') in (0,3) else '1'
        p=subprocess.run(ucode()+ucode_paths()+[str(CLI),mode,actual],input=json.dumps(state),capture_output=True,text=True,timeout=5)
        self.assertEqual(p.returncode,0,p.stderr)
        return json.loads(p.stdout)

    def state(self,cards,pair,active):
        return dict(ok=1,supported=True,ready=True,model='f50pro',cards=cards,
            logical_cards=pair,active_card=active,saved_card=0)

    def test_current_pair_including_mixed_sources_and_changed_routes(self):
        # All seven board IDs. Live owner routes, not group-by-internal/external.
        for cards,lefts,rights in [([0,1,2],[0],[1,2]),([0,1],[0],[1]),([0,2],[0],[2]),
                ([0,2,3,4],[0,3],[2,4]),([0,1,3,4],[0,3],[1,4]),
                ([3,4],[3],[4]),([0,2,3,4],[0,3],[2,4])]:
            for left in lefts:
                for right in rights:
                    for active,wanted in [(left,right),(right,left)]:
                        state=self.state(cards,[left,right],active);saved=copy.deepcopy(state)
                        self.assertEqual(self.select(state),{'ok':1,'target':'f50pro-card-'+str(wanted)})
                        self.assertEqual(state,saved)

    def test_list_order_preserved_and_single_source_noop(self):
        order=[0,1,4,3]
        for i,card in enumerate(order):
            routes=[card if card in (0,3) else 0,card if card not in (0,3) else 4]
            self.assertEqual(self.select(self.state([3,0,4,1],routes,card),'list'),
                {'ok':1,'target':'f50pro-card-'+str(order[(i+1)%4])})
        self.assertEqual(self.select(self.state([0],[0,None],0),'list'),{'ok':1,'target':None})

    def test_unknown_current_route_or_invalid_mode_never_falls_back_to_list(self):
        state=self.state([0,1,3,4],[0,4],0)
        for change in [dict(logical_cards=None),dict(logical_cards=[0]),dict(logical_cards=[0,0]),
            dict(logical_cards=[False,4]),dict(logical_cards=[0,2]),
            dict(ready=False),dict(model='u30air'),
            dict(cards=[0,False,4]),dict(cards=[0,0,4]),dict(cards=[]),dict(logical_cards=[None,4])]:
            with self.subTest(change=change):self.assertEqual(self.select(dict(state,**change))['ok'],0)
        self.assertEqual(self.select(state,'unknown')['ok'],0)

    def test_live_stack_overrides_stale_active_and_saved_cards(self):
        for model,cards,pair in [('f50pro',[0,1,3,4],[0,4]),('u30pro',[0,1,2,3],[0,2])]:
            state=dict(self.state(cards,pair,0),model=model,saved_card=0)
            self.assertEqual(self.select(state,'pair','1'),{'ok':1,'target':model+'-card-0'})
            self.assertNotEqual(self.select(state,'list','1')['target'],model+'-card-'+str(pair[1]))
            for invalid in ('','2','unknown'):
                self.assertEqual(self.select(state,'list',invalid)['ok'],0)

    def test_u30pro_current_imei_routes_and_all_forms(self):
        for cards,pairs in [([0,1,2,3],[[0,1],[0,2],[3,1],[3,2]]),
                ([0,1,2],[[0,1],[0,2]]),([0,1],[[0,1]]),
                ([0,1,3],[[0,1],[3,1]]),([0,2],[[0,2]])]:
            for pair in pairs:
                for active in pair:
                    state=dict(self.state(cards,pair,active),model='u30pro')
                    wanted=pair[1] if active==pair[0] else pair[0]
                    self.assertEqual(self.select(state),{'ok':1,'target':'u30pro-card-'+str(wanted)})
                    self.assertEqual(self.select(state,'list'),{'ok':1,'target':'u30pro-card-'+str(cards[(cards.index(active)+1)%len(cards)])})
        single=dict(self.state([3],[3,None],3),model='u30pro')
        self.assertEqual(self.select(single),{'ok':1,'target':None})
        self.assertEqual(self.select(single,'list'),{'ok':1,'target':None})
        for pair in ([None,None],[3,3],[3,0]):
            self.assertEqual(self.select(dict(single,logical_cards=pair))['ok'],0)
        multi=dict(single,cards=[0,1,3])
        self.assertEqual(self.select(multi)['ok'],0)

    def test_repeated_events_use_current_pair_without_retained_state(self):
        program="""import {target} from 'mu300.button-cycle';
let s={ok:1,supported:true,ready:true,model:'f50pro',cards:[0,1,3,4],logical_cards:[0,4],active_card:0};
for(let i=0;i<20000;i++) {
 let wanted=s.active_card==s.logical_cards[0]?s.logical_cards[1]:s.logical_cards[0];
 let r=target(s,'pair');if(!r.ok || r.target!='f50pro-card-'+wanted)die(sprintf('%J',r));
 s.active_card=wanted;
 if(i==9999){s.logical_cards=[3,1];s.active_card=3;}
}
print('ok');"""
        program=program.replace("print('ok');", """s={ok:1,supported:true,ready:true,model:'u30pro',cards:[0,1,2,3],logical_cards:[0,2],active_card:0};
for(let i=0;i<20000;i++) {
 let wanted=s.active_card==s.logical_cards[0]?s.logical_cards[1]:s.logical_cards[0];
 let r=target(s,'pair');if(!r.ok || r.target!='u30pro-card-'+wanted)die(sprintf('%J',r));
 s.active_card=wanted;
 if(i==9999){s.logical_cards=[3,1];s.active_card=3;}
}
print('ok');""")
        p=subprocess.run(ucode()+ucode_paths()+['-e',program],capture_output=True,text=True,timeout=60)
        self.assertEqual((p.returncode,p.stdout),(0,'ok'),p.stderr)

if __name__=='__main__':unittest.main(verbosity=2)
