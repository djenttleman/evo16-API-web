// ── EVO 16 Remote — Knob UI (0–50 dB, mute, phantom, DI y link de par) ──
// Audient hardware style — large SVG knobs, electric blue fill

const API = '/api';
const RANGE = 50;            // 0–50 dB
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
  const deg = gain * DEG_PER_UNIT;
  const arcLen = KNOB_CIRC * (gain / RANGE) * 0.833333;
  els.fill.setAttribute('stroke-dasharray', `${arcLen.toFixed(2)} ${KNOB_CIRC.toFixed(2)}`);
  els.fill.setAttribute('stroke-dashoffset', '0');
  els.dot.setAttribute('transform', `rotate(${START_ANGLE + deg} 50 50)`);
  els.valEl.textContent = gain;
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
      <div class="knob-wrap" data-ch="${ch}">
        <svg class="knob-svg" viewBox="0 0 100 100">
          <circle class="knob-bg" cx="50" cy="50" r="${KNOB_R}"/>
          <circle class="knob-fill" cx="50" cy="50" r="${KNOB_R}"
                  stroke-dasharray="0 ${KNOB_CIRC.toFixed(2)}" stroke-dashoffset="0"
                  transform="rotate(120 50 50)"/>
          <circle class="knob-dot" cx="50" cy="8" r="4.5"/>
        </svg>
        <div class="knob-value">0</div>
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
      fetch(`${API}/gain/${channel}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ db: Math.round(db) }),
      }).catch(() => {});
    }

    wrap.addEventListener('pointerdown', e => {
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
      let newGain = Math.round(Math.max(0, Math.min(RANGE, startGain + dy)));
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
        const r = await fetch(`${API}/mute/${ch}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ muted: newMute }),
        });
        if (r.ok) {
          entry.mute = newMute;
          btn.classList.toggle('muted', newMute);
          /* NO text change — toggle visual only */
        }
      } catch (err) { /* ignore network errors */ }
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
        const r = await fetch(`${API}/phantom/${ch}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ on: newPhantom }),
        });
        if (r.ok) {
          entry.phantom = newPhantom;
          btn.classList.toggle('on', newPhantom);
          btn.textContent = newPhantom ? '48V' : '48V';
        }
      } catch (err) { /* ignore */ }
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
        const r = await fetch(`${API}/instrument/${ch}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ on: newInstr }),
        });
        if (r.ok) {
          entry.instrument = newInstr;
          btn.classList.toggle('on', newInstr);
          btn.textContent = newInstr ? 'INSTR' : 'INSTR';
        }
      } catch (err) { /* ignore */ }
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
        const r = await fetch(`${API}/link/${ch}`, {
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
      } catch (err) { /* ignore */ }
    });
  });
}

