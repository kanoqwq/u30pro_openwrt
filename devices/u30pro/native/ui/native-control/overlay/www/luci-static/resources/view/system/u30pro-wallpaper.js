'use strict';
'require view';
'require rpc';
'require request';
'require mu300.common as M';

/* System > Screen > Wallpaper: a picture or a short video as the wallpaper of the screen, and the look of the glass over it
 * (u30pro-wallpaper, /usr/share/u30pro/wallpaper.uc; the screen side is tools/ui/wall.h).  The browser does the work: it cuts the picture
 * or every frame of the video to the 240x240 screen (centred, cover) and encodes pictures or lossless tile deltas; a video becomes a "U3LW" clip of up to 20 seconds.
 * The same is made at 480x480 for the web pages (the overview's picture of the screen is sharp with it on a high-density display).  The
 * files go up through cgi-upload and the router only checks and stores them. */
var callGet = rpc.declare({ object: 'u30pro-wallpaper', method: 'get' });
var callImage = rpc.declare({ object: 'u30pro-wallpaper', method: 'image' });
var callSet = rpc.declare({ object: 'u30pro-wallpaper', method: 'set', params: [ 'dim', 'glass', 'blur', 'tint', 'pages', 'fast_panel' ] });
var callInstall = rpc.declare({ object: 'u30pro-wallpaper', method: 'install' });
var callRemove = rpc.declare({ object: 'u30pro-wallpaper', method: 'remove' });

