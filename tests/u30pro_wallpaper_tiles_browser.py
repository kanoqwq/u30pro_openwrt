"""Exercise the production tile encoder in Chromium, independently decode every frame."""
import base64
from pathlib import Path
import struct
import zlib
from playwright.sync_api import sync_playwright

TOP = Path(__file__).resolve().parents[1]
source = (TOP/'devices/u30pro/native/ui/native-control/overlay/www/luci-static/resources/view/system/u30pro-wallpaper.js').read_text(encoding='utf8')
helpers = source[source.index('var TILE ='):source.index('function upload(')]
with sync_playwright() as p:
    chrome = Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
    browser = p.chromium.launch(headless=True, **({'executable_path': str(chrome)} if chrome.exists() else {}))
    page = browser.new_page()
    result = page.evaluate(r'''async helpers => {
        // LuCI modules close over an XHR Response class, not window.Response.
        class LuCIResponse { constructor(xhr) { xhr.getAllResponseHeaders(); } }
        let reproduced=false;
        try { new LuCIResponse(new Blob([]).stream()); } catch(e) { reproduced=/getAllResponseHeaders/.test(e.message); }
        if(!reproduced) throw Error('LuCI collision fixture did not reproduce');
        const f = new Function('Response','var SIZE=240;'+helpers+';return {tileDelta,zlib,pack,rgbOf,jpeg};')(LuCIResponse);
        const b64 = bytes => { let s=''; for (let b of bytes) s+=String.fromCharCode(b); return btoa(s); };
        const frames=[], raw=[]; let prev=null;
        for (let i=0;i<5;i++) {
            const cur = prev ? prev.slice() : Uint8Array.from({length:240*240*3},(_,k)=>(k*17)&255);
            if(i===1) cur[cur.length-1]^=255; // final tile, channel and bitmap bit
            if(i===2) for(let k=0;k<cur.length;k++)cur[k]=(255-cur[k]); // every tile
            if(i===4) cur[0]=(cur[0]+1)&255; // modulo arithmetic at the first pixel
            frames.push(await f.zlib(f.tileDelta(prev,cur)));raw.push(b64(cur));prev=cur;
        }
        const clip=await f.pack(frames,24,240,2).arrayBuffer();
        const c=document.createElement('canvas');c.width=c.height=240;
        c.getContext('2d').fillRect(0,0,240,240);
        const jpeg=await f.jpeg(c,.8), legacy=await f.pack([jpeg],15,240,1).arrayBuffer();
        const web=await f.pack([jpeg],15,480,1).arrayBuffer();
        return {clip:b64(new Uint8Array(clip)),raw,legacy:b64(new Uint8Array(legacy)),web:b64(new Uint8Array(web))};
    }''', helpers)
    browser.close()

clip = base64.b64decode(result['clip'])
assert struct.unpack('<4sBBHHHI',clip[:16]) == (b'U3LW',2,24,240,240,16,5)
pos=16
cur=None
for frame in result['raw']:
    length=struct.unpack_from('<I',clip,pos)[0]
    data=zlib.decompress(clip[pos+4:pos+4+length]);pos+=4+length
    if data[0]==0:
        cur=bytearray(data[1:]); assert len(cur)==240*240*3
    else:
        assert data[0]==1
        bits=data[1:30];offset=30
        for t in range(225):
            if bits[t//8] & (1<<(t%8)):
                for y in range(16):
                    o=((t//15*16+y)*240+t%15*16)*3
                    for k in range(48):cur[o+k]=(cur[o+k]+data[offset+k])&255
                    offset+=48
        assert offset==len(data)
    assert bytes(cur)==base64.b64decode(frame)
assert pos==len(clip)
for name,size in [('legacy',240),('web',480)]:
    data=base64.b64decode(result[name])
    assert struct.unpack('<4sBBHHHI',data[:16])==(b'U3LW',1,15,size,size,0,1)
    assert data[20:22]==b'\xff\xd8'
print('PASS: real Chromium lossless key/delta, unchanged/all/final tiles, wraparound, legacy JPEG and web format')
