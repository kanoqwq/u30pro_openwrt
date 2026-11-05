"""Actual browser canvas scaling of production picture/video-frame helpers."""
from pathlib import Path
from playwright.sync_api import sync_playwright

TOP=Path(__file__).resolve().parents[1]
source=(TOP/'devices/u30pro/native/ui/native-control/overlay/www/luci-static/resources/view/system/u30pro-wallpaper.js').read_text(encoding='utf8')
helpers=source[source.index('var steps = {}'):source.index('/* frames packed')]
with sync_playwright() as p:
    chrome=Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
    browser=p.chromium.launch(headless=True,**({'executable_path':str(chrome)} if chrome.exists() else {}))
    page=browser.new_page()
    result=page.evaluate(r"""async helpers=>{
        const assert=(v,m)=>{if(!v)throw Error(m);};
        let calls=[];
        function canvas(w,h){const c=document.createElement('canvas');c.width=w;c.height=h;return c;}
        function E(tag,attrs){const c=canvas(attrs.width,attrs.height),x=c.getContext('2d'),draw=x.drawImage.bind(x);
            x.drawImage=(...args)=>{calls.push({width:c.width,crop:args.slice(1,5)});return draw(...args);};return c;}
        const f=new Function('E','var SIZE=240, WEB=480;'+helpers+';return {cover,screenSize,steps};')(E);
        const out=E('canvas',{width:480,height:480}),ctx=out.getContext('2d');
        const solid=(w,h,color)=>{const c=canvas(w,h),x=c.getContext('2d');x.fillStyle=color;x.fillRect(0,0,w,h);return c;};
        const pixel=c=>Array.from(c.getContext('2d').getImageData(120,120,1,1).data);
        let src=solid(3840,2160,'rgb(20,120,220)');
        f.cover(ctx,src,3840,2160);
        assert(JSON.stringify(calls.map(x=>x.width))==='[1080,540,480]','4K must shrink in steps');
        assert(JSON.stringify(calls[0].crop)==='[840,0,2160,2160]','landscape centered crop');
        assert(JSON.stringify(pixel(out))==='[20,120,220,255]','color preservation');
        const first=Object.values(f.steps);calls=[];
        f.cover(ctx,solid(2160,3840,'red'),2160,3840);
        assert(JSON.stringify(calls[0].crop)==='[0,840,2160,2160]','portrait centered crop');
        assert(Object.values(f.steps).every((c,i)=>c===first[i]),'video frame scratch canvases must be reused');
        f.cover(ctx,canvas(3840,2160),3840,2160);
        assert(pixel(out).every(x=>x===0),'transparent frame must not retain the last video frame');
        calls=[];f.cover(ctx,solid(160,80,'lime'),160,80);
        assert(calls.length===1 && calls[0].crop.join(',')==='40,0,80,80','small picture upscale and crop');
        const small=f.screenSize(out);
        assert(small.width===240 && small.height===240,'device dimensions');
        assert(JSON.stringify(pixel(small))==='[0,255,0,255]','screen picture');
        assert(f.screenSize(out)===small,'screen canvas reused across frames');
        const packed=await new Promise(resolve=>small.toBlob(resolve,'image/jpeg',.9));
        const bytes=new Uint8Array(await packed.arrayBuffer());
        assert(bytes[0]===255 && bytes[1]===216,'JPEG encoding retained');
        // Exercise an actual decoded video frame, using the same conversion path.
        const video=document.createElement('video'),videoSource=solid(1920,1080,'rgb(80,160,240)');
        const stream=videoSource.captureStream(1);video.srcObject=stream;video.muted=true;
        await video.play();
        assert(video.readyState>=2 && video.videoWidth===1920,'decoded video ready');
        calls=[];f.cover(ctx,video,video.videoWidth,video.videoHeight);
        stream.getTracks().forEach(t=>t.stop());video.pause();video.srcObject=null;
        assert(calls.map(x=>x.width).join(',')==='540,480','decoded video uses halving');
        const px=pixel(out);
        assert(Math.abs(px[0]-80)<=4 && Math.abs(px[1]-160)<=4 && Math.abs(px[2]-240)<=4 && px[3]===255,'decoded video color');
        return 'PASS: 4K and portrait center crops, halving stages, scratch reuse, transparent frames, small images, 240px JPEG and real video frames';
    }""",helpers)
    print(result)
    browser.close()
