// Native clients use Bearer; the local web UI uses an HttpOnly same-origin session.
let bearer = '';
let deviceReady = false;
let testSession = false;
let deviceMissing = false;
const writes = new Map();

function showError(error) {
  const badge = document.getElementById('status-badge');
  badge.textContent = `${testSession ? 'PRUEBA · ' : ''}${deviceMissing ? 'SIN EQUIPO' : 'SIN CONEXIÓN'}`;
  badge.className = 'badge offline';
  document.getElementById('connection-info').textContent = error.message || 'No se pudo contactar al equipo.';
}

function setDeviceReady(ready) {
  deviceReady = ready;
  document.querySelectorAll('.ch-actions button, #main-volume, #store-standalone, #preset-apply, #preset-save').forEach(el => { el.disabled = !ready; });
  document.querySelectorAll('.knob-wrap').forEach(el => {
    el.setAttribute('aria-disabled', String(!ready));
    el.setAttribute('role', ready ? 'slider' : 'group');
    if (!ready) {
      el.removeAttribute('aria-valuenow');
      el.querySelector('.knob-value').textContent = '—';
    }
  });
  const main = document.getElementById('main-volume');
  if (ready) main.removeAttribute('aria-valuetext');
  else {
    main.setAttribute('aria-valuetext', 'No disponible');
    document.getElementById('main-volume-val').textContent = '—';
  }
  if (!ready) { state = []; writes.forEach(writer => { writer.pending = null; }); }
  else document.getElementById('connection-info').textContent = '';
}

async function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (bearer) headers.set('Authorization', `Bearer ${bearer}`);
  const response = await fetch(url, { ...options, headers, signal: AbortSignal.timeout(12000) });
  if (!response.ok) {
    if (response.status === 401) document.getElementById('auth-form').hidden = false;
    const payload = await response.json().catch(() => ({}));
    const error = new Error(typeof payload.detail === 'string' ? payload.detail : `No se pudo completar la solicitud (${response.status}).`);
    if ([401, 503].includes(response.status)) setDeviceReady(false);
    showError(error);
    throw error;
  }
  return response;
}

function queueWrite(key, url, payload) {
  let writer = writes.get(key);
  if (!writer) { writer = { busy: false, pending: null }; writes.set(key, writer); }
  writer.pending = payload;
  if (writer.busy) return;
  writer.busy = true;
  const send = async () => {
    const next = writer.pending;
    writer.pending = null;
    try {
      if (next && deviceReady) await apiFetch(url, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(next),
      });
    } catch (error) { showError(error); }
    if (writer.pending && deviceReady) setTimeout(send, 90);
    else writer.busy = false;
  };
  setTimeout(send, 80);
}

document.getElementById('auth-form').addEventListener('submit', async event => {
  event.preventDefault();
  bearer = document.getElementById('api-credential').value.trim();
  try {
    await apiFetch('/api/health');
    document.getElementById('api-credential').value = '';
    document.getElementById('auth-form').hidden = true;
    poll(); loadPresets();
  } catch (error) { document.getElementById('auth-error').textContent = error.message; }
});

// ── EVO 16 Remote — Knob UI (0…50 dB, mute, phantom, DI y link de par) ──
// Audient hardware style — large SVG knobs, electric blue fill

const API = '/api';
const MIN_GAIN = GainScale.min;
const MAX_GAIN = GainScale.max;
const RANGE = MAX_GAIN - MIN_GAIN;
// Canales con hardware de instrumento (DI): locales 1-2 + ADAT 9-10 y 17-18.
// Igual que Evo16Service.INSTR_CHANNELS del backend (el resto responde 400).
const DI_CHANNELS = [1, 2, 9, 10, 17, 18];
const DEG_PER_UNIT = 300 / RANGE;   // 300° sweep (7→5 o'clock)
const START_ANGLE = 210;            // 0 dB = 7 o'clock (210° clockwise from top)

const KNOB_R = 42;           // SVG circle radius
const KNOB_CIRC = 2 * Math.PI * KNOB_R;   // ~263.9

let state = [];              // {ch, gain, mute, phantom, instrument, linked, linkPair}
let knobEls = new Map();    // ch → { wrap, fill, dot, valEl }

