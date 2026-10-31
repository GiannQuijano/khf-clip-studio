// Demo mode: stands in for the server so the real studio UI runs with a sample video.
(function () {
const DURATION = 66;
const SEGS = [
  [0.8, "Hey everyone, quick update from the field."],
  [3.6, "We're standing on a lakebed right now, and it only fills up during the monsoon."],
  [9.4, "The rest of the year, families here walk over an hour just to collect water."],
  [15.2, "Most of that walking is done by kids, before school, in this heat."],
  [20.6, "So today is a really big day for this village."],
  [24.2, "We just finished drilling a new borewell, and the water is clean."],
  [29.8, "It has three taps, and it's going to serve around a thousand people."],
  [35.4, "When the first bucket filled up, the whole street started cheering."],
  [40.6, "One grandmother told me she has waited her entire life for this."],
  [46.0, "None of this happens without you."],
  [48.8, "Every dollar you give goes straight into projects like this one."],
  [54.0, "If you want to be part of the next well, the link is in our bio."],
  [59.6, "Thank you. Truly. From all of us out here."],
];
const segments = SEGS.map(([s, text], i) => {
  const next = i + 1 < SEGS.length ? SEGS[i + 1][0] : DURATION - 2;
  const end = Math.min(s + text.split(' ').length * 0.36 + 0.3, next - 0.2);
  return {start: s, end: Math.round(end * 100) / 100, text};
});
const words = [];
segments.forEach(seg => {
  const ws = seg.text.split(' '), step = (seg.end - seg.start) / ws.length;
  ws.forEach((w, i) => words.push({start: seg.start + i * step, end: seg.start + (i + 1) * step - 0.04, word: ' ' + w}));
});
const CLIPS = [
  {id: 'c1', score: 93, title: 'The day the water came', start: 20.6, end: 45.4,
   hook: 'So today is a really big day for this village.',
   on_screen_title: 'A new borewell for 1,000 people',
   why_it_works: 'A complete story in 25 seconds: the big news, the numbers (three taps, a thousand people), and an emotional payoff with the cheering street and the grandmother.',
   context_note: '',
   caption: 'Three taps. A thousand people. A lifetime of waiting, over. 💧 Thank you for making this possible.',
   hashtags: ['cleanwater', 'kindhuman', 'borewell', 'givingback', 'waterislife'],
   youtube_title: '1,000 people just got clean water', best_platforms: ['Reels', 'TikTok', 'Shorts'], id2: 1},
  {id: 'c2', score: 86, title: 'Why kids walk for water', start: 3.6, end: 20.3,
   hook: "We're standing on a lakebed right now, and it only fills up during the monsoon.",
   on_screen_title: 'This lake is dry most of the year',
   why_it_works: 'Strong visual hook (standing in a dry lakebed) and a clear problem that makes the next clip land. Good as part 1 of a two-part post.',
   context_note: "The clip doesn't say where this is. Add the village or region in the caption if you can share it.",
   caption: 'This lake only fills during the monsoon. The rest of the year, kids walk over an hour for water before school. Here’s what changed this week 👇',
   hashtags: ['cleanwater', 'watercrisis', 'kindhumanfoundation', 'nonprofit'],
   youtube_title: 'They walk an hour for water every day', best_platforms: ['Reels', 'TikTok', 'Facebook']},
  {id: 'c3', score: 79, title: 'None of this happens without you', start: 40.6, end: 63.4,
   hook: 'One grandmother told me she has waited her entire life for this.',
   on_screen_title: 'A message for our donors',
   why_it_works: 'A heartfelt thank-you with a clear call to action. Works well pinned on Instagram or as a donor update on Facebook and LinkedIn.',
   context_note: 'Opens on a quote from someone who is not on camera. The on-screen title explains who the message is for.',
   caption: 'Every dollar you give goes straight into projects like this one. Want to be part of the next well? Link in bio. 💙',
   hashtags: ['kindhuman', 'donate', 'cleanwater', 'thankyou'],
   youtube_title: 'Your donation built this well', best_platforms: ['Instagram', 'Facebook', 'LinkedIn']},
];
const SUMMARY = 'A field update from a dry lakebed: families, mostly kids, walk over an hour for water, and a new three-tap borewell now serves about a thousand people. It ends with a thank-you to donors and a clear call to action.';

const projects = {};
function newProject(id, name, created) {
  projects[id] = {id, name, source: 'source.mp4', created, startedAt: Date.now(), duration: DURATION, width: 720, height: 1280,
    has_audio: true, language: 'en', segments, suggestions: CLIPS.map(c => ({...c})), renders: [], summary: SUMMARY,
    options: {instructions: ''}, ai_used: true, simulate: false};
}
newProject('sample', 'sample-field-update.mp4', Date.now() / 1000);
let settings = {brand_context: 'Kind Human Foundation funds practical, lasting clean-water solutions, such as wells and borewells, in communities where safe water is hardest to reach. Tagline: Your donations. Our mission. Their joy. Tone: warm, hopeful, genuine, grateful. Usual call to action: donate or learn more at kindhumanfoundation.com.', min_len: 15, max_len: 60, count: 5};

function view(p) {
  const out = {...p};
  if (p.simulate) {
    const e = (Date.now() - p.startedAt) / 1000;
    const stages = [[1.5, 'probing'], [7, 'transcribing'], [10, 'finding clips']];
    const st = stages.find(([t]) => e < t);
    if (st) {
      out.status = st[1]; out.progress = Math.min(0.97, e / 10); out.suggestions = []; out.summary = '';
      if (st[1] !== 'transcribing' || e < 2) out.segments = [];
      if (st[1] === 'probing') { out.language = null }
    } else { p.simulate = false }
  }
  if (!p.simulate) { out.status = p.status || 'ready'; out.progress = 1 }
  if (p.status === 'finding clips' && Date.now() < p.busyUntil) { out.status = 'finding clips'; out.progress = 0.9 }
  else if (p.status === 'finding clips') { p.status = 'ready'; out.status = 'ready' }
  out.renders = p.renders.map(r => ({...r, status: Date.now() < r.doneAt ? 'rendering' : 'done'}));
  out.error = null;
  return out;
}
const json = (data, status = 200) => Promise.resolve(new Response(JSON.stringify(data), {status, headers: {'Content-Type': 'application/json'}}));
const realFetch = window.fetch.bind(window);
window.fetch = function (url, opts = {}) {
  const u = new URL(url, location.href); const path = u.pathname.replace(/^.*?(\/api\/)/, '/api/'); const m = (opts.method || 'GET').toUpperCase();
  if (!path.startsWith('/api/')) return realFetch(url, opts);
  let r;
  if (path === '/api/config') return json({ai: true, model: 'claude-opus-5-5', aspects: ['9:16', '1:1', '4:5', '16:9'], caption_styles: ['kind', 'bold', 'clean']});
  if (path === '/api/settings') { if (m === 'PUT') settings = JSON.parse(opts.body); return json(settings) }
  if (path === '/api/projects' && m === 'GET') return json(Object.values(projects).sort((a, b) => b.created - a.created).map(p => { const v = view(p); return {id: p.id, name: p.name, status: v.status, progress: v.progress, duration: p.duration, created: p.created, clips: v.suggestions.length} }));
  if ((r = path.match(/^\/api\/projects\/(\w+)$/))) {
    const p = projects[r[1]]; if (!p) return json({detail: 'Project not found'}, 404);
    if (m === 'DELETE') { delete projects[r[1]]; return json({ok: true}) }
    return json(view(p));
  }
  if ((r = path.match(/^\/api\/projects\/(\w+)\/suggest$/))) {
    const p = projects[r[1]]; const body = JSON.parse(opts.body || '{}');
    p.options = body; p.status = 'finding clips'; p.busyUntil = Date.now() + 3500;
    setTimeout(() => { p.suggestions = [...CLIPS].sort(() => Math.random() - 0.5).map(c => ({...c})); window.__demoToast && window.__demoToast('Demo: the live studio re-reads the transcript with your instructions.') }, 3500);
    return json({ok: true});
  }
  if ((r = path.match(/^\/api\/projects\/(\w+)\/renders$/)) && m === 'POST') {
    const p = projects[r[1]]; const b = JSON.parse(opts.body);
    const rr = {...b, id: 'r' + Math.random().toString(36).slice(2, 9), created: Date.now() / 1000, doneAt: Date.now() + 3000};
    p.renders.unshift(rr); return json(rr);
  }
  if ((r = path.match(/^\/api\/projects\/(\w+)\/renders\/(\w+)$/)) && m === 'DELETE') {
    const p = projects[r[1]]; p.renders = p.renders.filter(x => x.id !== r[2]); return json({ok: true});
  }
  if ((r = path.match(/^\/api\/projects\/(\w+)\/retry$/))) return json({ok: true});
  return json({detail: 'Not available in the demo'}, 404);
};

// Uploads: simulate processing a copy of the sample video.
window.XMLHttpRequest = class {
  constructor() { this.upload = {}; this.status = 0; this.responseText = '' }
  open() {}
  send() {
    window.__demoToast && window.__demoToast('Demo: your file stays on your computer. Processing the sample video instead.');
    let pct = 0;
    const iv = setInterval(() => {
      pct += 0.2; this.upload.onprogress && this.upload.onprogress({lengthComputable: true, loaded: pct, total: 1});
      if (pct >= 1) {
        clearInterval(iv);
        const id = 'up' + Math.random().toString(36).slice(2, 8);
        newProject(id, 'sample-field-update (copy).mp4', Date.now() / 1000); projects[id].simulate = true; projects[id].startedAt = Date.now();
        this.status = 200; this.responseText = JSON.stringify(view(projects[id])); this.onload && this.onload();
      }
    }, 150);
  }
};

// Links that would download files from the server.
document.addEventListener('click', e => {
  const a = e.target.closest && e.target.closest('a[href*="/api/"], a[href^="api/"]');
  if (a) { e.preventDefault(); window.__demoToast && window.__demoToast('Demo: in the live studio this downloads the file.') }
}, true);

if (!location.hash) { try { history.replaceState(null, '', '#sample') } catch { location.hash = 'sample' } }
window.__demo = {DURATION, words, segments, projects};
})();