var TEXT = {
  "High refresh": ["高刷新", "Yüksek yenileme"],
  "Use 96 MHz during swipes and high frame rate wallpapers, returning to the stock 48 MHz when idle. Up to about 53 fps; off by default. This exceeds the panel's stock clock. Turn it off if you see specks, shifted lines or wrong colours.": ["翻页和高帧率动态壁纸播放时使用 96 MHz，空闲后恢复原厂 48 MHz，最高约 53 帧/秒，默认关闭。此模式超出屏幕原厂时钟；若出现花点、错位或颜色异常，请关闭。", "Kaydırma ve yüksek kare hızlı duvar kâğıtlarında 96 MHz kullanır, boşta stok 48 MHz'e döner. Yaklaşık 53 kare/sn; varsayılan olarak kapalıdır. Panelin stok saatini aşar. Noktalar, kaymış çizgiler veya yanlış renkler görürseniz kapatın."],
  "%d fps (needs high refresh)": ["%d 帧/秒（需开启高刷新）", "%d kare/sn (yüksek yenileme gerekir)"],
  "It was converted in the older way (JPEG frames): set it again for a sharper picture and less work for the screen.": ["这段动态壁纸采用旧版 JPEG 帧格式；重新选择原视频设置，可提升清晰度并减少屏幕处理开销。", "Bu canlı duvar kâğıdı eski JPEG kareleriyle dönüştürülmüş; daha net görüntü ve daha az ekran işlemi için videoyu yeniden seçin."],
  "Screen wallpaper": [
    "屏幕壁纸",
    "Ekran duvar kâğıdı"
  ],
  "Wallpaper": [
    "屏幕壁纸",
    "Duvar kâğıdı"
  ],
  "Glass": [
    "玻璃效果",
    "Cam efekti"
  ],
  "Night blue": [
    "深夜蓝",
    "Gece mavisi"
  ],
  "Graphite": [
    "石墨灰",
    "Grafit"
  ],
  "White fog": [
    "雾白",
    "Beyaz sis"
  ],
  "Theme colour": [
    "主题色",
    "Tema rengi"
  ],
  "Off (still frame)": [
    "关闭（静态画面）",
    "Kapalı (sabit kare)"
  ],
  "Lock screen": [
    "锁屏",
    "Kilit ekranı"
  ],
  "Lock screen and home page": [
    "锁屏与主页",
    "Kilit ekranı ve ana sayfa"
  ],
  "%d s": [
    "%d 秒",
    "%d sn"
  ],
  "%d fps": [
    "%d 帧/秒",
    "%d kare/sn"
  ],
  "The browser cannot encode JPEG.": [
    "当前浏览器无法生成 JPEG 图片。",
    "Bu tarayıcı JPEG oluşturamıyor."
  ],
  "Upload failed: %s": [
    "上传失败：%s",
    "Yükleme başarısız: %s"
  ],
  "Choose a picture or video…": [
    "选择图片或视频…",
    "Resim veya video seç…"
  ],
  "Set as wallpaper": [
    "设为壁纸",
    "Duvar kâğıdı yap"
  ],
  "Remove wallpaper": [
    "移除壁纸",
    "Duvar kâğıdını kaldır"
  ],
  "No wallpaper: the screen shows its plain background.": [
    "尚未设置壁纸，屏幕使用纯色背景。",
    "Duvar kâğıdı yok; ekran düz arka planı gösteriyor."
  ],
  "Live wallpaper: %d frames at %d fps, %s.": [
    "动态壁纸：%d 帧，%d 帧/秒，%s。",
    "Canlı duvar kâğıdı: %d kare, %d kare/sn, %s."
  ],
  "Picture": [
    "静态图片",
    "Resim"
  ],
  "This browser cannot read the picture.": [
    "当前浏览器无法读取这张图片。",
    "Bu tarayıcı resmi okuyamıyor."
  ],
  "This browser cannot read the video.": [
    "当前浏览器无法读取这个视频。",
    "Bu tarayıcı videoyu okuyamıyor."
  ],
  "Converting the video: frame %d of %d": [
    "正在转换视频：第 %d / %d 帧",
    "Video dönüştürülüyor: %d / %d kare"
  ],
  "Live wallpaper ready: %d frames at %d fps, %s.": [
    "动态壁纸已准备：%d 帧，%d 帧/秒，%s。",
    "Canlı duvar kâğıdı hazır: %d kare, %d kare/sn, %s."
  ],
  "Picture ready.": [
    "图片已准备，点击“设为壁纸”应用。",
    "Resim hazır. Uygulamak için duvar kâğıdı yapın."
  ],
  "Uploading…": [
    "正在上传并应用壁纸…",
    "Duvar kâğıdı yükleniyor ve uygulanıyor…"
  ],
  "The wallpaper is on the screen.": [
    "壁纸已应用到屏幕。",
    "Duvar kâğıdı ekrana uygulandı."
  ],
  "Remove the wallpaper? The screen goes back to its plain background.": [
    "确定移除壁纸吗？屏幕将恢复纯色背景。",
    "Duvar kâğıdı kaldırılsın mı? Ekran düz arka plana döner."
  ],
  "Saved; the screen shows it now.": [
    "已保存，屏幕效果已更新。",
    "Kaydedildi; ekran güncellendi."
  ],
  "Save": [
    "保存设置",
    "Ayarları kaydet"
  ],
  "Video length": [
    "视频时长",
    "Video süresi"
  ],
  "Video frame rate": [
    "视频帧率",
    "Video kare hızı"
  ],
  "A picture or the first seconds of a video, cut to the round screen from the middle. The conversion runs in this browser.": [
    "选择图片或视频的开头片段，居中裁切为圆形屏幕壁纸。转换在当前浏览器中完成。",
    "Resim veya videonun başlangıcı yuvarlak ekrana ortalanarak kırpılır. Dönüştürme bu tarayıcıda yapılır."
  ],
  "Glass transparency": [
    "玻璃透明度",
    "Cam saydamlığı"
  ],
  "Glass blur": [
    "玻璃模糊度",
    "Cam bulanıklığı"
  ],
  "Glass colour": [
    "玻璃颜色",
    "Cam rengi"
  ],
  "Darken the wallpaper": [
    "壁纸暗化",
    "Duvar kâğıdını karart"
  ],
  "Play the live wallpaper on": [
    "动态壁纸播放范围",
    "Canlı duvar kâğıdının oynatıldığı yer"
  ],
  "It plays while the page is still and stops on a touch; elsewhere the frame it stopped at stays the wallpaper.": [
    "页面静止时播放，触摸时暂停；其他页面使用暂停时的画面。",
    "Sayfa dururken oynatılır, dokununca durur; diğer sayfalarda son kare gösterilir."
  ],
  "The same settings are on the screen under Functions > Display once a wallpaper is set.": [
    "设置壁纸后，也可在设备屏幕的“功能 → 显示”中调整这些效果。",
    "Duvar kâğıdı ayarlandıktan sonra bu seçenekler cihazda İşlevler > Ekran altında da bulunur."
  ],
  "Preparing the picture…": [
    "正在准备图片…",
    "Resim hazırlanıyor…"
  ],
  "Removing…": [
    "正在移除壁纸…",
    "Duvar kâğıdı kaldırılıyor…"
  ],
  "Saving…": [
    "正在保存设置…",
    "Ayarlar kaydediliyor…"
  ],
  "Cancel": [
    "取消",
    "İptal"
  ],
  "Cannot save the settings": [
    "无法保存设置",
    "Ayarlar kaydedilemiyor"
  ],
  "Cannot store the clip": [
    "无法保存动态壁纸，请检查可用空间",
    "Klip kaydedilemiyor; boş alanı kontrol edin"
  ],
  "Cannot store the picture": [
    "无法保存图片，请检查可用空间",
    "Resim kaydedilemiyor; boş alanı kontrol edin"
  ],
  "The uploaded picture is not a JPEG of at most 4 MB": [
    "图片格式无效，请使用不超过 4 MB 的 JPEG 图片",
    "Resim geçersiz; en fazla 4 MB JPEG kullanın"
  ],
  "Cannot prepare wallpaper storage": [
    "无法准备壁纸存储目录",
    "Duvar kâğıdı depolama alanı hazırlanamadı"
  ],
  "Everywhere": ["全部界面", "Her yerde"],
  "Home page": ["主页", "Ana sayfa"],
  "Signal page": ["信号页", "Sinyal sayfası"],
  "Traffic page": ["流量页", "Trafik sayfası"],
  "Functions": ["功能列表", "İşlevler"],
  "Pages under Functions": ["功能里的各页", "İşlevlerin alt sayfaları"],
  "Control centre and SMS list": ["控制中心和短信列表", "Kontrol merkezi ve SMS listesi"],
  "PIN pad": ["密码盘", "PIN tuş takımı"],
  "Pop-ups (QR code, SMS, power menu)": ["弹窗（二维码、短信、电源菜单）", "Açılır pencereler (QR kodu, SMS, güç menüsü)"],
  "It plays on selected scenes while the screen is still and pauses on a touch, swipe or scrolling list. Playback uses additional CPU and battery; unselected scenes keep a still frame.": ["在勾选的界面静止时播放，触摸、翻页或列表滚动时暂停。播放会增加 CPU 与电量消耗；未勾选的界面保持静态画面。", "Seçili ekranlar hareketsizken oynatılır; dokunma, kaydırma veya liste kaydırmada duraklar. Oynatma CPU ve pil tüketimini artırır; seçilmeyen ekranlar sabit kareyi gösterir."]
};
function T(text) {
    var lang = M.uiLanguage(), entry = TEXT[text];
    return entry && lang !== 'en' ? entry[lang === 'tr' ? 1 : 0] : _(text);
}
function card(title, body, help) {
    return E('section', { 'class': 'mud-card' }, [
        E('h3', {}, title),
        E('p', { 'class': 'u30-wp-help' }, help),
        E('div', { 'class': 'u30-wp-card-body' }, body)
    ]);
}

