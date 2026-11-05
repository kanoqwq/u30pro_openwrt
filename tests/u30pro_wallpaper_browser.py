"""Actual browser controls and theme tokens; RPC/upload are isolated mocks."""
from pathlib import Path
from playwright.sync_api import sync_playwright
import base64
import re

TOP=Path(__file__).resolve().parents[1]
common=(TOP/'openwrt/luci-app-mu300/htdocs/luci-static/resources/mu300/common.js').read_text(encoding='utf8')
source=(TOP/'devices/u30pro/native/ui/native-control/overlay/www/luci-static/resources/view/system/u30pro-wallpaper.js').read_text(encoding='utf8')
with sync_playwright() as p:
    chrome=Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
    browser=p.chromium.launch(headless=True,**({'executable_path':str(chrome)} if chrome.exists() else {}))
    for theme in ('aurora','bootstrap'):
        for dark in (False,True):
            for lang in ('zh-cn','en','tr'):
                for width in (360,1280):
                    page=browser.new_page(viewport={'width':width,'height':1000})
                    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    page.route('http://u30pro.test/**',lambda route:route.fulfill(body='<html><body><nav><a href="/cgi-bin/luci/admin/system/u30pro-wallpaper">Screen wallpaper</a></nav></body></html>',content_type='text/html'))
                    page.goto('http://u30pro.test/')
                    bg,surface,text,muted,border=('#15171b','#202329','#eee','#a5a9b0','#383c44') if dark else ('#f4f5f7','#fff','#202329','#626874','#dce0e6')
                    tokens={'surface':surface,'surface-sunken':bg,'text':text,'text-muted':muted,'hairline':border,'brand':'#447bee','on-brand':'#fff'} if theme=='aurora' else {'background-color-high':surface,'background-color-low':bg,'text-color-high':text,'text-color-medium':muted,'text-color-low':muted,'border-color-low':border,'primary-color-high':'#447bee','on-primary-color':'#fff'}
                    page.add_style_tag(content='html{'+''.join(f'--{k}:{v};' for k,v in tokens.items())+'}body{margin:16px;background:'+bg+';color:'+text+';font-family:Arial,sans-serif}*{box-sizing:border-box}')
                    page.evaluate(r"""([common,source,lang])=>{
                        window._=x=>x;window.L={env:{lang,cgi_base:'/cgi-bin'},resolveDefault:(p,d)=>p.catch(()=>d)};
                        String.prototype.format=function(...args){let i=0;return this.replace(/%1024mB|%[ds]/g,m=>m==='%1024mB'?String(args[i++]||0)+' B':String(args[i++]));};
                        window.E=function(tag,attrs,children){
                            if(attrs==null||typeof attrs!=='object'||attrs instanceof Node||Array.isArray(attrs)){children=attrs;attrs={};}
                            const el=document.createElement(tag);
                            if(tag==='video')el.addEventListener('error',()=>{window.mediaError=el.error&&{code:el.error.code,message:el.error.message};});
                            Object.entries(attrs).forEach(([name,value])=>{if(value==null)return;if(typeof value==='function')el.addEventListener(name,value);else el.setAttribute(name,String(value));});
                            function append(c){if(c==null)return;if(Array.isArray(c))c.forEach(append);else el.append(c instanceof Node?c:document.createTextNode(String(c)));}
                            append(children);return el;
                        };
                        window.calls=[];window.uploads=[];window.failUpload=false;
                        window.state={picture:true,settings:{dim:30,glass:50,blur:50,tint:0,live:2}};
                        const rpc={getSessionID:()=>'',declare:o=>(...args)=>{
                            calls.push([o.method,args]);
                            if(o.method==='get')return Promise.resolve(state);
                            if(o.method==='image')return Promise.resolve({});
                            return new Promise(resolve=>setTimeout(()=>{
                                if(o.method==='remove')state={...state,picture:false};
                                if(o.method==='install')state={...state,picture:true};
                                resolve({accepted:true,wallpaper:state});
                            },100));
                        }};
                        const request={post:(url,data)=>{uploads.push(data.get('filename'));return new Promise(resolve=>setTimeout(()=>resolve({ok:!failUpload,json:()=>failUpload?{failure:true,message:'test failure'}:{},statusText:'test'}),50));}};
                        const ui={addNotification:()=>{throw new Error('Persistent notifications must not be used for wallpaper actions');}};
                        const M=new Function('rpc','baseclass','L',common)(rpc,{extend:o=>o},L);
                        class LuCIResponse { constructor(xhr) { xhr.getAllResponseHeaders(); } }
                        window.view=new Function('Response','view','rpc','request','ui','M',source)(LuCIResponse,{extend:o=>o},rpc,request,ui,M);
                        document.body.append(view.render([state,{}]));
                    }""",[common,source,lang])
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(theme,dark,lang,width,'overflow')
                    assert page.locator('.mud-card').count()==2
                    assert page.locator('.mud-card').first.evaluate('(e)=>getComputedStyle(e).backgroundColor')==('rgb(32, 35, 41)' if dark else 'rgb(255, 255, 255)'),(theme,dark)
                    heading={'zh-cn':'屏幕壁纸','en':'Wallpaper','tr':'Duvar kâğıdı'}[lang]
                    assert page.locator('h2').inner_text()==heading
                    boxes=page.locator('.u30-wp-scenes input[type=checkbox]')
                    assert boxes.count()==10
                    assert boxes.evaluate_all('(nodes)=>nodes.filter(n=>n.checked).map(n=>+n.value)')==[1,2]
                    if theme=='aurora' and not dark and lang=='zh-cn' and width==360:
                        allbox=page.locator('.u30-wp-scenes input[value="511"]')
                        signal=page.locator('.u30-wp-scenes input[value="4"]')
                        savebutton=page.locator('.mud-wallpaper button').nth(3)
                        signal.check();savebutton.click()
                        assert boxes.first.is_disabled()
                        page.wait_for_function("document.querySelector('[role=status]').getAttribute('aria-busy')==='false'")
                        assert page.evaluate("calls.filter(x=>x[0]==='set').at(-1)[1][4]")==7
                        allbox.check();assert boxes.evaluate_all('(nodes)=>nodes.every(n=>n.checked)')
                        savebutton.click();page.wait_for_function("document.querySelector('[role=status]').getAttribute('aria-busy')==='false'")
                        assert page.evaluate("calls.filter(x=>x[0]==='set').at(-1)[1][4]")==511
                        page.locator('.u30-wp-scenes input[value="128"]').uncheck();assert not allbox.is_checked()
                        savebutton.click();page.wait_for_function("document.querySelector('[role=status]').getAttribute('aria-busy')==='false'")
                        assert page.evaluate("calls.filter(x=>x[0]==='set').at(-1)[1][4]")==383
                        allbox.check();allbox.uncheck();assert boxes.evaluate_all('(nodes)=>nodes.every(n=>!n.checked)')
                        savebutton.click();page.wait_for_function("document.querySelector('[role=status]').getAttribute('aria-busy')==='false'")
                        assert page.evaluate("calls.filter(x=>x[0]==='set').at(-1)[1][4]")==0
                        page.locator('.u30-wp-scenes input[value="1"]').check()
                        page.locator('.u30-wp-scenes input[value="2"]').check()
                    if lang!='zh-cn':assert not re.search(r'[\u4e00-\u9fff]',page.locator('.mud-wallpaper').inner_text())
                    if lang=='zh-cn':assert page.locator('nav a').inner_text()=='屏幕壁纸'
                    buttons=page.locator('.mud-wallpaper button')
                    # Save sends all five settings and disables concurrent file/remove actions.
                    buttons.nth(3).click()
                    assert page.locator('[role=status]').get_attribute('aria-busy')=='true'
                    assert buttons.nth(0).is_disabled() and buttons.nth(2).is_disabled()
                    page.wait_for_function("document.querySelector('[role=status]').getAttribute('aria-busy')==='false'")
                    assert page.evaluate("calls.filter(x=>x[0]==='set').at(-1)[1]")==[30,50,50,0,3,0]
                    assert page.locator('.mud-toast.success').count()==1
                    if theme=='aurora' and not dark and lang=='en' and width==1280:
                        # Repeated saves reuse one notice and restart its expiry.
                        for _ in range(10):
                            buttons.nth(3).click()
                            page.wait_for_function("document.querySelector('[role=status]').getAttribute('aria-busy')==='false'")
                            assert page.locator('.mud-toast').count()==1
                        page.wait_for_timeout(2000)
                        buttons.nth(3).click()
                        page.wait_for_function("document.querySelector('[role=status]').getAttribute('aria-busy')==='false'")
                        page.wait_for_timeout(1900)
                        assert page.locator('.mud-toast').count()==1
                        page.locator('.mud-toast').wait_for(state='detached',timeout=2500)
                        # A later save creates a live notice after expiry.
                        buttons.nth(3).click()
                        page.wait_for_function("document.querySelector('[role=status]').getAttribute('aria-busy')==='false'")
                        assert page.locator('.mud-toast.success').count()==1
                    # Themed confirmation: Escape cancels; explicit approval removes.
                    buttons.nth(2).click();page.locator('.mud-dlg').wait_for()
                    page.keyboard.press('Escape');assert not page.evaluate("calls.some(x=>x[0]==='remove')")
                    buttons.nth(2).click();page.locator('.mud-dlg [data-r="1"]').click()
                    page.wait_for_function("calls.some(x=>x[0]==='remove') && document.querySelector('[role=status]').getAttribute('aria-busy')==='false'")
                    assert buttons.nth(2).is_disabled()
                    # Real canvas/JPEG conversion + mocked upload failure and retry.
                    payload=page.evaluate("()=>{const c=document.createElement('canvas');c.width=80;c.height=40;return c.toDataURL('image/png').split(',')[1];}")
                    page.locator('input[type=file]').set_input_files({'name':'test.png','mimeType':'image/png','buffer':base64.b64decode(payload)})
                    page.wait_for_function("!document.querySelectorAll('.mud-wallpaper button')[1].disabled")
                    page.evaluate('failUpload=true');buttons.nth(1).click()
                    page.wait_for_function("document.querySelector('.mud-toast.error') && document.querySelector('[role=status]').getAttribute('aria-busy')==='false'")
                    assert page.locator('.mud-toast').count()==1
                    assert buttons.nth(1).is_enabled()
                    page.evaluate('failUpload=false');buttons.nth(1).click()
                    page.wait_for_function("calls.some(x=>x[0]==='install') && document.querySelector('[role=status]').getAttribute('aria-busy')==='false'")
                    assert page.evaluate('uploads.slice(-2)')==['/tmp/u30pro-wallpaper.jpg','/tmp/u30pro-wallpaper.web.jpg']
                    assert buttons.nth(1).is_disabled() and buttons.nth(2).is_enabled()
                    assert page.locator('.mud-toast.success').count()==1
                    assert page.locator('.mud-toast').count()==1
                    if theme=='aurora' and not dark and lang=='en' and width==360:
                        # Real encoded video -> decode/seek -> CompressionStream -> four uploads.
                        # The module above has LuCI's lexical Response shadow, as on the device.
                        payload=page.evaluate(r'''async()=>{
                            const c=document.createElement('canvas');c.width=c.height=64;
                            const ctx=c.getContext('2d');ctx.fillStyle='blue';ctx.fillRect(0,0,64,64);
                            document.body.append(c);
                            const stream=c.captureStream(0),track=stream.getVideoTracks()[0],parts=[];
                            const recorder=new MediaRecorder(stream,{mimeType:'video/webm;codecs=vp8'});
                            const done=new Promise(resolve=>{recorder.ondataavailable=e=>parts.push(e.data);recorder.onstop=resolve;});
                            recorder.start();track.requestFrame();
                            for(let i=0;i<8;i++){c.getContext('2d').fillStyle=i%2?'red':'blue';c.getContext('2d').fillRect(0,0,64,64);track.requestFrame();await new Promise(r=>setTimeout(r,80));}
                            recorder.stop();await done;stream.getTracks().forEach(t=>t.stop());c.remove();
                            const bytes=new Uint8Array(await new Blob(parts).arrayBuffer());
                            let s='';for(const b of bytes)s+=String.fromCharCode(b);return btoa(s);
                        }''')
                        fast=page.locator('input[aria-label="High refresh"]')
                        assert not fast.is_checked()
                        fast.check();buttons.nth(3).click()
                        page.wait_for_function("document.querySelector('[role=status]').getAttribute('aria-busy')==='false'")
                        assert page.evaluate("calls.filter(x=>x[0]==='set').at(-1)[1][5]")==1
                        page.locator('select').nth(1).select_option('50')
                        page.locator('input[type=file]').set_input_files({'name':'test.webm','mimeType':'video/webm','buffer':base64.b64decode(payload)})
                        try:
                            page.wait_for_function("!document.querySelectorAll('.mud-wallpaper button')[1].disabled",timeout=20000)
                        except Exception:
                            print('VIDEO CONVERSION FAILURE:',page.locator('[role=status]').inner_text(),errors,page.evaluate('window.mediaError'),len(base64.b64decode(payload)),flush=True)
                            raise
                        assert '50 fps' in page.locator('[role=status]').inner_text()
                        buttons.nth(1).click()
                        page.wait_for_function("document.querySelector('[role=status]').getAttribute('aria-busy')==='false'")
                        assert page.evaluate('uploads.slice(-4)')==['/tmp/u30pro-wallpaper.jpg','/tmp/u30pro-wallpaper.web.jpg','/tmp/u30pro-wallpaper.live','/tmp/u30pro-wallpaper.web.live']
                    assert not errors,errors
                    if theme=='aurora' and lang=='zh-cn':
                        page.screenshot(path=str(TOP/f'work/u30pro-runtime/wallpaper-{width}-{dark}.png'),full_page=True)
                    page.close()
    browser.close()
print('PASS 24 wallpaper layouts and scene masks; repeated saves reuse one expiring toast, errors recover, save/cancel/remove/image-convert/upload flows: zh/en/tr, official/Aurora light/dark, mobile/desktop; mocked RPC only')
