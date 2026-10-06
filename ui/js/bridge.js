// Event bus + API access. Falls back to an in-memory mock when opened in a
// plain browser so the UI can be developed and screenshotted without Python.
const handlers = {};
window.echo = {
  on(name, fn) { (handlers[name] ||= []).push(fn); },
  emit(name, payload) { (handlers[name] || []).forEach(fn => fn(payload)); },
};

const mock = (() => {
  let state = 'idle', timer = null;
  const history = [
    { id: '2026-09-21_14-27-54', name: 'Reunión de seguimiento', duration_s: 181, model: 'small', preview: 'Me dudaba que tenía con los organismos colegiados…' },
    { id: '2026-09-21_15-16-55', name: '2026-09-21_15-16-55', duration_s: 12, model: 'small', preview: 'Hola…' },
  ];
  const turns = [
    { start_s: 0, speaker: 'YO', text: 'Buenos días, arrancamos con el punto de vacaciones.' },
    { start_s: 14, speaker: 'OTROS', text: 'Perfecto, yo tengo dos comentarios sobre el plan de acción.' },
    { start_s: 41, speaker: 'YO', text: 'Adelante, los anotamos.' },
  ];
  const models = ['tiny', 'base', 'small', 'medium', 'large-v3-turbo', 'large-v3'].map((n, i) => ({
    name: n, label: ['Tiny', 'Base', 'Balanced', 'Medium', 'Best', 'Large v3'][i], note: '',
    size_mb: [75, 148, 488, 1500, 1620, 3100][i], installed: n === 'small' }));
  return {
    async bootstrap() { return { state, model: 'small', models, gpu: 'NVIDIA GeForce RTX 5060 Ti', settings: { theme: 'system', vocabulary: '', hotkey: 'ctrl+shift+r', model: 'small' }, history }; },
    async toggle() {
      if (state === 'idle') {
        state = 'recording'; echo.emit('state', state);
        timer = setInterval(() => echo.emit('levels', { microphone: Math.random() * .3, system: Math.random() * .15 }), 50);
      } else if (state === 'recording') {
        clearInterval(timer); state = 'transcribing'; echo.emit('state', state);
        let p = 0; const t = setInterval(() => { p += 12; echo.emit('progress', Math.min(p, 100)); if (p >= 100) { clearInterval(t); state = 'idle'; echo.emit('state', state); echo.emit('history_changed'); } }, 300);
      }
    },
    async set_model(n) { models.forEach(m => m.installed = m.installed || m.name === n); return models; },
    async download_model(name) { let p = 0; const t = setInterval(() => { p += 20; echo.emit('model_download', { name, pct: p, done: p >= 100, error: null }); if (p >= 100) { clearInterval(t); models.find(m => m.name === name).installed = true; } }, 250); },
    async get_settings() { return {}; },
    async set_settings(p) { return p; },
    async list_devices() { return { inputs: [], loopbacks: [] }; },
    async list_history() { return history; },
    async load_transcript(id) { return { id, meta: history.find(h => h.id === id) || history[0], turns }; },
    async rename() {}, async delete() {}, async export() { return 'ok'; }, async open_folder() {},
  };
})();

export async function api() {
  if (!window.pywebview?.api) {
    await new Promise(r => {
      let n = 0;
      const t = setInterval(() => { if (window.pywebview?.api || ++n > 20) { clearInterval(t); r(); } }, 50);
    });
  }
  return window.pywebview?.api || mock;
}