var SIZE = 240, WEB = 480;
var TINTS = [ [ 0, T('Night blue') ], [ 1, T('Graphite') ], [ 2, T('White fog') ], [ 3, T('Theme colour') ] ];
/* The wp_live_pages mask is shared with wallpaper.uc and native tools/ui/wall.h. */
var SCENES = [ [ 1, T('Lock screen') ], [ 2, T('Home page') ], [ 4, T('Signal page') ], [ 8, T('Traffic page') ], [ 16, T('Functions') ],
    [ 32, T('Pages under Functions') ], [ 64, T('Control centre and SMS list') ], [ 128, T('PIN pad') ], [ 256, T('Pop-ups (QR code, SMS, power menu)') ] ];
var ALL_SCENES = 511;
var LENGTHS = [ 5, 10, 15, 20 ], RATES = [ 15, 24, 30, 50 ];

function check(r) {
	if (r && r.error) throw new Error(T(r.error));
	return r;
}

/* draw the square s x s at (sx, sy) of src onto the whole of ctx's square canvas.  Browsers scale a drawImage bilinearly from a few source
 * pixels, so one large reduction aliases (a 4K video came out soft and shimmering, 9 dB further from an exact average than the stepwise
 * result); halving step by step averages every source pixel, and only the last step is less than 2:1 */
var steps = {};
function shrink(ctx, src, sx, sy, s) {
	var size = ctx.canvas.width;
	for (var n = Math.round(s / 2); n > size; n = Math.round(n / 2)) {
		var c = steps[n] || (steps[n] = E('canvas', { 'width': n, 'height': n })), x = c.getContext('2d');
		x.imageSmoothingQuality = 'high';
		x.clearRect(0, 0, n, n);
		x.drawImage(src, sx, sy, s, s, 0, 0, n, n);
		src = c; sx = sy = 0; s = n;
	}
	ctx.imageSmoothingQuality = 'high';
	ctx.clearRect(0, 0, size, size);
	ctx.drawImage(src, sx, sy, s, s, 0, 0, size, size);
}

