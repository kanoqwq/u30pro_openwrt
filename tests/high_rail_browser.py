"""Exercise production dashboard markup and rail painter in Chromium."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from playwright.sync_api import sync_playwright

TOP=Path(__file__).resolve().parents[1]
RES=TOP/'openwrt/luci-app-mu300/htdocs/luci-static/resources'

if __name__=='__main__':
    sources=[(RES/p).read_text(encoding='utf-8') for p in ['mu300/common.js','view/mu300/home.js']]
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
        for width in [360,1280]:
            for lang,label in [('zh','高铁模式运行中...'),('en','High-speed rail mode active...'),('tr','Hızlı tren modu etkin...')]:
                page=browser.new_page(viewport={'width':width,'height':900})
                page.set_content('<main id="app"></main>')
                page.evaluate('''([sources,lang])=>{
                    const base={extend:x=>x},L={env:{lang},url:(...x)=>'/'+x.join('/')};
                    const M=new Function('rpc','baseclass','L',sources[0])({declare:()=>()=>Promise.resolve({})},base,L);
                    window.home=new Function('view','uci','R','M','SimRadio','Boot','L',sources[1])(base,{}, {},M,{}, {},L);
                    document.querySelector('#app').innerHTML=home.html();
                    M.injectCss();M.localize(document.querySelector('#app'));
                }''',[sources,lang])
                banner=page.locator('#mud-high-rail-notice')
                assert not banner.is_visible()
                page.evaluate("home.paintHighRail({supported:true,known:true,active:true})")
                assert banner.is_visible() and banner.inner_text().strip()==label
                icon=banner.locator('svg')
                assert icon.get_attribute('aria-hidden')=='true'
                assert icon.get_attribute('viewBox')=='0 0 1024 1024'
                original=ET.fromstring((TOP/'devices/u30pro/assets/high-rail.svg').read_bytes())
                assert icon.locator('path').evaluate_all('nodes=>nodes.map(n=>n.getAttribute("d"))')==[n.attrib['d'] for n in original]
                assert not any(c in banner.inner_text() for c in '【】')
                box=banner.bounding_box();glyph=icon.bounding_box();label_box=banner.locator('b').bounding_box()
                assert glyph['width']==glyph['height']==24
                assert abs((glyph['y']+12)-(label_box['y']+label_box['height']/2))<2
                assert label_box['x']>glyph['x']+glyph['width']
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                assert page.evaluate("document.querySelector('#mud-high-rail-notice').nextElementSibling.classList.contains('mud-body')")
                for invalid in [None,{}, {'supported':True,'known':False,'active':True},
                                {'supported':True,'known':True,'active':'1'},
                                {'supported':True,'known':True,'active':False}]:
                    page.evaluate('state=>home.paintHighRail(state)',invalid)
                    assert not banner.is_visible()
                page.close()
        browser.close()
    print(json.dumps({'cases':6,'result':'Pro banner entry/exit, unknown/error and three languages passed'}))
