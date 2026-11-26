#!/usr/bin/ucode
import * as fs from 'fs';
import { target, current_state } from 'mu300.button-cycle';
let reply;
try {
    let state=current_state(json(fs.stdin.read('all')),ARGV[1]);
    reply=state.ok?target(state,ARGV[0]):state;
}
catch(e) { reply={ok:0,error:'sim_read_failed'}; }
printf('%J\n',reply);