/* draw a picture or a video frame centred and cut to a square on the WEB-sized canvas */
function cover(ctx, src, w, h) {
	var s = Math.min(w, h);
	shrink(ctx, src, (w - s) / 2, (h - s) / 2, s);
}

/* the screen's size from the web-sized canvas: a 2:1 reduction */
var small = null;
function screenSize(canvas) {
	if (!small) small = E('canvas', { 'width': SIZE, 'height': SIZE });
	shrink(small.getContext('2d'), canvas, 0, 0, WEB);
	return small;
}

/* frames packed into a "U3LW" clip: a 16-byte header (magic, version, fps, width, height, tile side or 0, frame count), then length + frame.
 * Version 1: JPEG frames (the 480x480 web copy, and the screen's clip when the browser has no CompressionStream); version 2: the screen's
 * clip as zlib frames of 16x16 tile deltas (tools/ui/wall.h): lossless, and the screen only inflates and adds the tiles that changed */
var TILE = 16, TX = SIZE / TILE, TMAP = Math.ceil(TX * TX / 8);
function pack(frames, fps, size, version) {
	var head = new DataView(new ArrayBuffer(16)), parts = [ head.buffer ];
	[ 85, 51, 76, 87 ].forEach(function(c, i) { head.setUint8(i, c); });
	head.setUint8(4, version || 1);
	head.setUint8(5, fps);
	head.setUint16(6, size, true);
	head.setUint16(8, size, true);
	head.setUint16(10, version == 2 ? TILE : 0, true);
	head.setUint32(12, frames.length, true);
	frames.forEach(function(b) {
		var l = new DataView(new ArrayBuffer(4));
		l.setUint32(0, b.size, true);
		parts.push(l.buffer, b);
	});
	return new Blob(parts, { type: 'application/octet-stream' });
}

/* the SIZE x SIZE canvas as R G B bytes */
function rgbOf(canvas) {
	var d = canvas.getContext('2d').getImageData(0, 0, SIZE, SIZE).data, o = new Uint8Array(SIZE * SIZE * 3);

	for (var i = 0, j = 0; i < d.length; i += 4) { o[j++] = d[i]; o[j++] = d[i + 1]; o[j++] = d[i + 2]; }
	return o;
}

/* a version 2 frame before compression: 0 and every pixel (the first), or 1, the bitmap of the tiles that differ from prev and their
 * per-channel differences (mod 256) */
function tileDelta(prev, cur) {
	if (!prev) { var key = new Uint8Array(1 + cur.length); key.set(cur, 1); return key; }
	var bits = new Uint8Array(TMAP), tiles = [];
	for (var t = 0; t < TX * TX; t++) {
		var x0 = (t % TX) * TILE, y0 = Math.floor(t / TX) * TILE, same = true, y, k, o;
		for (y = 0; y < TILE && same; y++)
			for (k = 0, o = ((y0 + y) * SIZE + x0) * 3; k < TILE * 3; k++) if (cur[o + k] !== prev[o + k]) { same = false; break; }
		if (same) continue;
		var d = new Uint8Array(TILE * TILE * 3), p = 0;
		for (y = 0; y < TILE; y++)
			for (k = 0, o = ((y0 + y) * SIZE + x0) * 3; k < TILE * 3; k++) d[p++] = (cur[o + k] - prev[o + k]) & 255;
		bits[t >> 3] |= 1 << (t & 7);
		tiles.push(d);
	}
	var out = new Uint8Array(1 + TMAP + tiles.length * TILE * TILE * 3), q = 1 + TMAP;
	out[0] = 1;
	out.set(bits, 1);
	tiles.forEach(function(d) { out.set(d, q); q += d.length; });
	return out;
}

/* zlib (CompressionStream "deflate" is the zlib format) */
function zlib(bytes) {
	// LuCI evaluates modules in a scope containing its XHR Response class.
	// CompressionStream needs the browser Fetch Response, not that wrapper.
	return new window.Response(new Blob([ bytes ]).stream().pipeThrough(new CompressionStream('deflate'))).blob();
}

function jpeg(canvas, q) {
	return new Promise(function(resolve, reject) {
		canvas.toBlob(function(b) { b ? resolve(b) : reject(new Error(T('The browser cannot encode JPEG.'))); }, 'image/jpeg', q);
	});
}