// ── Global: update visual for a channel ──
function setVisual(ch, gain) {
  const els = knobEls.get(ch);
  if (!els) return;
  const deg = (gain - MIN_GAIN) * DEG_PER_UNIT;
  const arcLen = KNOB_CIRC * ((gain - MIN_GAIN) / RANGE) * 0.833333;
  els.fill.setAttribute('stroke-dasharray', `${arcLen.toFixed(2)} ${KNOB_CIRC.toFixed(2)}`);
  els.fill.setAttribute('stroke-dashoffset', '0');
  els.dot.setAttribute('transform', `rotate(${START_ANGLE + deg} 50 50)`);
  els.valEl.textContent = gain;
  els.wrap.setAttribute('aria-valuenow', gain);
}

// ── DOM build ──
function buildRack() {
  const rack = document.getElementById('rack');
  rack.innerHTML = '';
  const sections = [
    { label: 'ANALOG 1–8', start: 1, end: 8 },
    { label: 'ADAT 1 9–16', start: 9, end: 16 },
    { label: 'ADAT 2 17–24', start: 17, end: 24 },
  ];
  for (const sec of sections) {
    const hdr = document.createElement('div');
    hdr.className = 'section-header';
    hdr.textContent = sec.label;
    rack.appendChild(hdr);
    for (let ch = sec.start; ch <= sec.end; ch++) {
      const card = document.createElement('div');
      card.className = 'channel';
      card.id = `ch-${ch}`;
      card.innerHTML = `
      <div class="ch-label">CH ${ch}</div>
      <div class="knob-wrap" data-ch="${ch}" role="slider" tabindex="0" aria-label="Ganancia canal ${ch}" aria-valuemin="${MIN_GAIN}" aria-valuemax="${MAX_GAIN}" aria-disabled="true">
        <svg class="knob-svg" viewBox="0 0 100 100">
          <circle class="knob-bg" cx="50" cy="50" r="${KNOB_R}"/>
          <circle class="knob-fill" cx="50" cy="50" r="${KNOB_R}"
                  stroke-dasharray="0 ${KNOB_CIRC.toFixed(2)}" stroke-dashoffset="0"
                  transform="rotate(120 50 50)"/>
          <circle class="knob-dot" cx="50" cy="8" r="4.5"/>
        </svg>
        <div class="knob-value">—</div>
      </div>
      <div class="ch-actions">
        <button class="btn-48v" data-ch="${ch}">48V</button>
        ${DI_CHANNELS.includes(ch) ? '<button class="btn-instr" data-ch="' + ch + '">INSTR</button>' : ''}
        <button class="btn-link" data-ch="${ch}">LINK</button>
        <button class="btn-mute" data-ch="${ch}">MUTE</button>
      </div>
    `;
      rack.appendChild(card);
    }
  }
  bindKnobs();
  bindMutes();
  bindPhantoms();
  bindInstruments();
  bindLinks();
}

