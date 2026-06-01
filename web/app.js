// ── EVO 16 Remote — Knob UI (0–50 dB, mute, phantom) ──
// Audient hardware style — large SVG knobs, electric blue fill

const API = '/api';
const RANGE = 50;            // 0–50 dB
const DEG_PER_UNIT = 300 / RANGE;   // 300° sweep (7→5 o'clock)
const START_ANGLE = 210;            // 0 dB = 7 o'clock (210° clockwise from top)

const KNOB_R = 42;           // SVG circle radius
const KNOB_CIRC = 2 * Math.PI * KNOB_R;   // ~263.9

let state = [];              // {ch, gain, mute, phantom, instrument}
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
        ${ch <= 2 ? '<button class="btn-instr" data-ch="' + ch + '">INSTR</button>' : ''}
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
      // Update instrument button (CH1-2 only)
      const instrBtn = document.querySelector(`.btn-instr[data-ch="${inp.channel}"]`);
      if (instrBtn) {
        const hasInstr = inp.instrument !== undefined ? inp.instrument : false;
        instrBtn.classList.toggle('on', hasInstr);
        instrBtn.textContent = hasInstr ? 'INSTR' : 'INSTR';
      }
    }

    // Sync local state
    state = data.inputs.map(i => ({
      ch: i.channel,
      gain: Math.round(i.gain),
      mute: i.mute,
      phantom: i.phantom,
      instrument: i.instrument !== undefined ? i.instrument : false,
    }));
  } catch (err) {
    const badge = document.getElementById('status-badge');
    badge.textContent = '● OFFLINE';
    badge.className = 'badge offline';
  }
}

// ── Init ──
buildRack();
poll();
setInterval(poll, 2000);
