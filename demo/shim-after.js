// Demo mode, part 2: draws the sample "footage", swaps it into the real player and export previews.
(function () {
const D = window.__demo, words = D.words, DURATION = D.DURATION;
window.__demoToast = toast;

// ---- the sample footage: a vertical phone video of someone talking at a dry lakebed ----
const SW = 720, SH = 1280;
const frame = document.createElement('canvas'); frame.width = SW; frame.height = SH;
const fc = frame.getContext('2d');
const speaking = t => words.some(w => t >= w.start && t <= w.end);
function drawScene(t) {
  const c = fc;
  const sky = c.createLinearGradient(0, 0, 0, SH * .55); sky.addColorStop(0, '#5f9fd8'); sky.addColorStop(1, '#b9d6ee');
  c.fillStyle = sky; c.fillRect(0, 0, SW, SH);
  c.fillStyle = 'rgba(255,255,255,.9)';
  [[120, 180, 70], [190, 160, 55], [560, 120, 60], [620, 140, 45]].forEach(([x, y, r]) => { c.beginPath(); c.arc(x + Math.sin(t * .05) * 10, y, r, 0, 7); c.fill() });
  const ground = c.createLinearGradient(0, SH * .52, 0, SH); ground.addColorStop(0, '#c9b48a'); ground.addColorStop(1, '#9c8457');
  c.fillStyle = ground; c.fillRect(0, SH * .52, SW, SH * .48);
  c.fillStyle = '#5d7a45';
  [[40, 30], [150, 22], [610, 34], [690, 26], [470, 18]].forEach(([x, r]) => { c.beginPath(); c.ellipse(x, SH * .52 - r * .4, r * 1.6, r, 0, 0, 7); c.fill() });
  c.strokeStyle = 'rgba(90,70,40,.25)'; c.lineWidth = 3;
  for (let i = 0; i < 9; i++) { c.beginPath(); c.moveTo(0, SH * .6 + i * 70); c.lineTo(SW, SH * .58 + i * 74); c.stroke() }
  // speaker
  const sway = Math.sin(t * 1.1) * 5, talk = speaking(t) ? Math.abs(Math.sin(t * 13)) : 0, cx = SW / 2 + sway;
  c.fillStyle = '#2b3a5c'; c.beginPath(); c.ellipse(cx, SH + 60, 330, 420, 0, Math.PI, 0); c.fill();
  c.fillStyle = '#23304d'; c.beginPath(); c.moveTo(cx - 60, SH - 330); c.lineTo(cx, SH - 250); c.lineTo(cx + 60, SH - 330); c.fill();
  c.fillStyle = '#c99573'; c.fillRect(cx - 52, SH - 470, 104, 140);
  c.beginPath(); c.ellipse(cx, SH - 590 + talk * 2, 150, 185, 0, 0, 7); c.fill();
  c.fillStyle = '#8a5a36'; c.beginPath(); c.ellipse(cx, SH - 500, 135, 90, 0, 0, Math.PI); c.fill(); // beard
  c.fillStyle = '#6b4427'; c.beginPath(); c.ellipse(cx, SH - 700, 158, 95, 0, Math.PI, 0); c.fill(); // hair
  c.fillStyle = '#2a1d16'; c.beginPath(); c.arc(cx - 52, SH - 610, 9, 0, 7); c.arc(cx + 52, SH - 610, 9, 0, 7); c.fill();
  c.fillStyle = '#5a2e22'; c.beginPath(); c.ellipse(cx, SH - 515, 34, 5 + talk * 14, 0, 0, 7); c.fill();
}

// ---- captions, mirroring the export styles ----
const STY = {kind: {hl: 'accent', upper: true}, bold: {hl: '#FFE500', upper: true}, clean: {hl: null, upper: false}};
const TSTY = {brand: ['#fff', 'primary'], accent: ['primary', 'accent'], dark: ['#fff', '#000'], outline: ['#fff', null]};
function group(t, start, end) {
  const ws = words.filter(w => w.end > start && w.start < end), gs = []; let cur = [];
  ws.forEach(w => { cur.push(w); if (cur.length >= 3 || /[.,?!]$/.test(w.word)) { gs.push(cur); cur = [] } });
  if (cur.length) gs.push(cur);
  for (let i = 0; i < gs.length; i++) {
    const g = gs[i], ge = Math.min(i + 1 < gs.length ? gs[i + 1][0].start : g[g.length - 1].end, g[g.length - 1].end + .6);
    if (t >= g[0].start && t < ge) return {g, a: g.findIndex(w => t >= w.start && t <= w.end + .04)};
  }
}
function drawCaps(c, W, H, t, r) {
  const col = Object.assign({primary: '#3C4292', accent: '#5EC3B9'}, r.colors || {}), pick = v => col[v] || v;
  const s = STY[r.caption_style] || STY.kind, hl = s.hl && pick(s.hl);
  const titleOn = r.title && t - r.start < 4, bottomTitle = titleOn && r.title_position === 'bottom';
  if (titleOn) {
    const [tc, tb] = (TSTY[r.title_style] || TSTY.brand).map(v => v && pick(v));
    const fs = Math.round(H * (H >= W ? .042 : .06)); c.font = `700 ${fs}px Inter, "Nunito Sans", sans-serif`;
    const bw = Math.min(c.measureText(r.title).width + fs * 1.2, W * .92), bh = fs * 1.6;
    const top = r.title_position === 'middle' ? (H - bh) / 2 : r.title_position === 'bottom' ? H * (H > W ? .92 : .94) - bh : H * .08;
    c.textAlign = 'center'; c.textBaseline = 'middle';
    if (tb) { c.fillStyle = tb; c.fillRect((W - bw) / 2, top, bw, bh) }
    else { c.lineJoin = 'round'; c.lineWidth = Math.max(3, fs * .14); c.strokeStyle = '#000'; c.strokeText(r.title, W / 2, top + fs * .82, W * .88) }
    c.fillStyle = tc; c.fillText(r.title, W / 2, top + fs * .82, W * .88);
  }
  if (!r.captions) return;
  const cg = group(t, r.start, r.end); if (!cg) return;
  let fs = Math.round(H * (H >= W ? .05 : .07)); c.textAlign = 'left'; c.textBaseline = 'middle';
  const parts = cg.g.map(w => (s.upper ? w.word.toUpperCase() : w.word).trim());
  const measure = () => { c.font = `800 ${fs}px Inter, "Nunito Sans", sans-serif`; const ws = parts.map(p => c.measureText(p).width), sp = c.measureText(' ').width; return [ws, sp, ws.reduce((a, b) => a + b, 0) + sp * (parts.length - 1)] };
  let [ws, sp, tot] = measure(); if (tot > W * .9) { fs = Math.floor(fs * W * .9 / tot); [ws, sp, tot] = measure() }
  let x = (W - tot) / 2; const y = H * (H > W ? .74 : .86) - (bottomTitle ? H * (H > W ? .08 : .14) : 0);
  c.lineJoin = 'round'; c.lineWidth = Math.max(3, fs * .14); c.strokeStyle = '#000';
  parts.forEach((p, i) => { c.strokeText(p, x, y); c.fillStyle = hl && i === cg.a ? hl : '#fff'; c.fillText(p, x, y); x += ws[i] + sp });
}
const ASPECT = {'9:16': [360, 640], '4:5': [400, 500], '1:1': [440, 440], '16:9': [640, 360]};
function renderOut(c, W, H, t, r) {
  drawScene(t);
  if (r.framing === 'fit') {
    c.save(); c.filter = 'blur(16px) brightness(.85)'; const s = Math.max(W / SW, H / SH); c.drawImage(frame, (W - SW * s) / 2, (H - SH * s) / 2, SW * s, SH * s); c.restore();
    const f = Math.min(W / SW, H / SH); c.drawImage(frame, (W - SW * f) / 2, (H - SH * f) / 2, SW * f, SH * f);
  } else {
    const s = Math.max(W / SW, H / SH), sw = W / s, sh = H / s, fx = r.focus_x ?? .5;
    c.drawImage(frame, (SW - sw) * fx, (SH - sh) / 2, sw, sh, 0, 0, W, H);
  }
  drawCaps(c, W, H, t, r);
}

// ---- a stand-in for the <video> player that the studio code can drive ----
let player = null;
function makePlayer() {
  const wrap = document.createElement('div'); wrap.className = 'demo-player';
  const cv = document.createElement('canvas'); cv.width = 405; cv.height = 720; cv.id = 'player';
  const bar = document.createElement('div'); bar.className = 'demo-bar';
  bar.innerHTML = '<button type="button" class="btn small" data-pp aria-label="Play">▶</button><div class="demo-scrub" data-scrub><i></i></div><span class="time" data-clock></span>';
  wrap.append(cv, bar);
  let t = 0, playing = false, last = performance.now();
  Object.defineProperty(cv, 'currentTime', {get: () => t, set: v => { t = Math.max(0, Math.min(DURATION, v)) }});
  Object.defineProperty(cv, 'paused', {get: () => !playing});
  cv.play = () => { playing = true; return Promise.resolve() };
  cv.pause = () => { playing = false };
  const ctx = cv.getContext('2d');
  bar.querySelector('[data-pp]').onclick = () => playing ? cv.pause() : cv.play();
  cv.onclick = () => playing ? cv.pause() : cv.play();
  bar.querySelector('[data-scrub]').onclick = e => { const b = e.currentTarget.getBoundingClientRect(); t = (e.clientX - b.left) / b.width * DURATION };
  function tick(now) {
    if (!cv.isConnected && wrap !== player) return;
    const dt = Math.min(.1, (now - last) / 1000); last = now;
    if (playing) { t += dt; if (t >= DURATION) { t = DURATION; playing = false } cv.dispatchEvent(new Event('timeupdate')) }
    drawScene(t); ctx.drawImage(frame, 0, 0, cv.width, cv.height);
    bar.querySelector('[data-pp]').textContent = playing ? '❚❚' : '▶';
    bar.querySelector('[data-scrub] i').style.width = (t / DURATION * 100) + '%';
    bar.querySelector('[data-clock]').textContent = `${fmt(t)} / ${fmt(DURATION)}`;
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
  cv.addEventListener('timeupdate', onTime);
  return wrap;
}

// ---- thumbnails and export previews ----
const thumb = (() => { const c = document.createElement('canvas'); c.width = 112; c.height = 72; const x = c.getContext('2d'); drawScene(25); x.drawImage(frame, 0, 380, 720, 463, 0, 0, 112, 72); return c.toDataURL('image/jpeg', .8) })();
let exportCanvases = [];
function decorate() {
  document.querySelectorAll('img[src*="/thumb"]').forEach(img => { img.src = thumb; img.onerror = null });
  const cvp = document.querySelector('canvas#player');
  if (cvp && player && cvp.parentElement !== player) { cvp.replaceWith(player); player.prepend(cvp) }
  const v = document.querySelector('video#player');
  if (v) {
    if (!player) player = makePlayer();
    const host = v.closest('.card');
    v.replaceWith(player);
    host && host.classList.add('demo-host');
  }
  exportCanvases = exportCanvases.filter(e => e.cv.isConnected);
  document.querySelectorAll('.render video').forEach(vid => {
    const m = vid.getAttribute('src').match(/renders\/(\w+)\/file/); const r = current && current.renders.find(x => x.id === (m && m[1]));
    if (!r) return;
    const [W, H] = ASPECT[r.aspect] || ASPECT['9:16'];
    const cv = document.createElement('canvas'); cv.width = W; cv.height = H; cv.className = 'demo-export'; cv.style.aspectRatio = `${W}/${H}`;
    vid.replaceWith(cv); exportCanvases.push({cv, r});
  });
}
(function loop(now) {
  exportCanvases.forEach(({cv, r}) => { if (!cv.isConnected) return; const t = r.start + ((now / 1000) % Math.max(1, r.end - r.start)); renderOut(cv.getContext('2d'), cv.width, cv.height, t, r) });
  requestAnimationFrame(loop);
})(performance.now());

// Suggested thumbnails: draw the frame instead of asking the server for it.
function demoThumbs() {
  document.querySelectorAll('img[data-thumb]').forEach(img => {
    const id = img.dataset.thumb, t = thumbTimes[id]; if (t == null) return;
    const aspect = $(`#a-${id}`)?.value || '9:16', [W, H] = ASPECT[aspect] || ASPECT['9:16'];
    const key = [t.toFixed(1), aspect, $(`#f-${id}`)?.value, $(`#x-${id}`)?.value].join('|');
    if (img.dataset.key === key) return;
    const cv = document.createElement('canvas'); cv.width = W; cv.height = H;
    renderOut(cv.getContext('2d'), W, H, t, {framing: $(`#f-${id}`)?.value || 'crop', focus_x: +($(`#x-${id}`)?.value ?? .5), captions: false});
    img.dataset.key = key; img.src = cv.toDataURL('image/jpeg', .85);
  });
}
const origThumb = refreshThumb;
refreshThumb = function (id) { origThumb(id); demoThumbs() };

// Run after every studio re-render.
const origRender = renderProject;
renderProject = function (full) {
  if (full) player = null;
  origRender(full);
  decorate(); demoThumbs();
};
const origList = loadList;
loadList = async function () { await origList(); decorate() };

// Banner explaining the demo.
const banner = document.createElement('div'); banner.className = 'demo-banner';
banner.innerHTML = '<b>Demo</b> with a made-up sample video, so you can click through everything. Upload, exports and downloads are simulated; real videos go in the live studio. <a href="#sample" data-reset>Reset demo</a>';
document.querySelector('.topbar').after(banner);
banner.querySelector('[data-reset]').onclick = e => { e.preventDefault(); openProject('sample') };
// The guide and pricing pages live in the studio itself.
document.querySelectorAll('.nav a[href$=".html"]').forEach(a => { a.addEventListener('click', e => { e.preventDefault(); toast('In the live studio this opens the ' + a.textContent + ' page.') }) });
})();
init();