// ── Knob drag ──
function bindKnobs() {
  document.querySelectorAll('.knob-wrap').forEach(wrap => {
    const ch = +wrap.dataset.ch;
    const fill = wrap.querySelector('.knob-fill');
    const dot = wrap.querySelector('.knob-dot');
    const valEl = wrap.querySelector('.knob-value');

    knobEls.set(ch, { wrap, fill, dot, valEl });

    let dragging = false;
    let startY = 0, startGain = 0, lastCommitted = 0;

    function commit(channel, db) {
      queueWrite(`gain-${channel}`, `${API}/gain/${channel}`, { db: GainScale.toApi(Math.round(db)) });
    }

    wrap.addEventListener('keydown', e => {
      if (!deviceReady || !['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
      e.preventDefault();
      const entry = state.find(s => s.ch === ch);
      if (!entry) return;
      const direction = ['ArrowUp', 'ArrowRight'].includes(e.key) ? 1 : -1;
      const gain = e.key === 'Home' ? MIN_GAIN : e.key === 'End' ? MAX_GAIN
        : Math.max(MIN_GAIN, Math.min(MAX_GAIN, entry.gain + direction));
      entry.gain = gain; setVisual(ch, gain); commit(ch, gain);
    });

    wrap.addEventListener('pointerdown', e => {
      if (!deviceReady) return;
      dragging = true;
      startY = e.clientY;
      const entry = state.find(s => s.ch === ch);
      startGain = entry ? entry.gain : 0;
      lastCommitted = startGain;
      wrap.classList.add('dragging');
      wrap.setPointerCapture(e.pointerId);
      e.preventDefault();
    });

    wrap.addEventListener('pointermove', e => {
      if (!dragging) return;
      const dy = (startY - e.clientY) * 0.5;  // sensitivity
      let newGain = Math.round(Math.max(MIN_GAIN, Math.min(MAX_GAIN, startGain + dy)));
      setVisual(ch, newGain);
      // Real-time: commit every 1 dB step during drag
      if (newGain !== lastCommitted) {
        commit(ch, newGain);
        lastCommitted = newGain;
        const entry = state.find(s => s.ch === ch);
        if (entry) entry.gain = newGain;
      }
    });

    wrap.addEventListener('pointerup', e => {
      if (!dragging) return;
      dragging = false;
      wrap.classList.remove('dragging');
    });

    wrap.addEventListener('pointerleave', () => {
      if (dragging) {
        dragging = false;
        wrap.classList.remove('dragging');
      }
    });

    // Prevent touch scrolling while interacting with knob
    wrap.addEventListener('touchstart', e => e.preventDefault());
  });
}

// ── Mute buttons ──
function bindMutes() {
  document.querySelectorAll('.btn-mute').forEach(btn => {
    btn.addEventListener('click', async () => {
      const ch = +btn.dataset.ch;
      const entry = state.find(s => s.ch === ch);
      if (!entry) return;
      const newMute = !entry.mute;
      try {
        const r = await apiFetch(`${API}/mute/${ch}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ muted: newMute }),
        });
        if (r.ok) {
          entry.mute = newMute;
          btn.classList.toggle('muted', newMute);
          /* NO text change — toggle visual only */
        }
      } catch (err) { showError(err); }
    });
  });
}

// ── Phantom buttons ──
function bindPhantoms() {
  document.querySelectorAll('.btn-48v').forEach(btn => {
    btn.addEventListener('click', async () => {
      const ch = +btn.dataset.ch;
      const entry = state.find(s => s.ch === ch);
      if (!entry) return;
      const newPhantom = !entry.phantom;
      try {
        const r = await apiFetch(`${API}/phantom/${ch}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ on: newPhantom }),
        });
        if (r.ok) {
          entry.phantom = newPhantom;
          btn.classList.toggle('on', newPhantom);
          btn.textContent = newPhantom ? '48V' : '48V';
        }
      } catch (err) { showError(err); }
    });
  });
}

// ── Instrument buttons (CH1-2 only) ──
function bindInstruments() {
  document.querySelectorAll('.btn-instr').forEach(btn => {
    btn.addEventListener('click', async () => {
      const ch = +btn.dataset.ch;
      const entry = state.find(s => s.ch === ch);
      if (!entry) return;
      const newInstr = !entry.instrument;
      try {
        const r = await apiFetch(`${API}/instrument/${ch}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ on: newInstr }),
        });
        if (r.ok) {
          entry.instrument = newInstr;
          btn.classList.toggle('on', newInstr);
          btn.textContent = newInstr ? 'INSTR' : 'INSTR';
        }
      } catch (err) { showError(err); }
    });
  });
}

// ── Link buttons (pares: 1-2, 3-4, 5-6, …) ──
// El link es un estado POR PAR (EU58 CS=3): al tocarlo se actualizan los botones de los DOS
// canales del par. Con el par linkeado el firmware espeja el preamp (gain, DI), así que el
// cliente no tiene que duplicar escrituras.
function pairOf(ch) {
  const a = ch % 2 === 1 ? ch : ch - 1;
  return [a, a + 1];
}

function bindLinks() {
  document.querySelectorAll('.btn-link').forEach(btn => {
    btn.addEventListener('click', async () => {
      const ch = +btn.dataset.ch;
      const entry = state.find(s => s.ch === ch);
      if (!entry) return;
      const newLinked = !entry.linked;
      try {
        const r = await apiFetch(`${API}/link/${ch}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ on: newLinked }),
        });
        if (r.ok) {
          const pair = entry.linkPair || pairOf(ch);
          for (const c of pair) {
            const e = state.find(s => s.ch === c);
            if (e) { e.linked = newLinked; e.linkPair = pair; }
            const b = document.querySelector(`.btn-link[data-ch="${c}"]`);
            if (b) b.classList.toggle('on', newLinked);
          }
        }
      } catch (err) { showError(err); }
    });
  });
}

