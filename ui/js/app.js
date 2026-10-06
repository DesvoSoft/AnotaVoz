import { api } from './bridge.js';
import { Waveform } from './waveform.js';

const $ = s => document.querySelector(s);
const STATE = { loading: 'Cargando modelo…', idle: 'Listo', recording: 'Grabando', transcribing: 'Transcribiendo…' };
const WEAK = ['tiny', 'base', 'small'];
let A, startedAt = null, current = null, models = [], selected = '', hasGpu = false;

const mic = new Waveform($('#waveMic'), '--yo');
const sys = new Waveform($('#waveSys'), '--otros');

const pad = n => String(n).padStart(2, '0');
const fmt = s => `${pad(Math.floor(s / 3600))}:${pad(Math.floor(s % 3600 / 60))}:${pad(s % 60)}`;
const esc = t => String(t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const speaker = s => (s === 'YO' ? 'Tú' : 'Otros');

function setState(s) {
  $('#statusText').textContent = STATE[s] || s;
  $('#dot').className = 'dot ' + s;
  const btn = $('#recBtn');
  btn.disabled = s === 'loading' || s === 'transcribing';
  btn.classList.toggle('recording', s === 'recording');
  $('#progress').hidden = s !== 'transcribing';
  if (s === 'recording') { startedAt = Date.now(); mic.start(); sys.start(); }
  else { startedAt = null; $('#timer').textContent = ''; mic.stop(); sys.stop(); }
  if (s === 'transcribing') $('#progressBar').style.width = '0%';
}

setInterval(() => {
  if (!startedAt) return;
  const s = Math.floor((Date.now() - startedAt) / 1000);
  $('#timer').textContent = `${pad(Math.floor(s / 60))}:${pad(s % 60)}`;
}, 500);

function showView(name) {
  document.querySelectorAll('.view').forEach(v => v.classList.toggle('active', v.id === 'view-' + name));
  document.querySelectorAll('.nav').forEach(n => n.classList.toggle('active', n.dataset.view === name));
  if (name === 'history') loadHistory();
  if (name === 'settings') renderModels();
}
document.querySelectorAll('.nav').forEach(n => n.onclick = () => showView(n.dataset.view));

async function loadHistory() {
  const items = await A.list_history();
  const q = $('#search').value.trim().toLowerCase();
  const shown = items.filter(i => !q || (i.name + ' ' + i.preview).toLowerCase().includes(q));
  $('#historyList').innerHTML = shown.map(i => `
    <div class="item ${i.id === current ? 'active' : ''}" data-id="${esc(i.id)}">
      <b>${esc(i.name)}</b><small>${esc(i.id.replace('_', ' '))} · ${Math.round(i.duration_s / 60) || '<1'} min</small>
      <p>${esc(i.preview || '')}</p></div>`).join('') || '<p class="empty">Sin grabaciones</p>';
  document.querySelectorAll('.item').forEach(el => el.onclick = () => openTranscript(el.dataset.id));
}

async function openTranscript(id) {
  current = id;
  const d = await A.load_transcript(id);
  if (d.error) { $('#transcript').innerHTML = `<p class="empty">${esc(d.error)}</p>`; return; }
  const q = $('#search').value.trim();
  const re = q ? new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi') : null;
  const hl = t => {
    if (!re) return esc(t);
    let out = '', last = 0;
    for (const m of t.matchAll(re)) { out += esc(t.slice(last, m.index)) + `<mark>${esc(m[0])}</mark>`; last = m.index + m[0].length; }
    return out + esc(t.slice(last));
  };
  $('#transcript').innerHTML = `
    <div class="tools">
      <button data-a="copy">Copiar</button><button data-a="md">MD</button><button data-a="srt">SRT</button>
      <button data-a="folder">Abrir carpeta</button><button data-a="rename">Renombrar</button><button data-a="delete">Borrar</button></div>` +
    d.turns.map(t => `<div class="turn ${t.speaker}"><div class="bubble"><small>${speaker(t.speaker)} · ${fmt(t.start_s)}</small>${hl(t.text)}</div></div>`).join('');
  $('#transcript').querySelectorAll('.tools button').forEach(b => b.onclick = () => toolAction(b.dataset.a, d));
  loadHistory();
}

async function toolAction(a, d) {
  if (a === 'copy') await navigator.clipboard.writeText(d.turns.map(t => `[${fmt(t.start_s)}] ${speaker(t.speaker)}: ${t.text}`).join('\n'));
  else if (a === 'folder') A.open_folder(d.id);
  else if (a === 'rename') { const n = prompt('Nombre', d.meta.name); if (n) { await A.rename(d.id, n); loadHistory(); } }
  else if (a === 'delete') {
    if (confirm('¿Borrar esta grabación?')) { await A.delete(d.id); current = null; $('#transcript').innerHTML = '<p class="empty">Elige una grabación</p>'; loadHistory(); }
  } else { const p = await A.export(d.id, a); $('#log').textContent = p.error || `Exportado: ${p}`; }
}
$('#search').oninput = () => { loadHistory(); if (current) openTranscript(current); };

function renderModels() {
  $('#modelList').innerHTML = models.map(m => `
    <div class="model ${m.name === selected ? 'sel' : ''}" data-n="${m.name}">
      <div><b>${esc(m.label)}</b> <small class="muted">${m.name} · ${m.size_mb} MB ${m.note ? '· ' + esc(m.note) : ''}</small>
      <div class="bar2" ${m.installed ? 'hidden' : ''}><i id="dl-${m.name}"></i></div></div>
      <button class="btn">${m.name === selected ? 'En uso' : m.installed ? 'Usar' : 'Descargar'}</button></div>`).join('');
  document.querySelectorAll('.model').forEach(el => el.querySelector('button').onclick = async () => {
    const n = el.dataset.n, m = models.find(x => x.name === n);
    if (m.installed) { models = await A.set_model(n); selected = n; renderModels(); checkUpgrade(); }
    else A.download_model(n);
  });
}

// Light is the default; only suggest the big model where a GPU makes it cheap to run.
function checkUpgrade() { $('#upgradeBanner').hidden = !(hasGpu && WEAK.includes(selected)); }

$('#upgradeBtn').onclick = async () => {
  const best = models.find(m => m.name === 'large-v3-turbo');
  if (best.installed) { models = await A.set_model(best.name); selected = best.name; checkUpgrade(); }
  else { A.download_model(best.name); $('#log').textContent = 'Descargando modelo…'; }
};

window.echo.on('state', setState);
window.echo.on('log', m => { $('#log').textContent = m; });
window.echo.on('levels', l => { mic.push(l.microphone); sys.push(l.system); });
window.echo.on('progress', p => { $('#progressBar').style.width = p + '%'; });
window.echo.on('history_changed', () => { if ($('#view-history').classList.contains('active')) loadHistory(); });
window.echo.on('model_download', async e => {
  const bar = $('#dl-' + e.name); if (bar) bar.style.width = e.pct + '%';
  $('#log').textContent = e.error ? `Error de descarga: ${e.error}` : e.done ? 'Modelo descargado' : `Descargando ${e.name}… ${Math.round(e.pct)}%`;
  if (e.done) {
    const m = models.find(x => x.name === e.name); if (m) m.installed = true;
    if (e.name === 'large-v3-turbo' && WEAK.includes(selected)) { models = await A.set_model(e.name); selected = e.name; checkUpgrade(); }
    renderModels();
  }
});

$('#recBtn').onclick = () => A.toggle();
$('#theme').onchange = e => { document.documentElement.dataset.theme = e.target.value; A.set_settings({ theme: e.target.value }); };
$('#vocab').onchange = e => A.set_settings({ vocabulary: e.target.value });

(async () => {
  A = await api();
  const b = await A.bootstrap();
  models = b.models; selected = b.model; hasGpu = !!b.gpu;
  $('#gpuChip').textContent = b.gpu ? `⚡ ${b.gpu}` : 'CPU · modo ligero';
  $('#vocab').value = b.settings.vocabulary || '';
  $('#theme').value = b.settings.theme || 'system';
  document.documentElement.dataset.theme = b.settings.theme || 'system';
  setState(b.state);
  checkUpgrade();
})();
