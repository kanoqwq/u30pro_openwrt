"""Actual configurable button UI: no hardware; translated RPC and persistence."""
from pathlib import Path
from playwright.sync_api import sync_playwright

TOP=Path(__file__).resolve().parents[1]
JS=TOP/'openwrt/luci-app-mu300/htdocs/luci-static/resources'
sources={n:(JS/('mu300/'+n+'.js')).read_text(encoding='utf-8') for n in ('common','buttons')}
device=(JS/'view/mu300/device.js').read_text(encoding='utf-8')
style=device.split('<style>',1)[1].split('</style>',1)[0]
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe')
    for lang in ('zh','en','tr'):
        for width in (320,1280):
            page=browser.new_page(viewport={'width':width,'height':900});errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.set_content('<style>'+style+'</style><main class="mud"></main>')
            page.evaluate('''({sources,lang})=>{
                window.calls=[];window.fail=false;window.state={ok:1,supported:true,short:'none',long:'none'};
                window.L={env:{lang},hasViewPermission:()=>true};
                const rpc={declare:o=>(...args)=>{
                    if(o.method==='button_get')return Promise.resolve({...state});
                    if(o.method==='button_set'){calls.push(args);if(fail)return Promise.reject(Error('transport'));state={...state,short:args[0],long:args[1]};return Promise.resolve({...state});}
                    throw Error(o.method);
                }};
                window.M=new Function('rpc','baseclass','L',sources.common)(rpc,{extend:x=>x},L);M.injectCss();
                window.widget=new Function('rpc','baseclass','M','L',sources.buttons)(rpc,{extend:x=>x},M,L);
                window.instance=widget.mount(document.querySelector('main'));
            }''',dict(sources=sources,lang=lang))
            button=page.locator('.mud-buttons button')
            page.wait_for_function('!document.querySelector(".mud-buttons button").disabled')
            assert page.locator('#mud-button-0').input_value()=='none'
            assert page.locator('#mud-button-1').input_value()=='none'
            assert page.evaluate('calls.length')==0
            page.locator('#mud-button-0').select_option('data-switch')
            page.locator('#mud-button-1').select_option('wifi-band');button.click()
            page.wait_for_function('calls.length===1 && !document.querySelector(".mud-buttons button").disabled')
            assert page.evaluate('calls[0]')==['data-switch','wifi-band']
            assert page.locator('#mud-button-0').input_value()=='data-switch'
            page.evaluate('fail=true');button.click()
            page.wait_for_function('calls.length===2 && !document.querySelector(".mud-buttons button").disabled')
            assert page.locator('[role=status]').inner_text()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            if lang!='zh':assert not page.locator('main').evaluate('e=>/[\\u4e00-\\u9fff]/.test(e.textContent)')
            page.evaluate("instance.dispose();document.querySelector('main').innerHTML='';state.supported=false;widget.mount(document.querySelector('main'))")
            page.wait_for_timeout(100)
            assert page.locator('.mud-buttons').is_hidden()
            assert not errors,errors
            page.close()
    browser.close()
print('PASS configurable F50 Pro button: default none, saved short/long, error recovery, unsupported model, 3 languages and mobile/desktop')