// ── Poll device status ──
let polling = false;
async function poll() {
  if (polling) return;
  polling = true;
  try {
    const health = await (await apiFetch(`${API}/health`)).json();
    testSession = health.testMode === true;
    deviceMissing = !health.ok;
    document.getElementById('test-banner').hidden = !testSession;
    if (!health.ok) throw new Error(health.stateDetail || 'EVO 16 no disponible');
    const r = await apiFetch(`${API}/status`);
    const data = await r.json();
    if (data.status !== 'ok' || data.sampleAgeSeconds > 6) throw new Error('El estado del equipo no está actualizado');
    setDeviceReady(true);
    document.getElementById('device-name').textContent = data.device;

    const badge = document.getElementById('status-badge');
    badge.textContent = testSession ? 'PRUEBA · SIMULADO' : '● LIVE';
    badge.className = 'badge live';

    // Update each channel from server state
    for (const inp of data.inputs) {
      const els = knobEls.get(inp.channel);
      if (!els) continue;

      // Skip channels being dragged
      if (els.wrap.classList.contains('dragging')) continue;

      const gain = GainScale.fromApi(inp.gain);
      setVisual(inp.channel, gain);

      // Update mute button
      const muteBtn = document.querySelector(`.btn-mute[data-ch="${inp.channel}"]`);
      if (muteBtn) {
        muteBtn.classList.toggle('muted', inp.mute);
        /* NO text change */
      }
      // Update phantom button
      const phantomBtn = document.querySelector(`.btn-48v[data-ch="${inp.channel}"]`);
      if (phantomBtn) {
        phantomBtn.classList.toggle('on', inp.phantom);
        phantomBtn.textContent = inp.phantom ? '48V' : '48V';
      }
      // Update instrument button (sólo canales con hardware de DI)
      const instrBtn = document.querySelector(`.btn-instr[data-ch="${inp.channel}"]`);
      if (instrBtn) {
        const hasInstr = inp.instrument === true;
        instrBtn.classList.toggle('on', hasInstr);
        instrBtn.textContent = hasInstr ? 'INSTR' : 'INSTR';
      }
      // Update link button (estado del par al que pertenece el canal)
      const linkBtn = document.querySelector(`.btn-link[data-ch="${inp.channel}"]`);
      if (linkBtn) linkBtn.classList.toggle('on', inp.linked === true);
    }

    // Volumen del MAIN OUT (si el server lo reporta). No pisar mientras se arrastra el slider.
    if (typeof data.mainVolume === 'number') {
      const el = document.getElementById('main-volume');
      const val = document.getElementById('main-volume-val');
      if (el && document.activeElement !== el) {
        const v = dbToVol(data.mainVolume);
        el.value = v;
        if (val) val.textContent = `${v} / 100  (${data.mainVolume.toFixed(1)} dB)`;
      }
    }

    // Sync local state
    state = data.inputs.map(i => ({
      ch: i.channel,
      gain: GainScale.fromApi(i.gain),
      mute: i.mute,
      phantom: i.phantom,
      instrument: i.instrument === true,
      linked: i.linked === true,
      linkPair: i.linkPair || pairOf(i.channel),
    }));
  } catch (err) {
    showError(err);
    setDeviceReady(false);
  } finally { polling = false; }
}

// ── Perfiles de preamps (un archivo JSON por perfil, guardado en el server) ──
// Guardar = captura el estado ACTUAL del equipo. Aplicar = lo reinyecta (gain, 48V, DI, link de
// par y mute de los 24 canales). Sirve para mandar estados guardados de preamp por escena.
let presets = [];

function presetInfo(txt, cls) {
  const el = document.getElementById('preset-info');
  el.textContent = txt;
  el.className = 'preset-info' + (cls ? ' ' + cls : '');
}