function upload(path, blob) {
	var data = new FormData();
	data.append('sessionid', rpc.getSessionID());
	data.append('filename', path);
	data.append('filedata', blob);
	return request.post(L.env.cgi_base + '/cgi-upload', data, { timeout: 0 }).then(function(res) {
		var r = res.json();
		if (!res.ok || !r || r.failure) throw new Error(T('Upload failed: %s').format(r && r.message ? r.message : res.statusText));
		return r;
	});
}

function opt(pair, cur) { return E('option', { 'value': String(pair[0]), 'selected': String(pair[0]) === String(cur) ? '' : null }, pair[1]); }

return view.extend({
	load: function() {
		return Promise.all([ L.resolveDefault(callGet(), {}), L.resolveDefault(callImage(), {}) ]);
	},

	render: function(data) {
		M.injectCss();
		Array.prototype.forEach.call(document.querySelectorAll('a[href*="/system/u30pro-wallpaper"]'), function(a) { a.textContent = T('Screen wallpaper'); });
		var self = this, info = data[0] || {}, img = data[1] || {};
		var notice = null, noticeTimer = null;
		function notify(message, type) {
			if (noticeTimer) clearTimeout(noticeTimer);
			if (notice) notice.update(T(message), type);
			else notice = M.toast(T(message), { type: type, timeout: 0 });
			noticeTimer = setTimeout(function() {
				notice.close(); notice = null; noticeTimer = null;
			}, type === 'error' ? 6000 : 3500);
		}
		var canvas = E('canvas', { 'width': WEB, 'height': WEB, 'class': 'u30-wp-canvas' });
		var ctx = canvas.getContext('2d');
		var status = E('div', { 'class': 'u30-wp-status', 'role': 'status', 'aria-live': 'polite' });
		var file = E('input', { 'type': 'file', 'accept': 'image/*,video/*', 'style': 'display:none' });
		var length = E('select', { 'class': 'cbi-input-select' }, LENGTHS.map(function(s) { return opt([ s, T('%d s').format(s) ], 10); }));
		var rate = E('select', { 'class': 'cbi-input-select' }, RATES.map(function(f) {
			return opt([ f, T(f > 30 ? '%d fps (needs high refresh)' : '%d fps').format(f) ], 24);
		}));
		var working = false;
		function setBusy(active, message) {
			working = active; status.classList.toggle('busy', active); status.setAttribute('aria-busy', String(active));
			if (message) status.textContent = message;
			[choose, remove, apply, save, length, rate, tint, live, fast, glass.input, blur.input, dim.input].forEach(function(el) { if(el) el.disabled = active; });
			if (!active) { apply.disabled = !pending; remove.disabled = !self.info.picture; }
		}
		var pending = null;	/* {jpg, web: Blob, live, webLive: Blob|null} waiting for Apply */

		this.info = info;
		var choose = E('button', { 'type': 'button', 'class': 'mud-btn', 'click': function() { file.click(); } }, T('Choose a picture or video…'));
		var apply = E('button', { 'type': 'button', 'class': 'mud-btn on', 'disabled': '' }, T('Set as wallpaper'));
		var remove = E('button', { 'type': 'button', 'class': 'mud-btn warn', 'disabled': info.picture ? null : '' }, T('Remove wallpaper'));

		function describe() {
			var i = self.info;
			if (pending) return;
			status.textContent = !i.picture ? T('No wallpaper: the screen shows its plain background.') :
				(i.live ? T('Live wallpaper: %d frames at %d fps, %s.').format(i.frames, i.fps, '%1024mB'.format(i.live_bytes)) +
					(i.live_version === 1 ? ' ' + T("It was converted in the older way (JPEG frames): set it again for a sharper picture and less work for the screen.") : '') : T('Picture'));
		}

		function showStored(im) {
			ctx.clearRect(0, 0, WEB, WEB);
			if (!im || !im.data) { ctx.fillStyle = '#0b1220'; ctx.fillRect(0, 0, WEB, WEB); return; }
			var p = new Image();
			p.onload = function() { ctx.imageSmoothingQuality = 'high'; ctx.drawImage(p, 0, 0, WEB, WEB); };
			p.src = 'data:' + (im.type || 'image/jpeg') + ';base64,' + im.data;
		}

		function picture(f) {
			return new Promise(function(resolve, reject) {
				var p = new Image(), url = URL.createObjectURL(f);
				p.onload = function() { URL.revokeObjectURL(url); cover(ctx, p, p.naturalWidth, p.naturalHeight); resolve(); };
				p.onerror = function() { URL.revokeObjectURL(url); reject(new Error(T('This browser cannot read the picture.'))); };
				p.src = url;
			}).then(function() { return Promise.all([ jpeg(screenSize(canvas), .9), jpeg(canvas, .9) ]); }).then(function(b) {
				return { jpg: b[0], web: b[1], live: null, webLive: null };
			});
		}

		/* Screen clips use lossless tile deltas with CompressionStream, legacy JPEG otherwise. Web clips stay JPEG. */
		function video(f) {
			var v2 = typeof CompressionStream == 'function', prev = null;
			var fps = +rate.value, secs = +length.value, v = E('video', { 'muted': '', 'playsinline': '', 'preload': 'auto' }), url = URL.createObjectURL(f);
			v.muted = true;
			return new Promise(function(resolve, reject) {
				v.onloadeddata = resolve;
				v.onerror = function() { reject(new Error(T('This browser cannot read the video.'))); };
				v.src = url;
			}).then(function() {
				var n = Math.max(1, Math.min(Math.floor(Math.min(v.duration || 0, secs) * fps), secs * fps)), frames = [], web = [], first = null;
				function seek(t) {
					if (Math.abs(v.currentTime - t) < 0.00001 && v.readyState >= 2) return Promise.resolve();
					return new Promise(function(resolve) { v.onseeked = function() { v.onseeked = null; resolve(); }; v.currentTime = t; });
				}
				function step(i) {
					if (i >= n) return Promise.resolve();
					status.textContent = T('Converting the video: frame %d of %d').format(i + 1, n);
					return seek(i / fps).then(function() {
						cover(ctx, v, v.videoWidth, v.videoHeight);
						var small = screenSize(canvas), screen;
						if (v2) { var rgb = rgbOf(small); screen = zlib(tileDelta(prev, rgb)); prev = rgb; }
						else screen = jpeg(small, .8);
						return Promise.all([ screen, jpeg(canvas, .8), i ? null : jpeg(small, .9), i ? null : jpeg(canvas, .9) ]);
					}).then(function(b) {
						frames.push(b[0]);
						web.push(b[1]);
						if (b[2]) first = { jpg: b[2], web: b[3] };
						return step(i + 1);
					});
				}
				return step(0).then(function() {
					return seek(0).then(function() { cover(ctx, v, v.videoWidth, v.videoHeight); return { jpg: first.jpg, web: first.web, live: pack(frames, fps, SIZE, v2 ? 2 : 1), webLive: pack(web, fps, WEB, 1), frames: frames.length, fps: fps }; });
				});
			}).finally(function() { URL.revokeObjectURL(url); v.removeAttribute('src'); v.load(); });
		}

		file.addEventListener('change', function() {
			var f = file.files[0];
			file.value = '';
			if (!f || working) return;
			pending = null;
			setBusy(true, T('Preparing the picture…'));
			(/^video\//.test(f.type) ? video(f) : picture(f)).then(function(p) {
				pending = p;
				status.textContent = p.live ? T('Live wallpaper ready: %d frames at %d fps, %s.').format(p.frames, p.fps, '%1024mB'.format(p.live.size)) :
					T('Picture ready.');
				apply.disabled = false;
			}).catch(function(e) {
				status.textContent = e.message;
				showStored(self.img);
			}).finally(function() { setBusy(false); });
		});

		apply.addEventListener('click', function() {
			if (!pending || working) return;
			setBusy(true);
			status.textContent = T('Uploading…');
			var p = pending;
			upload('/tmp/u30pro-wallpaper.jpg', p.jpg).then(function() {
				return upload('/tmp/u30pro-wallpaper.web.jpg', p.web);
			}).then(function() {
				return p.live ? upload('/tmp/u30pro-wallpaper.live', p.live) : null;
			}).then(function() {
				return p.webLive ? upload('/tmp/u30pro-wallpaper.web.live', p.webLive) : null;
			}).then(function() { return callInstall(); }).then(check).then(function(r) {
				pending = null;
				self.info = r.wallpaper || {};
				notify('The wallpaper is on the screen.', 'success');
				return L.resolveDefault(callImage(), null).then(function(im) { if(im) self.img=im; });
			}).catch(function(e) {
				notify(e.message, 'error');
				apply.disabled = false;
			}).finally(function() {
				setBusy(false);
				describe();
			});
		});

        remove.addEventListener('click', function() {
            if (working) return;
            M.confirmBox(T('Remove wallpaper'), T('Remove the wallpaper? The screen goes back to its plain background.'), {
                danger: true, okText: T('Remove wallpaper'), cancelText: T('Cancel')
            }).then(function(confirmed) {
                if (!confirmed || working) return;
                setBusy(true, T('Removing…'));
                return callRemove().then(check).then(function(r) {
                    self.info = r.wallpaper || {}; self.img = null; pending = null;
                    showStored(null);
                }).catch(function(e) { notify(e.message, 'error'); }).finally(function() {
                    setBusy(false); describe();
                });
            });
        });

		/* the look */
		var st = info.settings || {};
		var fast = E('input', { 'type': 'checkbox', 'aria-label': T('High refresh') });
		fast.checked = st.fast_panel === 1;
		function range(min, max, step, value, unit) {
			var out = E('span', { 'class': 'u30-wp-val' }), inp = E('input', { 'type': 'range', 'min': min, 'max': max, 'step': step, 'value': value });
			var paint = function() { out.textContent = inp.value + (unit || ''); };
			inp.addEventListener('input', paint);
			paint();
			return { input: inp, el: E('div', { 'class': 'u30-wp-range' }, [ inp, out ]) };
		}
		var glass = range(0, 100, 5, st.glass != null ? st.glass : 50, '%'), blur = range(0, 100, 5, st.blur != null ? st.blur : 50);
		var dim = range(0, 90, 5, st.dim != null ? st.dim : 30, '%');
		var tint = E('select', { 'class': 'cbi-input-select' }, TINTS.map(function(t) { return opt(t, st.tint || 0); }));
        var pages = st.pages != null ? st.pages : (st.live === 0 ? 0 : st.live === 1 ? 1 : 3), boxes = [];
        function scene(bit, label) {
            var box = E('input', { 'type': 'checkbox', 'value': String(bit) });
            box.checked = bit === ALL_SCENES ? pages === ALL_SCENES : !!(pages & bit);
            return { box: box, el: E('label', { 'class': 'u30-wp-scene' }, [ box, E('span', {}, label) ]) };
        }
        var all = scene(ALL_SCENES, T('Everywhere'));
        SCENES.forEach(function(t) { boxes.push(scene(t[0], t[1])); });
        function mask() { return boxes.reduce(function(m, b) { return b.box.checked ? m | +b.box.value : m; }, 0); }
        all.box.addEventListener('change', function() { boxes.forEach(function(b) { b.box.checked = all.box.checked; }); });
        boxes.forEach(function(b) { b.box.addEventListener('change', function() { all.box.checked = mask() === ALL_SCENES; }); });
        var live = E('fieldset', { 'class': 'u30-wp-scenes', 'aria-label': T('Play the live wallpaper on') },
            [ all.el ].concat(boxes.map(function(b) { return b.el; })));
		var save = E('button', { 'type': 'button', 'class': 'mud-btn on', 'click': function() {
			if (working) return;
			setBusy(true, T('Saving…'));
			return callSet(+dim.input.value, +glass.input.value, +blur.input.value, +tint.value, mask(), fast.checked ? 1 : 0).then(check).then(function() {
				notify('Saved; the screen shows it now.', 'success');
			}).catch(function(e) { notify(e.message, 'error'); }).finally(function() { setBusy(false); describe(); });
		} }, T('Save'));

		function row(title, field, descr) {
			return E('div', { 'class': 'cbi-value' }, [ E('label', { 'class': 'cbi-value-title' }, title),
				E('div', { 'class': 'cbi-value-field' }, [ field, descr ? E('div', { 'class': 'cbi-value-description' }, descr) : '' ]) ]);
		}

		this.img = img;
		showStored(img);
		describe();

		return E('div', { 'class': 'mud-wallpaper' }, [
            E('style', {}, `
.mud-wallpaper{color:var(--text,var(--text-color-high,#222));display:grid;gap:18px;min-width:0}
.mud-wallpaper h2{margin:0;font-size:1.4rem}
.mud-wallpaper .mud-card>h3{font-size:1rem;letter-spacing:normal;color:inherit;margin-bottom:10px}
.mud-wallpaper .u30-wp-help{color:var(--text-muted,var(--text-color-medium,#666));line-height:1.65;margin:0 0 20px}
.mud-wallpaper .u30-wp{display:flex;flex-wrap:wrap;gap:24px;align-items:center}
.mud-wallpaper .u30-wp-canvas{width:200px;height:200px;max-width:100%;border-radius:50%;background:var(--surface-sunken,#0b1220);box-shadow:0 0 0 6px var(--surface-sunken,rgba(127,127,127,.15));flex:none;margin:6px}
.mud-wallpaper .u30-wp-side{flex:1 1 240px;min-width:0;display:grid;gap:16px}
.mud-wallpaper .u30-wp-btns{display:flex;flex-wrap:wrap;gap:10px;margin:4px 0}
.mud-wallpaper .mud-btn{white-space:normal;min-height:40px;line-height:1.5;height:auto;max-width:100%;margin:0}
.mud-wallpaper .cbi-value{display:grid;grid-template-columns:minmax(130px,1fr) minmax(0,2fr);gap:12px 24px;padding:14px 0;margin:0;border-bottom:1px solid var(--hairline,var(--border-color-low,#ddd))}
.mud-wallpaper .cbi-value-title{float:none;width:auto;text-align:left;line-height:1.6;padding:5px 0;margin:0}
.mud-wallpaper .cbi-value-field{margin:0;min-width:0;padding:0}
.mud-wallpaper .cbi-value-description{color:var(--text-muted,var(--text-color-medium,#666));line-height:1.6;margin-top:8px}
.mud-wallpaper select{width:100%;max-width:420px;min-width:0;min-height:40px;height:auto;background:var(--surface,var(--background-color-high,#fff));color:inherit;border:1px solid var(--hairline,var(--border-color-low,#ddd));border-radius:var(--radius-base,.5rem);padding:8px 12px;font:inherit}
.mud-wallpaper .u30-wp-range{display:flex;align-items:center;gap:12px;max-width:420px;min-height:40px}
.mud-wallpaper input[type=range]{flex:1;min-width:0;width:100%;accent-color:var(--brand,var(--primary-color-high,#2f7bf6));margin:0}
.mud-wallpaper .u30-wp-val{min-width:44px;text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
.mud-wallpaper .u30-wp-scenes{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(200px,100%),1fr));gap:10px 16px;min-width:0;margin:0;padding:0;border:0}
.mud-wallpaper .u30-wp-scene{display:flex;align-items:flex-start;gap:8px;min-width:0;line-height:1.5;cursor:pointer;overflow-wrap:anywhere}
.mud-wallpaper .u30-wp-scene input{flex:none;margin:4px 0 0;accent-color:var(--brand,var(--primary-color-high,#2f7bf6))}
.mud-wallpaper .u30-wp-scenes:disabled{opacity:.65}
.mud-wallpaper .u30-wp-status{line-height:1.6;overflow-wrap:anywhere}
.mud-wallpaper .u30-wp-status.busy:before{content:'';display:inline-block;width:14px;height:14px;margin-right:8px;vertical-align:-2px;border:2px solid var(--hairline,#ccc);border-top-color:var(--brand,#2f7bf6);border-radius:50%;animation:u30-wp-spin .8s linear infinite}
@keyframes u30-wp-spin{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.mud-wallpaper .u30-wp-status.busy:before{animation:none}}
@media(max-width:600px){.mud-wallpaper .cbi-value{grid-template-columns:1fr;gap:6px}.mud-wallpaper .u30-wp{justify-content:center}.mud-wallpaper .u30-wp-btns>*{flex:1 1 140px}.mud-wallpaper .mud-card{padding:16px}}
`),
			E('h2', {}, T('Wallpaper')),
			card(T('Wallpaper'), [
				E('div', { 'class': 'u30-wp' }, [ canvas, E('div', { 'class': 'u30-wp-side' }, [
					status,
					E('div', { 'class': 'u30-wp-btns' }, [ choose, apply, remove ]),
					row(T('Video length'), length), row(T('Video frame rate'), rate)
				]) ]),
				file
			], T('A picture or the first seconds of a video, cut to the round screen from the middle. The conversion runs in this browser.')),
			card(T('Glass'), [
				row(T('High refresh'), fast, T("Use 96 MHz during swipes and high frame rate wallpapers, returning to the stock 48 MHz when idle. Up to about 53 fps; off by default. This exceeds the panel's stock clock. Turn it off if you see specks, shifted lines or wrong colours.")),
				row(T('Glass transparency'), glass.el),
				row(T('Glass blur'), blur.el),
				row(T('Glass colour'), tint),
				row(T('Darken the wallpaper'), dim.el),
				row(T('Play the live wallpaper on'), live, T('It plays on selected scenes while the screen is still and pauses on a touch, swipe or scrolling list. Playback uses additional CPU and battery; unselected scenes keep a still frame.')),
				E('div', { 'class': 'u30-wp-btns' }, save)
			], T('The same settings are on the screen under Functions > Display once a wallpaper is set.'))
		]);
	},

	handleSaveApply: null,
	handleSave: null,
	handleReset: null
});