// ── Poll device status ──
async function poll() {
  try {
    const r = await fetch(`${API}/status`);
    const data = await r.json();
    document.getElementById('device-name').textContent = data.device;

    const badge = document.getElementById('status-badge');
    badge.textContent = '● LIVE';
    badge.className = 'badge live';

    // Update each channel from server state
    for (const inp of data.inputs) {
      const els = knobEls.get(inp.channel);
      if (!els) continue;

      // Skip channels being dragged
      if (els.wrap.classList.contains('dragging')) continue;

      const gain = Math.round(inp.gain);
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
      gain: Math.round(i.gain),
      mute: i.mute,
      phantom: i.phantom,
      instrument: i.instrument === true,
      linked: i.linked === true,
      linkPair: i.linkPair || pairOf(i.channel),
    }));
  } catch (err) {
    const badge = document.getElementById('status-badge');
    badge.textContent = '● OFFLINE';
    badge.className = 'badge offline';
  }
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
    const d = await (await fetch(`${API}/presets`)).json();
    presets = d.presets || [];
    const sel = document.getElementById('preset-select');
    const keep = sel.value;
    sel.innerHTML = presets.length
      ? presets.map(p => `<option value="${p.name}">${p.name}${p.error ? ' (ilegible)' : ''}</option>`).join('')
      : '<option value="">— sin perfiles —</option>';
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
      const r = await fetch(`${API}/presets/${encodeURIComponent(name)}/apply`, { method: 'POST' });
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
      const r = await fetch(`${API}/presets/${encodeURIComponent(name)}`, { method: 'POST' });
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
    const sugerido = `~/Documents/${name}.json`;
    const path = (prompt(`¿Dónde guardo «${name}»? (archivo .json)`, sugerido) || '').trim();
    if (!path) return;
    try {
      const r = await fetch(`${API}/presets/${encodeURIComponent(name)}/export`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      });
      const d = await r.json();
      if (!r.ok) return presetInfo(d.detail || 'No se pudo exportar.', 'bad');
      presetInfo(`Exportado a ${d.file} (${d.bytes} bytes).`, 'ok');
    } catch (err) { presetInfo('Error de red al exportar.', 'bad'); }
  });

  document.getElementById('preset-import').addEventListener('click', async () => {
    const path = (prompt('Ruta del archivo .json a importar al banco local:', '~/Documents/') || '').trim();
    if (!path) return;
    const name = (prompt('¿Con qué nombre entra al banco? (vacío = el que trae el archivo)', '') || '').trim();
    try {
      const r = await fetch(`${API}/presets/import`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(name ? { path, name } : { path }),
      });
      const d = await r.json();
      if (!r.ok) return presetInfo(d.detail || 'No se pudo importar.', 'bad');
      await loadPresets();
      document.getElementById('preset-select').value = d.name;
      presetInfo(`Importado «${d.name}» (${d.channels} canales).`, 'ok');
    } catch (err) { presetInfo('Error de red al importar.', 'bad'); }
  });

  document.getElementById('preset-delete').addEventListener('click', async () => {
    const name = selectedPreset();
    if (!name) return presetInfo('Elegí un perfil primero.', 'bad');
    if (!confirm(`¿Borrar el perfil «${name}»? Se elimina el archivo del disco.`)) return;
    try {
      const r = await fetch(`${API}/presets/${encodeURIComponent(name)}`, { method: 'DELETE' });
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
// Escala de la pantalla del equipo (confirmada por David): 0 = −96 dB y 100 = 0 dB → lineal:
//     dB = (v − 100) × 0.96        v = dB / 0.96 + 100
// El valor se manda MIENTRAS se desliza (throttle ~90 ms, siempre el último valor) para que el
// equipo avance en conjunto con el slider, como si fuera la perilla.
const VOL_MIN_DB = -96, VOL_MAX_DB = 0;
const volToDb = (v) => VOL_MIN_DB + (v / 100) * (VOL_MAX_DB - VOL_MIN_DB);
const dbToVol = (db) => Math.round(((db - VOL_MIN_DB) / (VOL_MAX_DB - VOL_MIN_DB)) * 100);

function bindMainVolume() {
  const el = document.getElementById('main-volume');
  const val = document.getElementById('main-volume-val');
  if (!el) return;
  let timer = null, pendiente = null;

  function pintar(v) {
    if (val) val.textContent = `${v} / 100  (${volToDb(v).toFixed(1)} dB)`;
  }
  async function enviar(db) {
    try {
      const r = await fetch(`${API}/main-volume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ db }),
      });
      const d = await r.json();
      if (r.ok && typeof d.mainVolume === 'number' && val) val.textContent = `${el.value} / 100  (${d.mainVolume.toFixed(1)} dB)`;
    } catch (err) { /* ignore */ }
  }
  function encolar(db) {
    pendiente = db;
    if (timer) return;
    timer = setTimeout(() => { timer = null; const db = pendiente; pendiente = null; enviar(db); }, 90);
  }

  el.addEventListener('input', () => { pintar(+el.value); encolar(volToDb(+el.value)); });
  el.addEventListener('change', () => {           // asegura el valor final al soltar
    if (timer) { clearTimeout(timer); timer = null; }
    enviar(volToDb(+el.value));
  });
  pintar(+el.value);
}

// ── Init ──
buildRack();
poll();
setInterval(poll, 2000);
loadPresets();
bindPresets();
bindMainVolume();