function selectedPreset() {
  return document.getElementById('preset-select').value;
}

async function loadPresets() {
  try {
    const d = await (await apiFetch(`${API}/presets`)).json();
    presets = d.presets || [];
    const sel = document.getElementById('preset-select');
    const keep = sel.value;
    sel.replaceChildren();
    if (!presets.length) sel.add(new Option('— sin perfiles —', ''));
    for (const preset of presets) sel.add(new Option(`${preset.name}${preset.error ? ' (ilegible)' : ''}`, preset.name));
    if (keep && presets.some(p => p.name === keep)) sel.value = keep;
    if (d.dir) sel.title = `Los archivos viven en ${d.dir}`;
  } catch (err) { /* sin server: el badge ya avisa */ }
}

function bindPresets() {
  document.getElementById('preset-apply').addEventListener('click', async () => {
    const name = selectedPreset();
    if (!name) return presetInfo('Elegí un perfil primero.', 'bad');
    presetInfo(`Aplicando «${name}»…`);
    try {
      const r = await apiFetch(`${API}/presets/${encodeURIComponent(name)}/apply`, { method: 'POST' });
      const d = await r.json();
      if (!r.ok) return presetInfo(d.detail || 'No se pudo aplicar.', 'bad');
      const errs = (d.errors || []).length;
      presetInfo(errs ? `«${name}» aplicado con ${errs} aviso(s).` : `«${name}» aplicado (${d.applied} operaciones).`,
                  errs ? 'warn' : 'ok');
      poll();
    } catch (err) { presetInfo('Error de red al aplicar.', 'bad'); }
  });

  document.getElementById('preset-save').addEventListener('click', async () => {
    const sugerido = selectedPreset() || `Escena ${new Date().toLocaleDateString()}`;
    const name = (prompt('Nombre del perfil (se guarda el estado ACTUAL del equipo):', sugerido) || '').trim();
    if (!name) return;
    presetInfo(`Guardando «${name}»…`);
    try {
      const r = await apiFetch(`${API}/presets/${encodeURIComponent(name)}`, { method: 'POST' });
      const d = await r.json();
      if (!r.ok) return presetInfo(d.detail || 'No se pudo guardar.', 'bad');
      presetInfo(`Guardado «${d.name}» (${d.channels} canales).`, 'ok');
      await loadPresets();
      document.getElementById('preset-select').value = d.name;
    } catch (err) { presetInfo('Error de red al guardar.', 'bad'); }
  });

  document.getElementById('preset-export').addEventListener('click', async () => {
    const name = selectedPreset();
    if (!name) return presetInfo('Elegí un perfil primero.', 'bad');
    try {
      const response = await apiFetch(`${API}/presets/${encodeURIComponent(name)}/export`, { method: 'POST' });
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url; link.download = `${name}.json`; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      presetInfo(`Exportado «${name}».`, 'ok');
    } catch (err) { presetInfo(err.message, 'bad'); }
  });

  const fileInput = document.getElementById('preset-file');
  document.getElementById('preset-import').addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', async () => {
    const file = fileInput.files[0];
    if (!file) return;
    try {
      if (file.size > 250 * 1024) throw new Error('El perfil supera los 250 KB.');
      const preset = JSON.parse(await file.text());
      const r = await apiFetch(`${API}/presets/import`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ preset }),
      });
      const data = await r.json();
      await loadPresets();
      document.getElementById('preset-select').value = data.name;
      presetInfo(`Importado «${data.name}» (${data.channels} canales).`, 'ok');
    } catch (err) { presetInfo(err.message, 'bad'); }
    finally { fileInput.value = ''; }
  });

  document.getElementById('preset-delete').addEventListener('click', async () => {
    const name = selectedPreset();
    if (!name) return presetInfo('Elegí un perfil primero.', 'bad');
    if (!confirm(`¿Borrar el perfil «${name}»? Se elimina el archivo del disco.`)) return;
    try {
      const r = await apiFetch(`${API}/presets/${encodeURIComponent(name)}`, { method: 'DELETE' });
      if (!r.ok) return presetInfo('No se pudo borrar.', 'bad');
      document.getElementById('preset-select').value = '';
      presetInfo(`Borrado «${name}».`, 'ok');
      await loadPresets();
    } catch (err) { presetInfo('Error de red al borrar.', 'bad'); }
  });
}

// ── Volumen del MAIN OUT (unidad 0x36 CS=18) ──
// Registro descubierto desensamblando la app oficial (UacXUAudientMonitorController::setMainVolume):
// 2 bytes Q8.8 con signo. La app NO expone este control; acá lo mandamos por USB.
// La pantalla del equipo NO es lineal en dB — es logarítmica (comprobado contra el equipo, 16-oct-2026):
//     pantalla = 100 × 10^(dB / 96)        dB = 96 × log10(pantalla / 100)
//   · −96 dB  → 10 en pantalla     (con la recta vieja, el slider 0 mandaba −96 y la pantalla decía 10 ✗)
//   · −61.4 dB → 22                (el slider 36 mandaba −61.4 por la recta y la pantalla decía 22 ✗)
//   · 0 dB    → 100
// Antes se usaba la recta `dB = (v − 100) × 0.96`: por eso el número del slider se corría del de la
// pantalla. Con esta ley, el número del slider y el de la pantalla son EL MISMO.
// El valor se manda MIENTRAS se desliza (throttle ~90 ms, siempre el último valor) para que el
// equipo avance en conjunto con el slider, como si fuera la perilla.
const VOL_PISO_DB = -128;          // piso real del registro (Q8.8 con signo: −32768 / 256)
const volToDb = (v) => (v <= 0 ? VOL_PISO_DB : Math.max(VOL_PISO_DB, 96 * Math.log10(v / 100)));
const dbToVol = (db) => (db <= VOL_PISO_DB + 8 ? 0
  : Math.min(100, Math.floor(100 * Math.pow(10, db / 96) + 1e-9)));   // +1e-9: redondeo del log/pow
                                                                      // floor: la pantalla trunca igual

function bindMainVolume() {
  const el = document.getElementById('main-volume');
  const val = document.getElementById('main-volume-val');
  if (!el) return;
  function pintar(v) {
    if (val) val.textContent = `${v} / 100  (${volToDb(v).toFixed(1)} dB)`;
  }
  function enviar() {
    if (!deviceReady) return;
    pintar(+el.value);
    queueWrite('main', `${API}/main-volume`, { db: volToDb(+el.value) });
  }
  el.addEventListener('input', enviar);
  el.addEventListener('change', enviar);
  if (deviceReady) pintar(+el.value);
}

// ── Guardar el estado en la memoria INTERNA de la interfaz ("Store Standalone State") ──
// Para que el equipo trabaje solo, sin computadora. Trigger 0x36 CS=24 (ver service.py).
// Es de UNA SOLA VÍA: pisa lo que haya guardado; se verifica ciclando la energía del equipo.
function bindStandalone() {
  const btn = document.getElementById('store-standalone');
  if (!btn) return;
  btn.addEventListener('click', async () => {
    const ok = confirm('¿Guardar el estado ACTUAL en la memoria de la interfaz?\n\n' +
      'PISA lo que haya guardado y no se puede deshacer desde acá.\n\n' +
      'Es el estado que el equipo usará cuando trabaje solo, sin computadora.');
    if (!ok) return;
    const info = document.getElementById('preset-info');
    btn.disabled = true;
    try {
      const r = await apiFetch(`${API}/store-standalone`, { method: 'POST' });
      const d = await r.json();
      if (info) {
        info.textContent = r.ok
          ? 'Guardado en la interfaz ✓ — verificalo ciclando la energía del equipo'
          : (d.detail || 'No se pudo guardar.');
        info.className = 'preset-info ' + (r.ok ? 'ok' : 'bad');
      }
    } catch (err) {
      if (info) { info.textContent = 'Error de red al guardar en la interfaz.'; info.className = 'preset-info bad'; }
    } finally { btn.disabled = !deviceReady; }
  });
}

// ── Init ──
buildRack();
setDeviceReady(false);
poll();
setInterval(() => { if (!document.hidden) poll(); }, 2000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
loadPresets();
bindPresets();
bindMainVolume();
bindStandalone();
