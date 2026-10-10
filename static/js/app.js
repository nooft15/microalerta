/* MicroAlerta — SPA móvil (vanilla JS, sin build).
   Vistas: #/home #/report #/map #/protocol #/selfcare #/settings #/admin #/profile
   =============================================================== */
'use strict';

const $ = (s, el) => (el || document).querySelector(s);
const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));

const state = {
  user: null,
  stains: [],
  locations: [],
  community: null,
  places: [],
  settings: { temp: 'C', wind: 'kmh', conc: 'pml' },
  windMode: 'streams',
  wx: { data: null, ts: null },     // clima actual (caché con marca de tiempo)
  reportWx: { data: null, ts: null, busy: false, key: null },  // clima del formulario de reporte
  timers: [],                       // intervalos de la vista activa
  leaflet: null,                    // {map, stopWind}
  windAnim: true,
};

/* Lugares climáticos del usuario (Copiapó es el punto base fijo) */
const HOME_PLACE = { id: 'home', name: 'Copiapó', lat: -27.37, lon: -70.33, home: true };
function currentPlaces() {
  return [HOME_PLACE].concat(Array.isArray(state.places) ? state.places : []);
}
function loadPlaces() {
  try {
    const raw = localStorage.getItem('microalerta_places');
    const arr = raw ? JSON.parse(raw) : [];
    state.places = Array.isArray(arr) ? arr.filter(p => p && p.name && isFinite(p.lat)) : [];
  } catch (e) { state.places = []; }
}
function savePlaces() {
  try { localStorage.setItem('microalerta_places', JSON.stringify(state.places)); } catch (e) {}
}

/* ── Unidades y preferencias ───────────────────────────────── */
function loadSettings() {
  try {
    const raw = localStorage.getItem('microalerta_units');
    if (raw) state.settings = Object.assign(state.settings, JSON.parse(raw));
  } catch (e) { /* valores por defecto */ }
}
function saveSettings() {
  try { localStorage.setItem('microalerta_units', JSON.stringify(state.settings)); } catch (e) {}
}

function fmtTemp(celsius) {
  const u = state.settings.temp;
  const v = u === 'F' ? celsius * 9 / 5 + 32 : celsius;
  return (Math.abs(v) < 10 ? v.toFixed(1) : Math.round(v)) + ' ' + (u === 'F' ? '°F' : '°C');
}
function fmtWind(kmh) {
  const u = state.settings.wind;
  const v = u === 'ms' ? kmh / 3.6 : u === 'mph' ? kmh / 1.609344 : u === 'kn' ? kmh / 1.852 : kmh;
  const lbl = { kmh: 'km/h', ms: 'm/s', mph: 'mph', kn: 'kt' }[u] || 'km/h';
  return (v < 10 ? v.toFixed(1) : Math.round(v)) + ' ' + lbl;
}
function fmtConc(pml) {
  return state.settings.conc === 'pl'
    ? Math.round(pml * 1000) + ' part./L'
    : (+pml).toFixed(3) + ' part./mL';
}
function fmtDepo(pcm2) { return (+pcm2).toFixed(2) + ' p/cm²'; }
function fmtNum(n) { return Number(n || 0).toLocaleString('es-CL'); }

/* Fecha + hora local legible para mostrar junto a los reportes */
function fmtDT(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d)) return escapeHtml(String(iso));
  const p = (n) => String(n).padStart(2, '0');
  return p(d.getDate()) + '/' + p(d.getMonth() + 1) + '/' + d.getFullYear() +
         ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
}

/**
 * MicroAlerta · formulario de muestreo
 *
 * Cada bloque del formulario tiene su propia explicación colapsable
 * (▶/▼) para saber qué se está registrando y por qué.
 *
 * Pasos y qué contienen:
 *  1) Ubicación y cronología — punto de muestreo, fecha de exposición,
 *     hora aproximada de observación. Si el punto es el "punto base" de
 *     Copiapó, aparece marcado como BASE, igual que en el mapa.
 *  2) Instrumento (placa Petri) — tipo de plato (muestra / réplica / blanco
 *     de control), volumen de agua destilada congelada, ventana e intervalo
 *     de exposición, tinción elegida (solo las que el administrador permite)
 *     y bank de referencia.
 *  3) Observación microscópica — qué se cuenta bajo el campo:
 *     fibras, fragmentos, films, minerales, aglomerados y partículas
 *     inciertas. Estos conteos alimentan la concentración p/mL, la de
 *     deposición p/cm², la tasa p/m²·día y el índice de exposición 0-11+.
 *  4) Imagen del campo — se toma o sube una foto del plato. Corresponde a la
 *     evidencia que el admin revisará para aprobar o rechazar la muestra.
 *  5) Clima y medio ambiente — se busca automáticamente para la fecha/hora
 *     de la muestra: temperatura, humedad, viento (km/h, m/s, mph o nudos
 *     según tus preferencias), velocidad de ráfaga, dirección del viento
 *     (con punto cardinal) y precipitación de la ventana. Se adjunta al
 *     historial meteorológico del Excel. Aquí puedes dejar de mostrarlo.
 *  6) Confirmación — resumen del reporte a enviar. Al confirmar se valida, se
 *     guarda y puedes elegir registrar otro reporte inmediatamente.
 *
 * Unidades: se muestran con los valores que haya elegido en Ajustes
 * (temp °C/°F, viento km/h·m/s·mph·nudos, concentración part./mL o part./L).
 */
/* Cambia el color de fondo de la app (no de los paneles) según el estado */
function setBodyLevel(level) {
  document.body.classList.remove('level-0', 'level-1', 'level-2', 'level-3');
  if (level !== null && level !== undefined && level >= 0)
    document.body.classList.add('level-' + Math.min(level, 3));
}

/* Índice de exposición (0-11+) -> nivel de fondo 0-3 (bajo/moderado/alto/muy alto) */
function levelFromIndex(idx) {
  const i = (idx && typeof idx === 'object') ? idx.index : idx;
  if (i === null || i === undefined || isNaN(i)) return null;
  if (i <= 2) return 0;
  if (i <= 5) return 1;
  if (i <= 7) return 2;
  return 3;
}

/* ── Explicaciones del formulario ─────────────────────────────
   Se pueden mostrar u ocultar, y el usuario puede pedir que no se
   vuelvan a mostrar: esa elección se guarda en este dispositivo. */
const HELP_KEY = 'microalerta_help_seen';
function helpVisible() {
  try { return localStorage.getItem(HELP_KEY) !== '1'; } catch (e) { return true; }
}
function setHelpVisible(v) {
  try {
    if (v) localStorage.removeItem(HELP_KEY); else localStorage.setItem(HELP_KEY, '1');
  } catch (e) { /* almacenamiento no disponible */ }
}
function helpBlock(text, visible) {
  return `<div class="form-help${visible ? ' visible' : ''}">${text}</div>`;
}
function helpToggleHTML(visible) {
  return `<div class="card help-card">
      <h2>Explicaciones del formulario</h2>
      <div class="seg-group form-help-toggle">
        <button type="button" class="seg-btn ${visible ? 'on' : ''}" data-help="show">Mostrar explicaciones</button>
        <button type="button" class="seg-btn ${visible ? '' : 'on'}" data-help="hide">Ocultar explicaciones</button>
      </div>
      <label class="check-row">
        <input type="checkbox" id="helpNever" ${visible ? '' : 'checked'}>
        <span>No volver a mostrar estas explicaciones</span>
      </label>
    </div>`;
}

/* Muestra/oculta las explicaciones de las secciones del formulario */
function toggleFormHelp(show) {
  const visible = (typeof show === 'boolean')
    ? show
    : !$$('.form-help').some(el => el.classList.contains('visible'));
  $$('.form-help').forEach(el => el.classList.toggle('visible', visible));
  $$('.form-help-toggle .seg-btn').forEach(b =>
    b.classList.toggle('on', (b.dataset.help === 'show') === visible));
  const chk = $('#helpNever');
  if (chk) chk.checked = !visible;
  return visible;
}

/* Guarda las unidades también en la cuenta (si hay sesión iniciada) */
function syncPrefsToServer() {
  if (!state.user) return;
  api('/prefs', { method: 'PUT', json: { units: state.settings } }).catch(() => {});
}
async function loadPrefsFromServer() {
  if (!state.user) return;
  try {
    const d = await api('/prefs');
    const u = d.prefs && d.prefs.units;
    if (u) { state.settings = Object.assign(state.settings, u); saveSettings(); }
  } catch (e) { /* sin preferencias aún */ }
}

/* ── Utilidades ─────────────────────────────────────────────── */
function escapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function fmt(v, d) { return (v === null || v === undefined || v === '') ? (d || '—') : v; }
function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

function stainLabel(v) {
  return { lugol: 'Lugol', azul_metileno: 'Azul de metileno', ninguna: 'Sin tinción' }[v] || v;
}
function typeLabel(t) {
  return { muestra: 'Muestra de campo', replica: 'Réplica', blanco: 'Control (blanco)' }[t] || t;
}
function statusBadge(st) {
  if (st === 'aprobado') return '<span class="badge ok">Aprobado</span>';
  if (st === 'rechazado') return '<span class="badge no">Rechazado</span>';
  return '<span class="badge pend">Pendiente</span>';
}

async function api(path, opts = {}) {
  const init = { method: opts.method || 'GET', headers: opts.headers || {} };
  if (opts.body) {
    init.body = opts.body;
    if (!(opts.body instanceof FormData)) init.headers['Content-Type'] = 'application/json';
  } else if (opts.json) {
    init.body = JSON.stringify(opts.json);
    init.headers['Content-Type'] = 'application/json';
  }
  const resp = await fetch('/api' + path, init);
  let data = null;
  try { data = await resp.json(); } catch (e) { /* sin cuerpo */ }
  if (!resp.ok) {
    let msg = (data && data.error) || ('Error ' + resp.status);
    if (data && data.allowed) msg += ' (' + data.allowed.join(', ') + ')';
    const err = new Error(msg);
    err.status = resp.status;
    throw err;
  }
  return data;
}

function showBanner(msg, type) {
  const b = $('#banner');
  b.textContent = msg;
  b.className = 'banner ' + (type || '');
  clearTimeout(showBanner._t);
  showBanner._t = setTimeout(() => b.classList.add('hidden'), 4500);
}
function spinnerHTML(t) { return '<div class="spinner">' + escapeHtml(t || 'Cargando…') + '</div>'; }

/* Colores del índice (espejo de science.INDEX_COLORS) — tonos de plástico */
const IDX_COLORS = ['#8FD9AE', '#5FBF80', '#2E9E5B', '#9FC63B',
  '#D8D22B', '#F5C518', '#F2A31C', '#F2711C', '#E85D2A', '#E23B3B', '#B71C3C', '#8E6BD1'];

/* Escala del semáforo (espejo de science.SEMAPHORE_LEVELS): color, rango y
   recomendaciones de autocuidado por nivel. Es la leyenda del icono "i". */
const SEM_LEVELS = [
  { level: 0, label: 'Saludable', color: '#2E9E5B', range: '< 0.5',
    advice: 'Sin precaución especial. Aire limpio.',
    recommendations: [
      'Aire limpio: sin mascarilla ni restricciones para la población general.',
      'Buen momento para la actividad al aire libre, la escuela y el deporte.',
      'Mantén las placas de muestreo activas para seguir construyendo la serie.',
    ] },
  { level: 1, label: 'Moderada', color: '#F5C518', range: '0.5 – 2.0',
    advice: 'Personas sensibles: use mascarilla al aire libre.',
    recommendations: [
      'Personas sensibles (asma, alergias, adultos mayores, niñez): use mascarilla al aire libre.',
      'Ventila tu casa a primera hora, cuando el aire suele estar más limpio.',
      'Limita el ejercicio intenso y prolongado en exteriores.',
    ] },
  { level: 2, label: 'Alta', color: '#F2711C', range: '2.0 – 5.0',
    advice: 'Evite actividades al aire libre; use mascarilla.',
    recommendations: [
      'Use mascarilla (ideal N95/KN95) al salir a la calle.',
      'Evite la actividad física al aire libre.',
      'Mantén ventanas cerradas en horas de viento y limpia superficies con paño húmedo.',
    ] },
  { level: 3, label: 'Muy alta', color: '#E23B3B', range: '≥ 5.0',
    advice: 'Use mascarilla N95, permanezca en interiores.',
    recommendations: [
      'Permanece en interiores con puertas y ventanas cerradas.',
      'Si debes salir, use mascarilla N95/KN95 bien ajustada.',
      'Hidrátate y acude al médico si presentas tos, ardor de ojos o dificultad para respirar.',
    ] },
];

/* Nivel del semáforo (0-3) a partir de la concentración en part./mL */
function semLevelOf(conc) {
  const c = parseFloat(conc) || 0;
  if (c < 0.5) return 0;
  if (c < 2) return 1;
  if (c < 5) return 2;
  return 3;
}

function semaforoHTML(sem, idx, level) {
  const color = idx ? idx.color : sem.color;
  const num = idx ? idx.index_label : '';
  const lvl = (typeof level === 'number') ? level
    : (idx && idx.conc_p_ml != null ? semLevelOf(idx.conc_p_ml) : null);
  const recs = (lvl != null && SEM_LEVELS[lvl]) ? SEM_LEVELS[lvl].recommendations : [];
  return `<div class="semaforo">
    <div class="circle" style="background:${color}"><b>${num}</b></div>
    <div class="sem-main">
      <div class="sem-title-row">
        <div class="lbl">${sem.label} <span style="color:${color}">${escapeHtml(sem.range)}</span></div>
        <button type="button" class="sem-info-btn" data-sem-info aria-label="Ver escala y recomendaciones" title="Ver escala y recomendaciones">i</button>
      </div>
      <div class="adv">${escapeHtml(sem.advice)}</div>
      ${recs.length ? `<ul class="sem-recs">${recs.map(r => `<li>${escapeHtml(r)}</li>`).join('')}</ul>` : ''}
    </div>
  </div>`;
}

/* Modal de información: llena la escala del semáforo una vez y la cachea. */
function openSemInfo() {
  const body = $('#semInfoBody');
  if (body && !body.dataset.filled) {
    body.innerHTML = SEM_LEVELS.map(l => `
      <div class="sem-scale-item">
        <span class="dot" style="background:${l.color}"></span>
        <div>
          <b>${escapeHtml(l.label)} <span class="sem-range">${escapeHtml(l.range)} part./mL</span></b>
          <div class="sem-scale-advice">${escapeHtml(l.advice)}</div>
          <ul>${l.recommendations.map(r => `<li>${escapeHtml(r)}</li>`).join('')}</ul>
        </div>
      </div>`).join('');
    body.dataset.filled = '1';
  }
  const m = $('#semInfo');
  if (m) m.classList.remove('hidden');
}
function closeSemInfo() {
  const m = $('#semInfo');
  if (m) m.classList.add('hidden');
}

/* Barra tipo índice UV para el nivel de plásticos */
function gaugeHTML(idx) {
  if (!idx) return '';
  const pct = Math.min(100, (idx.index / idx.max_scale) * 100);
  const segs = IDX_COLORS.map(c => `<i style="background:${c}"></i>`).join('');
  return `<div class="gauge" role="img" aria-label="Índice ${idx.index_label} de ${idx.max_scale}">
    <div class="gauge-head">
      <span class="gauge-num" style="background:${idx.color}">${idx.index_label}</span>
      <span class="gauge-cat" style="color:${idx.color}">${escapeHtml(idx.label)}</span>
    </div>
    <div class="gauge-bar">${segs}<span class="gauge-marker" style="left:calc(${pct}% - 7px)"></span></div>
    <div class="gauge-scale"><span>0</span><span>${idx.max_scale}+</span></div>
    <div class="muted">${escapeHtml(idx.scale_note)}</div>
  </div>`;
}

function metricKeys(pairs) {
  return `<div class="metric-keys">` + pairs.map(([label, value]) =>
    `<div class="m"><b>${escapeHtml(value)}</b><span>${escapeHtml(label)}</span></div>`).join('') + `</div>`;
}

/* ── Clima en tiempo real (caché + refresco automático) ────── */
async function fetchWeather(force) {
  const age = state.wx.ts ? Date.now() - state.wx.ts : Infinity;
  if (!force && state.wx.data && age < 30000) return state.wx;
  try {
    const d = await api('/weather?lat=-27.37&lon=-70.33');
    if (d.weather) state.wx = { data: d.weather, ts: Date.now() };
  } catch (e) { /* conserva el último dato */ }
  return state.wx;
}
function wxStamp() {
  return state.wx.ts
    ? new Date(state.wx.ts).toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' })
    : '—';
}
function wxInnerFor(w) {
  if (!w || (w.temp === null && w.wind === null)) {
    return '<div class="muted">Clima no disponible en este momento. Se reintentará automáticamente.</div>';
  }
  const mk = [
    ['Temperatura', fmtTemp(w.temp)],
    ['Humedad', fmt(w.hum) + ' %'],
    ['Viento', fmtWind(w.wind)],
    ['Ráfagas', fmtWind(w.wind_max || w.wind)],
  ];
  if (w.precip !== null && w.precip !== undefined) {
    mk.push(['Precipitación', (+w.precip).toFixed(1) + ' mm']);
  }
  return metricKeys(mk) +
    `<div class="muted" style="margin-top:6px">Fuente ${escapeHtml(w.source || 'open-meteo')}</div>`;
}
function wxBlockInner(w) {
  w = w || state.wx.data;
  return wxInnerFor(w) +
    `<div class="muted" style="margin-top:6px">actualizado ${wxStamp()} · se renueva cada minuto</div>`;
}

let wxTimer = null;
function stopWxAutoRefresh() {
  if (wxTimer) { clearInterval(wxTimer); wxTimer = null; }
  document.removeEventListener('visibilitychange', onVisibility);
}
function startWxAutoRefresh() {
  stopWxAutoRefresh();
  wxTimer = setInterval(async () => {
    await fetchWeather(true);
    const el = document.getElementById('wxBlock');
    if (el) el.innerHTML = wxBlockInner();
  }, 60000);
  state.timers.push(wxTimer);
  document.addEventListener('visibilitychange', onVisibility);
}
async function onVisibility() {
  if (!document.hidden && ['home', 'selfcare'].includes(currentView())) {
    await fetchWeather(true);
    const el = document.getElementById('wxBlock');
    if (el) el.innerHTML = wxBlockInner();
  }
}
async function refreshWxNow() {
  showBanner('Actualizando clima…');
  await fetchWeather(true);
  const el = document.getElementById('wxBlock');
  if (el) el.innerHTML = wxBlockInner();
  showBanner('Clima actualizado', 'ok');
}

/* ── Clima de la ventana de exposición (formulario de reporte) ──
   Se busca solo: al elegir el punto y las fechas de exposición se consulta
   /api/weather y se muestran temperatura, humedad, viento, ráfaga, dirección,
   presión, precipitación y fuente. Al enviar, el backend guarda el mismo dato
   en weather_snapshots y el Excel lo publica en sus columnas de clima.      */
function isoUtcFromLocalInput(v) {
  if (!v) return null;
  const d = new Date(v);
  return isNaN(d.getTime()) ? null : d.toISOString();
}
function windDirLabel(deg) {
  if (deg === null || deg === undefined || isNaN(deg)) return '—';
  const c = compassLabel(+deg);
  return (c ? Math.round(+deg) + '° ' + c : Math.round(+deg) + '°');
}
function numOrDash(v, fn) {
  if (v === null || v === undefined || v === '' || isNaN(+v)) return '—';
  return fn ? fn(+v) : String(v);
}
function wxPreviewInner(w) {
  const data = (w === undefined) ? state.reportWx.data : w;
  if (state.reportWx.busy && !data)
    return '<div class="muted">Buscando el clima de la ventana de exposición…</div>';
  if (!data)
    return '<div class="muted">Elige el punto de muestreo y las fechas: el clima se completa solo y se adjunta a la muestra.</div>';
  return metricKeys([
    ['Temperatura', numOrDash(data.temp, fmtTemp)],
    ['Humedad', numOrDash(data.hum, v => v.toFixed(0) + ' %')],
    ['Viento', numOrDash(data.wind, fmtWind)],
    ['Ráfaga', numOrDash(data.wind_max, fmtWind)],
    ['Dir. viento', windDirLabel(data.wind_dir)],
    ['Presión', numOrDash(data.pressure, v => v.toFixed(1) + ' hPa')],
    ['Precipitación', numOrDash(data.precip, v => v.toFixed(1) + ' mm')],
  ]) + `<div class="muted" style="margin-top:6px">Fuente: ${escapeHtml(data.source || 'open-meteo')}</div>`;
}
function wxSentInner(w) {
  if (!w)
    return '<div class="muted">No se pudo leer el clima guardado, pero la muestra quedó registrada y el histórico se completa al aprobarla.</div>';
  const ventana = (w.window && w.window[0])
    ? `<div class="muted" style="margin-top:4px">Ventana: ${fmtDT(w.window[0])} → ${fmtDT(w.window[1])}</div>`
    : '';
  return wxPreviewInner(w) + ventana;
}
/* weather_snapshots (columnas de la base) -> claves de la vista previa */
function weatherFromSnapshot(w) {
  if (!w) return null;
  return {
    source: w.source, temp: w.temp_avg, hum: w.hum_avg, wind: w.wind_avg,
    wind_max: w.wind_max, wind_dir: w.wind_dir_avg, pressure: w.pressure_avg,
    precip: w.precip_mm, window: [w.ts_start, w.ts_end],
  };
}
function reportFormValues() {
  const sel = $('select[name=location_id]');
  const locId = sel ? sel.value : null;
  const loc = state.locations.find(l => String(l.id) === String(locId)) || null;
  const s = $('input[name=exposure_start]');
  const e = $('input[name=exposure_end]');
  return { loc: loc, start: s ? s.value : '', end: e ? e.value : '' };
}
async function updateReportWx(force) {
  const box = $('#wxPreview');
  if (!box) return;
  const stamp = $('#wxPreviewStamp');
  const f = reportFormValues();
  if (!f.loc) {
    state.reportWx = { data: null, ts: null, busy: false, key: null };
    box.innerHTML = wxPreviewInner();
    return;
  }
  const startIso = isoUtcFromLocalInput(f.start);
  const endIso = isoUtcFromLocalInput(f.end);
  const key = [f.loc.lat, f.loc.lon, startIso, endIso].join('|');
  if (!force && state.reportWx.key === key && state.reportWx.data) {
    box.innerHTML = wxPreviewInner();
    return;
  }
  state.reportWx = { data: state.reportWx.data, ts: state.reportWx.ts, busy: true, key: key };
  if (!state.reportWx.data) box.innerHTML = wxPreviewInner();
  const qs = 'lat=' + encodeURIComponent(f.loc.lat) + '&lon=' + encodeURIComponent(f.loc.lon) +
    (startIso ? '&start=' + encodeURIComponent(startIso) : '') +
    (endIso ? '&end=' + encodeURIComponent(endIso) : '');
  try {
    const d = await api('/weather?' + qs);
    state.reportWx = { data: d.weather || null, ts: Date.now(), busy: false, key: key };
    if (stamp && state.reportWx.ts)
      stamp.textContent = 'Actualizado ' + new Date(state.reportWx.ts)
        .toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' });
  } catch (err) {
    state.reportWx = { data: null, ts: null, busy: false, key: key };
    if (stamp) stamp.textContent = 'Clima no disponible ahora; se reintenta al enviar.';
  }
  const still = $('#wxPreview');
  if (still) still.innerHTML = wxPreviewInner();
}

/* ── Router ─────────────────────────────────────────────────── */
function currentView() {
  return (location.hash || '#/home').replace('#/', '').split('?')[0].split('/')[0] || 'home';
}
function updateBotnav() {
  $('#tabAdmin').classList.toggle('hidden', !(state.user && state.user.role === 'admin'));
}
function renderNavMarker(v) {
  const titles = { home: 'Resumen comunitario', panel: 'Panel', report: 'Nuevo reporte', map: 'Mapa de puntos',
    weather: 'Clima por lugares', protocol: 'Protocolo escolar', selfcare: 'Autocuidado',
    admin: 'Panel admin', settings: 'Ajustes y unidades', profile: 'Mi cuenta' };
  const sub = $('#subtitle');
  if (sub) sub.textContent = 'Atacama · ' + (titles[v] || 'MicroAlerta');
}
function destroyMap() {
  if (state.leaflet) {
    try { if (state.leaflet.stopWind) state.leaflet.stopWind(); } catch (e) { /* noop */ }
    try { state.leaflet.map.remove(); } catch (e) { /* noop */ }
    state.leaflet = null;
  }
}
function clearTimers() {
  state.timers.forEach(t => clearInterval(t));
  state.timers = [];
  stopWxAutoRefresh();
}
async function route() {
  clearTimers();
  setBodyLevel(null);        // al cambiar de vista el fondo vuelve al tono neutro
  const v = currentView();
  $$('#nav .tab').forEach(b => b.classList.toggle('active', b.dataset.view === v));
  renderNavMarker(v);
  if (v !== 'map') destroyMap();
  const view = $('#view');
  try {
    if (v === 'login') await renderLogin();
    else if (v === 'profile') await renderProfile();
    else if (v === 'settings') renderSettings();
    else if (v === 'weather') await renderWeatherPlaces();
    else if (v === 'map') { view.innerHTML = spinnerHTML('Preparando mapa…'); await renderMap(); }
    else if (v === 'protocol') await renderProtocol();
    else if (v === 'panel') await renderPanel();
    else if (v === 'selfcare') await renderSelfcare();
    else if (v === 'admin') await renderAdmin();
    else if (v === 'report') await renderReport();
    else await renderHome();
  } catch (err) {
    view.innerHTML = '<div class="empty">No se pudo cargar: ' + escapeHtml(err.message) + '</div>';
    if (err.status === 401) location.hash = '#/profile';
  }
  window.scrollTo(0, 0);
  updateBotnav();
}

/* ── INICIO ─────────────────────────────────────────────────── */
async function renderHome() {
  const view = $('#view');
  const [comm, recent] = await Promise.all([
    api('/community').then(d => { state.community = d; return d; }).catch(() => null),
    api('/reports?status=aprobado&limit=4').then(d => d.reports).catch(() => []),
  ]);
  await fetchWeather(false);
  startWxAutoRefresh();

  const locs = (comm && comm.locations) || [];
  let worstIdx = null;
  let worstLevel = null;
  locs.forEach(l => {
    const ix = l.report && l.report.index;
    if (ix && (!worstIdx || ix.index > worstIdx.index)) {
      worstIdx = ix;
      worstLevel = (l.report.semaphore && l.report.semaphore.level !== undefined)
        ? l.report.semaphore.level
        : levelFromIndex(ix);
    }
  });
  setBodyLevel(worstLevel);   // el fondo de la app refleja el nivel comunitario
  const worstSem = {
    label: worstIdx ? worstIdx.label : 'Sin datos aún',
    color: worstIdx ? worstIdx.color : '#94A0A8',
    range: worstIdx ? fmtConc(worstIdx.conc_p_ml) : '',
    advice: worstIdx ? 'Nivel más alto entre los puntos con datos aprobados.' : 'Sube tu primer reporte de muestreo',
  };

  const recentList = recent.map(r => `
    <div class="rep">
      <span class="dot" style="background:${r.index.color}"></span>
      <div class="body">
        <b>${escapeHtml(r.location_name)}</b>
        <div class="sub">${fmtConc(r.metrics.conc_p_ml)} · ${r.n_observed} partículas contadas</div>
        <div class="sub">${stainLabel(r.stain)} · ${typeLabel(r.sample_type)} · índice ${r.index.index_label}</div>
        <div class="sub">Aprobado: ${fmtDT(r.obs_created_at)}${r.obs_time ? ' · hora aprox. ' + escapeHtml(r.obs_time) : ''}</div>
      </div>
    </div>`).join('') || '<div class="empty">Aún no hay reportes aprobados.</div>';

  view.innerHTML = `
    <div class="card">
      <h2>Estado comunitario · Atacama</h2>
      ${semaforoHTML(worstSem, worstIdx, worstLevel)}
      ${gaugeHTML(worstIdx)}
      ${metricKeys([
        ['Puntos activos', comm ? comm.locations.length : 0],
        ['Reportes aprobados', comm ? comm.total_approved : 0],
        ['Muestras de campo', comm && comm.counts_by_kind ? (comm.counts_by_kind.muestra || 0) : 0],
        ['Blancos de control', comm && comm.counts_by_kind ? (comm.counts_by_kind.blanco || 0) : 0],
      ])}
    </div>
    <div class="card">
      <h2>Clima actual (Copiapó)</h2>
      <div id="wxBlock">${wxBlockInner()}</div>
      <div class="row2" style="margin-top:10px">
        <button class="btn ghost sm" type="button" onclick="refreshWxNow()">Actualizar ahora</button>
        <a href="#/weather" class="btn sm">Clima de otros lugares</a>
      </div>
    </div>
    <div class="card">
      <h2>Últimos reportes aprobados</h2>
      ${recentList}
      <a href="#/map" class="btn ghost">Ver el mapa</a>
    </div>
    <div class="card">
      <h2>¿Cómo aportas?</h2>
      <p class="muted" style="margin-bottom:6px">
        1) Sanitiza la placa Petri: lávala y desinféctala con alcohol 70° antes de verter los 40 mL de agua destilada congelada.<br>
        2) Colócala destapada, en altura (&gt;1,5 m) y al aire libre.<br>
        3) Déjala expuesta 24–72 h y obsérvala en el microscopio.<br>
        4) Sube la foto y tu conteo con la tinción utilizada.
      </p>
      <div class="row2">
        <a href="#/report" class="btn">Reportar muestra</a>
        <a href="#/protocol" class="btn ghost">Ver protocolo</a>
      </div>
    </div>
    ${!state.user ? `<div class="card">
      <h2>Participa como equipo escolar o vecinal</h2>
      <p class="muted">Para reportar necesitas una cuenta. Pide el alta a tu coordinador/a MicroAlerta.</p>
      <a href="#/profile" class="btn green">Iniciar sesión (demo)</a>
    </div>` : ''}
    <div class="footer-note">
      MicroAlerta · Ciencia escolar + datos ambientales + tecnología<br>
      Reporta la posible deposición de partículas tipo microplástico en el aire.
    </div>`;
}

/* ── LOGIN ──────────────────────────────────────────────────── */
async function renderLogin() {
  const view = $('#view');
  view.innerHTML = `
    <div class="card login-hero">
      <div class="logo big-logo">µ<span>A</span></div>
      <h1 class="page-title">Inicia sesión en MicroAlerta</h1>
      <p class="muted">Cuenta de equipo escolar, vecino/a o administración.</p>
      <form id="loginForm">
        <label class="req">Usuario</label>
        <input name="username" value="colegio" autocomplete="username" required>
        <label class="req">Contraseña</label>
        <input name="password" type="password" value="demo123" autocomplete="current-password" required>
        <button class="btn green" type="submit">Entrar</button>
      </form>
      <div class="demo-hint">
        <b>Cuentas demo</b>: <code>admin</code> · <code>colegio</code> · <code>ciudadano</code> — clave <code>demo123</code>
      </div>
    </div>`;
  $('#loginForm').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    try {
      const d = await api('/login', { method: 'POST', json: { username: fd.get('username'), password: fd.get('password') } });
      state.user = d.user;
      await loadPrefsFromServer();
      showBanner('Bienvenido/a, ' + d.user.name, 'ok');
      location.hash = '#/home';
    } catch (e) {
      showBanner('Credenciales inválidas', 'error');
    }
  });
}

/* ── CLIMA POR LUGARES (Copiapó = punto base; el usuario agrega los suyos) ── */
async function fetchPlaceWeather(p) {
  // El punto base reutiliza la lectura en vivo compartida si está fresca
  if (p.home) {
    await fetchWeather(false);
    return state.wx.data;
  }
  try {
    const d = await api('/weather?lat=' + p.lat + '&lon=' + p.lon, { timeout: 15000 });
    return d.weather;
  } catch (e) {
    return null;
  }
}

function placeBodyHTML(w, ts) {
  const body = wxInnerFor(w);
  const stamp = ts ? '<div class="muted" style="margin-top:6px">actualizado ' + ts + '</div>' : '';
  return body + stamp;
}

async function refreshPlaceCard(p) {
  const node = document.getElementById('wxp-' + p.id);
  if (!node) return;
  const w = await fetchPlaceWeather(p);
  const target = document.getElementById('wxp-' + p.id); // pudo cambiar la vista
  if (!target) return;
  const holder = target.querySelector('.wx-body');
  if (holder) {
    holder.innerHTML = placeBodyHTML(w,
      new Date().toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' }));
  } else if (w === null) {
    node.querySelector('.wx-body').innerHTML =
      '<div class="muted">No se pudo obtener el clima de este lugar ahora.</div>';
  }
}

async function loadAllPlaceWeather() {
  for (const p of currentPlaces()) {
    await refreshPlaceCard(p);
    await delay(120); // espacia las llamadas a los proveedores externos
  }
}

function removePlace(id) {
  state.places = state.places.filter(p => p.id !== id);
  savePlaces();
  showBanner('Lugar eliminado', 'ok');
  renderWeatherPlaces();
}

async function renderWeatherPlaces() {
  const view = $('#view');
  if (!state.locations.length)
    await api('/locations').then(d => { state.locations = d.locations; }).catch(() => {});

  const places = currentPlaces();
  const cards = places.map(p => `
    <div class="card" id="wxp-${p.id}">
      <div class="semaforo">
        <div class="circle" style="background:${p.home ? '#1E88E5' : '#4FA8F5'}">
          ${p.home ? 'BASE' : escapeHtml(p.name.slice(0, 2).toUpperCase())}
        </div>
        <div>
          <div class="lbl">${escapeHtml(p.name)}${p.home ? ' <span class="badge ok">punto base</span>' : ''}</div>
          <div class="adv">${p.lat.toFixed(3)}, ${p.lon.toFixed(3)}</div>
        </div>
      </div>
      <div class="wx-body">${spinnerHTML('Consultando clima…')}</div>
      ${!p.home ? `<button class="btn danger sm" type="button" onclick="removePlace('${p.id}')">Quitar</button>` : ''}
    </div>`).join('');

  const locOptions = state.locations
    .filter(l => !places.some(x => x.refId === l.id))
    .map(l => `<option value="${l.id}" data-lat="${l.lat}" data-lon="${l.lon}"
      data-name="${escapeHtml(l.name)}">${escapeHtml(l.name)} — ${escapeHtml(l.city)}</option>`)
    .join('');

  view.innerHTML = `
    <h1 class="page-title">Clima por lugares</h1>
    <div class="card">
      <h2>Punto de inicio</h2>
      <p class="muted"><b>Copiapó</b> es tu punto base: siempre aparece primero y es el centro del mapa.
      Agrega los lugares que quieras monitorear y vuelve aquí cuando quieras.</p>
      <button class="btn ghost sm" type="button" onclick="resetPlacesToHome()">
        Restablecer solo Copiapó (punto base)
      </button>
    </div>
    ${cards}
    <div class="card">
      <h2>Agregar un lugar</h2>
      <label>Elegir punto de muestreo</label>
      <select id="placeSelect"><option value="">— Selecciona —</option>${locOptions}</select>
      <button class="btn sm green" type="button" onclick="addPlaceFromSelect()">Agregar punto</button>
      <details style="margin-top:12px">
        <summary class="muted" style="cursor:pointer">O agregar un lugar personalizado…</summary>
        <label>Nombre</label><input id="cpName" placeholder="Ej: Casa de la abuela">
        <div class="input-row">
          <div><label class="req">Latitud</label><input id="cpLat" type="number" step="0.0001" placeholder="-27.37"></div>
          <div><label class="req">Longitud</label><input id="cpLon" type="number" step="0.0001" placeholder="-70.33"></div>
        </div>
        <button class="btn sm green" type="button" onclick="addCustomPlace()">Agregar lugar</button>
      </details>
    </div>
    <p class="muted footer-note">Los lugares se guardan en este dispositivo y su clima se
    refresca automáticamente cada minuto mientras estés aquí.</p>`;

  startWxAutoRefresh();                       // mantiene vivo el bloque de la casa
  state.timers.push(setInterval(() => loadAllPlaceWeather(), 60000));
  await loadAllPlaceWeather();
}

function addPlaceFromSelect() {
  const sel = $('#placeSelect');
  const opt = sel && sel.selectedOptions[0];
  if (!opt || !opt.value) { showBanner('Elige un punto de muestreo primero', 'error'); return; }
  const loc = {
    id: 'loc-' + opt.value,
    refId: opt.value,
    name: opt.dataset.name,
    lat: parseFloat(opt.dataset.lat),
    lon: parseFloat(opt.dataset.lon),
  };
  if (state.places.some(p => p.id === loc.id)) {
    showBanner('Ese lugar ya está en tu lista'); return;
  }
  state.places.push(loc);
  savePlaces();
  showBanner('Lugar agregado: ' + loc.name, 'ok');
  renderWeatherPlaces();
}

function addCustomPlace() {
  const name = ($('#cpName') || {}).value;
  const lat = parseFloat(($('#cpLat') || {}).value);
  const lon = parseFloat(($('#cpLon') || {}).value);
  if (!name || !isFinite(lat) || !isFinite(lon)) {
    showBanner('Completa nombre, latitud y longitud', 'error'); return;
  }
  state.places.push({ id: 'c' + Date.now(), name: name.trim(), lat, lon });
  savePlaces();
  showBanner('Lugar agregado: ' + name.trim(), 'ok');
  renderWeatherPlaces();
}

function resetPlacesToHome() {
  state.places = [];
  savePlaces();
  showBanner('Lista restablecida: solo Copiapó (punto base)', 'ok');
  renderWeatherPlaces();
}

/* ── REPORTAR ───────────────────────────────────────────────── */
function toLocalInput(d) {
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

async function renderReport() {
  const view = $('#view');
  if (!state.user) {
    view.innerHTML = `<div class="card login-hero">
      <div class="logo big-logo">µ<span>A</span></div>
      <h1 class="page-title">Necesitas una cuenta</h1>
      <p class="muted">Para subir un reporte inicia sesión con tu equipo escolar o vecinal.</p>
      <a href="#/profile" class="btn green">Ir a mi cuenta</a>
    </div>`;
    return;
  }
  if (!state.locations.length)
    await api('/locations').then(d => { state.locations = d.locations; });
  if (!state.stains.length)
    await api('/stains').then(d => { state.stains = d.stains; });

  const now = new Date();
  const start = new Date(now.getTime() - 24 * 3600 * 1000);
  const locOptions = state.locations.map(l =>
    `<option value="${l.id}">${escapeHtml(l.name)} — ${escapeHtml(l.city)}</option>`).join('');
  const stainOptions = state.stains.map(s =>
    `<option value="${s.value}">${escapeHtml(s.label)}</option>`).join('');

  const showHelp = helpVisible();
  const help = (text) => helpBlock(text, showHelp);
  view.innerHTML = `
    <h1 class="page-title">Nuevo reporte de muestreo</h1>
    ${helpToggleHTML(showHelp)}
    <form id="reportForm">
      <div class="card">
        <h2>Parte 1 · Placa Petri (recolección pasiva)</h2>
        ${help(`<b>Qué se registra aquí:</b> el plato Petri que estuvo destapado al aire libre.
        Elige el <b>punto de muestreo</b>, el <b>código de la placa</b> y su <b>tipo</b>:
        muestra de campo, réplica del mismo grupo o blanco de control cerrado. La
        <b>ventana de exposición</b> (inicio y fin) es el tiempo en que la placa captó
        partículas: define las horas de exposición y el clima que se adjunta. El
        <i>volumen</i> (40 mL) y el <i>área observada</i> (4 cm²) son los del protocolo y se
        usan para calcular la concentración y la deposición por cm².`)}
        <label class="req">Punto de muestreo</label>
        <select name="location_id" required>${locOptions}</select>

        <div class="input-row">
          <div><label>N° placa</label><input name="dish_id" placeholder="PL-005"></div>
          <div>
            <label class="req">Tipo de plato</label>
            <select name="sample_type" required>
              <option value="muestra">Muestra de campo</option>
              <option value="replica">Réplica (mismo grupo)</option>
              <option value="blanco">Control blanco cerrado</option>
            </select>
          </div>
        </div>
        <label>Grupo de réplicas (mismo grupo comparte el blanco)</label>
        <input name="replicate_group" placeholder="Ej: RG-COP-02 (vacío si única)">

        <div class="input-row">
          <div><label class="req">Inicio exposición</label>
            <input name="exposure_start" type="datetime-local" value="${toLocalInput(start)}" required></div>
          <div><label class="req">Fin exposición</label>
            <input name="exposure_end" type="datetime-local" value="${toLocalInput(now)}" required></div>
        </div>
        <label>Hora aproximada de observación (opcional)</label>
        <input name="obs_time" type="time" placeholder="HH:MM">
        <div class="input-row">
          <div><label>Volumen (mL)</label><input name="volume_ml" type="number" step="1" value="40"></div>
          <div><label>Área observada (cm²)</label><input name="area_cm2" type="number" step="0.1" value="4.0"></div>
        </div>
        <label>Medio de recolección</label>
        <input name="medium" value="Agua destilada congelada">
      </div>

      <div class="card">
        <h2>Parte 2 · Microscopio y tinción</h2>
        ${help(`<b>Cómo se cuenta bajo el microscopio:</b> con la tinción que permite la
        administración, cuenta las <b>partículas totales</b> del campo observado y repártelas por
        morfología: <b>fibras</b> (alargadas, típicas de textiles), <b>fragmentos</b> (irregulares),
        <b>films</b> (láminas) y <b>minerales/polvo</b>. Registra aparte las <b>partículas
        dudosas</b>: sirven para estimar la incertidumbre del conteo. Los aumentos 100×, 200× o
        400× indican la lente usada: a mayor aumento se ve menos campo, pero se identifican mejor
        las partículas pequeñas. La foto es la evidencia que revisa la administración.`)}
        <label class="req">Tinción utilizada (por eliminación)</label>
        <select name="stain" required>${stainOptions}</select>
        <div class="input-row">
          <div>
            <label>Aumento</label>
            <select name="microscope_mag">
              <option value="100">100×</option>
              <option value="200">200×</option>
              <option value="400" selected>400×</option>
            </select>
          </div>
          <div><label class="req">Partículas totales</label>
            <input id="nObs" name="n_observed" type="number" min="0" value="0" required></div>
        </div>
        <div id="estConc" class="muted" style="margin-top:6px">≈ ${fmtConc(0)}</div>

        <label>Morfologías observadas (categorías de partículas)</label>
        <div class="grid2">
          <div><label>Fibras</label><input name="morph_fiber" type="number" min="0" value="0"></div>
          <div><label>Fragmentos</label><input name="morph_fragment" type="number" min="0" value="0"></div>
          <div><label>Films (láminas)</label><input name="morph_film" type="number" min="0" value="0"></div>
          <div><label>Minerales / polvo</label><input name="morph_mineral" type="number" min="0" value="0"></div>
        </div>
        <label>Partículas inciertas</label>
        <input name="n_uncertain" type="number" min="0" value="0">
        <label>Foto del campo / placa</label>
        ${help(`<b>Evidencia:</b> la foto del campo o de la placa es lo que la administración
        revisa para aprobar y publicar el reporte; en el celular se abre la cámara directamente.
        En <b>Observaciones</b> anota anomalías, hollín visible o condiciones del sitio
        (por ejemplo: viento fuerte, tierra removida cerca, mucha gente en el lugar).`)}
        <input id="imgInput" type="file" accept="image/*" capture="environment" class="hidden">
        <div id="photoBox" class="photo">Toma o adjunta la foto<br><span style="font-size:11px">(la cámara del celular se abre automáticamente)</span></div>
        <label>Observaciones</label>
        <textarea class="ta" name="notes" placeholder="Anomalías, hollín visible, condiciones del sitio…"></textarea>
      </div>

      <div class="card">
        <h2>Parte 3 · Clima de la ventana de exposición (automático)</h2>
        ${help(`Estos datos se buscan y se adjuntan <b>solos</b>: temperatura, humedad, viento,
        ráfaga, dirección del viento, presión, precipitación y la <b>fuente</b> del dato.
        Se usan la ventana de exposición y las coordenadas del punto elegido: histórico si la
        placa ya se retiró, medición en vivo si la ventana incluye hoy. Con esto se puede
        correlacionar la deposición de partículas con el viento y el polvo del desierto.`)}
        <div id="wxPreview">${wxPreviewInner()}</div>
        <div class="row2" style="margin-top:10px">
          <button id="wxPreviewBtn" class="btn ghost sm" type="button">Actualizar clima</button>
          <span class="muted" id="wxPreviewStamp">Se calcula con el punto y las fechas elegidas.</span>
        </div>
      </div>

      <button id="reportSubmit" class="btn" type="submit">Enviar reporte a revisión</button>
      <p class="muted" style="margin-top:8px">Al enviar verás la confirmación con el resumen del
      reporte y el clima adjuntado, y podrás registrar otro reporte sin salir de esta pantalla.</p>
    </form>`;

// Estimación en vivo de concentración (con unidades del usuario)
  $('#nObs').addEventListener('input', (e) => {
    const n = parseInt(e.target.value || '0', 10);
    const v = parseFloat(document.querySelector('input[name=volume_ml]').value) || 40;
    $('#estConc').textContent = '≈ ' + fmtConc(n / v);
  });

  // Vista previa de la foto
  $('#imgInput').addEventListener('change', () => {
    const f = $('#imgInput').files[0];
    if (!f) return;
    const rd = new FileReader();
    rd.onload = () => { $('#photoBox').innerHTML = `<img src="${rd.result}" alt="foto de la placa">`; };
    rd.readAsDataURL(f);
  });
  $('#photoBox').addEventListener('click', () => $('#imgInput').click());

  // Explicaciones: mostrar/ocultar + "no volver a mostrar"
  $$('.form-help-toggle .seg-btn').forEach(b => b.addEventListener('click', () => {
    const visible = toggleFormHelp(b.dataset.help === 'show');
    setHelpVisible(visible);
  }));
  const neverChk = $('#helpNever');
  if (neverChk) neverChk.addEventListener('change', () => {
    setHelpVisible(!neverChk.checked);
    showBanner(neverChk.checked
      ? 'Listo: no volveremos a mostrar las explicaciones (puedes reactivarlas aquí arriba).'
      : 'Explicaciones activadas', 'ok');
  });

  // Clima de la ventana de exposición: se completa solo al elegir punto y fechas
  let wxDebounce = null;
  const wxTriggers = ['select[name=location_id]', 'input[name=exposure_start]', 'input[name=exposure_end]'];
  wxTriggers.forEach(sel => {
    const el = $(sel);
    if (!el) return;
    el.addEventListener('change', () => updateReportWx(false));
    el.addEventListener('input', () => {
      clearTimeout(wxDebounce);
      wxDebounce = setTimeout(() => updateReportWx(false), 700);
    });
  });
  const wxBtn = $('#wxPreviewBtn');
  if (wxBtn) wxBtn.addEventListener('click', () => updateReportWx(true));
  updateReportWx(false);

  $('#reportForm').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const btn = $('#reportSubmit');
    btn.disabled = true; btn.textContent = 'Enviando…';
    const fd = new FormData(ev.target);
    if ($('#imgInput').files && $('#imgInput').files[0]) fd.append('image', $('#imgInput').files[0]);
    try {
      const d = await api('/reports', { method: 'POST', body: fd });
      const r = d.report;
      setBodyLevel(r.semaphore ? r.semaphore.level : levelFromIndex(r.index));
      // Clima adjuntado: se lee el snapshot guardado con la muestra
      let wx = state.reportWx.data;
      try {
        const det = await api('/reports/' + r.obs_id);
        if (det && det.weather) wx = weatherFromSnapshot(det.weather);
      } catch (e) { /* se muestra el clima previsualizado */ }
      showBanner('Reporte enviado correctamente. Quedó en revisión.', 'ok');
      view.innerHTML = `
        <div class="card">
          <h2>✔ Reporte enviado ${statusBadge(r.status)}</h2>
          <p class="muted" style="margin-bottom:10px">Tu muestra quedó registrada con su clima.
          Un/a admin la revisará y, al aprobarla, aparecerá en el inicio, el mapa y el Excel de datos.</p>
          ${semaforoHTML(r.semaphore, r.index)}
          ${gaugeHTML(r.index)}
          ${metricKeys([
            ['Concentración', fmtConc(r.metrics.conc_p_ml)],
            ['Deposición', fmtDepo(r.metrics.depo_p_cm2)],
            ['Tasa diaria', Math.round(r.metrics.depo_p_m2_day) + ' p/m²·d'],
            ['Partículas', r.n_observed],
          ])}
          <p class="muted" style="margin-top:8px">
            ${stainLabel(r.stain)} · ${typeLabel(r.sample_type)} ·
            placa ${escapeHtml(r.dish_id || 'sin código')} · ${escapeHtml(r.location_name)}
            ${r.obs_time ? ' · hora aprox. ' + escapeHtml(r.obs_time) : ''}
          </p>
          <p class="muted">Registrado: ${fmtDT(r.obs_created_at)}</p>
          <h3 style="margin-top:12px">Clima adjuntado a esta muestra</h3>
          <div id="wxSent">${wxSentInner(wx)}</div>
          ${r.image_path ? `<div class="thumb-modal"><img src="${escapeHtml(r.image_path)}" alt="foto de la placa"></div>` : ''}
        </div>
        <div class="row2">
          <button id="anotherBtn" class="btn green" type="button">¿Registrar otro reporte?</button>
          <button id="homeBtn" class="btn ghost" type="button">Ir al inicio</button>
        </div>`;
      const another = $('#anotherBtn');
      if (another) another.addEventListener('click', () => {
        state.reportWx = { data: null, ts: null, busy: false, key: null };
        showBanner('Formulario listo para el próximo reporte');
        renderReport();
      });
      const homeBtn = $('#homeBtn');
      if (homeBtn) homeBtn.addEventListener('click', () => { location.hash = '#/home'; });
    } catch (e) {
      showBanner('No se pudo enviar: ' + e.message, 'error');
      btn.disabled = false; btn.textContent = 'Enviar reporte a revisión';
    }
  });
}

/* ── MAPA (Leaflet: satélite/relieve + animación de viento) ── */
function loadLeaflet() {
  return new Promise((resolve) => {
    if (window.L) return resolve(true);
    let settled = false;
    const done = (ok) => { if (!settled) { settled = true; resolve(ok); } };
    const css = document.createElement('link');
    css.rel = 'stylesheet';
    css.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
    document.head.appendChild(css);
    const sc = document.createElement('script');
    sc.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    sc.onload = () => done(true);
    sc.onerror = () => done(false);
    document.head.appendChild(sc);
    setTimeout(() => done(!!window.L), 7000);
  });
}

const COMPASS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSO', 'SO', 'OSO', 'O', 'ONO', 'NO', 'NNO'];
function compassLabel(deg) {
  if (deg === null || deg === undefined || isNaN(deg)) return '';
  return COMPASS[Math.round(deg / 22.5) % 16];
}

function pointPopup(l, data) {
  if (!data) {
    return `<b>${escapeHtml(l.name)}</b><br>${escapeHtml(l.city)}<br>
      <span class="muted">Sin reporte aprobado aún</span>`;
  }
  const r = data.report;
  const w = r.weather;
  const wLine = w && w.wind !== null && w.wind !== undefined
    ? `Viento: ${fmtWind(w.wind)}${w.wind_dir_avg != null ? ' del ' + compassLabel(w.wind_dir_avg) + ' (' + Math.round(w.wind_dir_avg) + '°)' : ''}<br>` : '';
  return `<b>${escapeHtml(l.name)}</b><br>${escapeHtml(l.city)}<br>
    Concentración: <b>${fmtConc(r.metrics.conc_p_ml)}</b><br>
    Índice ${r.index.index_label} · ${escapeHtml(r.index.label)}<br>
    Deposición: ${fmtDepo(r.metrics.depo_p_cm2)}<br>
    ${typeLabel(r.sample_type)} · ${stainLabel(r.stain)}<br>
    ${r.obs_created_at ? 'Fecha: ' + fmtDT(r.obs_created_at) + '<br>' : ''}${wLine}<span class="muted">Placa ${escapeHtml(r.dish_id || '')}${r.obs_time ? ' · hora aprox. ' + escapeHtml(r.obs_time) : ''}</span>`;
}

async function renderMap() {
  const [comm, allLoc] = await Promise.all([
    api('/community').then(d => { state.community = d; return d; }).catch(() => null),
    state.locations.length
      ? Promise.resolve({ locations: state.locations })
      : api('/locations').then(d => { state.locations = d.locations; return d; }),
  ]);
  const leafletOk = await loadLeaflet();
  if (leafletOk && window.L) renderLeafletMap(comm, allLoc.locations || []);
  else renderLegacyMap(comm, allLoc.locations || []);
}

function renderLeafletMap(comm, allLocations) {
  const view = $('#view');
  const locs = (comm && comm.locations) || [];
  const byId = {};
  locs.forEach(x => byId[x.location.id] = x);

  view.innerHTML = `
    <h1 class="page-title">Mapa de puntos · Región de Atacama</h1>
    <div class="card">
      <div class="map-wrap tall">
        <div id="leafletMap"></div>
        <canvas id="windCanvas" class="wx-canvas"></canvas>
      </div>
      <div class="wind-toggle">
        <span class="muted">Capa de viento:</span>
        <div class="seg-group" id="windModes">
          <button type="button" class="seg-btn mini ${state.windMode === 'streams' ? 'on' : ''}" data-mode="streams">Corrientes</button>
          <button type="button" class="seg-btn mini ${state.windMode === 'vectors' ? 'on' : ''}" data-mode="vectors">Vectores</button>
          <button type="button" class="seg-btn mini ${state.windMode === 'off' ? 'on' : ''}" data-mode="off">Apagado</button>
        </div>
      </div>
      <div class="map-legend">
        <span><i style="background:#8FD9AE"></i> Muy bajo</span>
        <span><i style="background:#9FC63B"></i> Bajo</span>
        <span><i style="background:#F5C518"></i> Moderado</span>
        <span><i style="background:#F2711C"></i> Alto</span>
        <span><i style="background:#E23B3B"></i> Muy alto</span>
        <span><i style="background:#8E6BD1"></i> Extremo</span>
      </div>
      <p class="muted" style="margin-top:6px">Capas: Callejero (OpenStreetMap), Satélite (Esri) y Relieve (OpenTopoMap). Toca un punto para ver su detalle.</p>
    </div>
    <div class="card">
      <h2>Último dato aprobado por punto</h2>
      ${pointListHTML(locs)}
    </div>`;

  destroyMap();
  const map = L.map('leafletMap', { zoomControl: true }).setView([-27.35, -70.45], 8);
  const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    { maxZoom: 19, attribution: '&copy; OpenStreetMap' }).addTo(map);
  // Satélite con nombres de lugares: imágenes Esri + capa de referencia
  const satBase = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    { maxZoom: 19, attribution: 'Imágenes &copy; Esri' });
  const satRef = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
    { maxZoom: 19, opacity: 0.95 });
  const sat = L.layerGroup([satBase, satRef]);
  const topo = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
    { maxZoom: 16, attribution: '&copy; OpenTopoMap (CC-BY-SA)' });
  L.control.layers(
    { 'Callejero': osm, 'Satélite': sat, 'Relieve': topo }, {}, { position: 'topright' }
  ).addTo(map);

  allLocations.forEach(l => {
    const d = byId[l.id];
    const color = d ? d.report.index.color : (l.color || '#94A0A8');
    L.circleMarker([l.lat, l.lon], {
      radius: d ? 9 : 5, color: '#15181B', weight: 1.5,
      fillColor: color, fillOpacity: 0.92,
    }).bindPopup(pointPopup(l, d)).addTo(map);
  });

  setTimeout(() => map.invalidateSize(), 150);

  state.leaflet = { map };

  const canvas = $('#windCanvas');
  setupWindAnimation(map, canvas, locs);
  $('#windModes').addEventListener('click', (e) => {
    const btn = e.target.closest('.seg-btn');
    if (!btn) return;
    state.windMode = btn.dataset.mode;
    $$('#windModes .seg-btn').forEach(b => b.classList.toggle('on', b === btn));
    if (state.leaflet && state.leaflet.restartWind) state.leaflet.restartWind();
  });
}

function pointListHTML(locs) {
  return locs.map(({ location, report }) => `
    <div class="rep">
      <span class="dot" style="background:${report.index.color}"></span>
      <div class="body">
        <b>${escapeHtml(location.name)}</b>
        <div class="sub">${escapeHtml(location.city)} · ${fmtConc(report.metrics.conc_p_ml)} · ${fmtDepo(report.metrics.depo_p_cm2)}</div>
        <div class="sub">${typeLabel(report.sample_type)} · ${stainLabel(report.stain)} · índice ${report.index.index_label} (${report.index.label})</div>
        <div class="sub">Aprobado: ${fmtDT(report.obs_created_at)}${report.obs_time ? ' · hora aprox. ' + escapeHtml(report.obs_time) : ''}</div>
      </div>
    </div>`).join('') ||
    '<div class="empty">Sube tu primer muestreo: los puntos aparecen al aprobarse.</div>';
}

/* Corrientes de viento de la zona: campo interpolado entre estaciones */
function setupWindAnimation(map, canvas, locs) {
  const container = map.getContainer();
  const ctx = canvas.getContext('2d');

  // Estaciones de viento: cada punto de muestreo con clima guardado
  // más la lectura EN VIVO del punto base (Copiapó).
  const stations = [];
  locs.forEach(({ location, report }) => {
    const w = report.weather;
    if (w && w.wind_dir_avg !== null && w.wind !== null && w.wind > 0) {
      const rad = (w.wind_dir_avg + 180) * Math.PI / 180; // hacia dónde va
      stations.push({ lat: location.lat, lon: location.lon,
        vx: Math.cos(rad) * w.wind, vy: Math.sin(rad) * w.wind });
    }
  });
  if (state.wx.data && state.wx.data.wind != null &&
      state.wx.data.wind_dir != null && state.wx.data.wind > 0) {
    const rad = (state.wx.data.wind_dir + 180) * Math.PI / 180;
    stations.push({ lat: -27.37, lon: -70.33,
      vx: Math.cos(rad) * state.wx.data.wind,
      vy: Math.sin(rad) * state.wx.data.wind, live: true });
  }
  if (!stations.length) {
    const rad = (250 + 180) * Math.PI / 180;   // respaldo: viento típico
    stations.push({ lat: -27.37, lon: -70.33,
      vx: Math.cos(rad) * 14, vy: Math.sin(rad) * 14 });
  }

  // Viento interpolado (IDW: inverso de la distancia al cuadrado, en km)
  function windAt(lat, lon) {
    let sx = 0, sy = 0, wsum = 0;
    for (let k = 0; k < stations.length; k++) {
      const s = stations[k];
      const dLat = (s.lat - lat) * 111;
      const dLon = (s.lon - lon) * 97;
      const wgt = 1 / (dLat * dLat + dLon * dLon + 0.03);
      sx += s.vx * wgt;
      sy += s.vy * wgt;
      wsum += wgt;
    }
    return { vx: sx / wsum, vy: sy / wsum };
  }

  // Modo vectores: rejilla de flechas con dirección e intensidad locales
  function drawVectors() {
    const w = canvas.width, h = canvas.height;
    const cols = Math.max(4, Math.ceil(w / 60));
    const rows = Math.max(3, Math.ceil(h / 48));
    for (let j = 0; j < rows; j++) {
      for (let i = 0; i < cols; i++) {
        const px = (i + 0.5) * w / cols;
        const py = (j + 0.5) * h / rows;
        const ll = map.containerPointToLatLng([px, py]);
        const wv = windAt(ll.lat, ll.lng);
        const spd = Math.hypot(wv.vx, wv.vy);
        if (!spd) continue;
        const ang = Math.atan2(wv.vy, wv.vx);
        const len = (9 + Math.min(26, spd * 1.6)) * Math.min(zoomScale, 1.7);
        const hx = px + Math.cos(ang) * len;
        const hy = py + Math.sin(ang) * len;
        ctx.strokeStyle = 'rgba(226, 240, 255, 0.85)';
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        ctx.moveTo(px, py);
        ctx.lineTo(hx, hy);
        ctx.stroke();
        const ha = ang + Math.PI;
        const hl = len * 0.38;
        ctx.strokeStyle = '#1E88E5';
        ctx.lineWidth = 1.8;
        ctx.beginPath();
        ctx.moveTo(hx, hy);
        ctx.lineTo(hx + Math.cos(ha - 0.5) * hl, hy + Math.sin(ha - 0.5) * hl);
        ctx.moveTo(hx, hy);
        ctx.lineTo(hx + Math.cos(ha + 0.5) * hl, hy + Math.sin(ha + 0.5) * hl);
        ctx.stroke();
      }
    }
  }

  // Escala según zoom: al acercar, las corrientes fluyen y se estiran más.
  // Escala ABSOLUTA de zoom: zoom 8 = referencia (1.0). Así el tamaño y la
  // velocidad de las corrientes/vectores se ajustan siempre igual al zoom.
  const REF_ZOOM = 8;
  let zoomScale = 1;
  function updateZoomScale() {
    zoomScale = Math.min(3, Math.max(0.55, Math.pow(1.7, map.getZoom() - REF_ZOOM)));
  }
  updateZoomScale();
  map.on('zoom zoomend', updateZoomScale);

  function resize() {
    canvas.width = container.clientWidth;
    canvas.height = container.clientHeight;
  }
  resize();
  map.on('resize', resize);
  window.addEventListener('resize', resize);

  // Cada corriente sigue un RUMBO que gira suavemente hacia el viento local,
  // con un vaivén muy sutil: trayectorias curvas continuas, sin zigzag.
  const N = 90;
  const TRAIL_MAX = 20;
  let flows = [];
  function spawn(p) {
    p = p || {};
    p.x = Math.random() * canvas.width;
    p.y = Math.random() * canvas.height;
    p.life = 140 + Math.random() * 200;
    p.wob = Math.random() * Math.PI * 2;
    p.wfreq = 0.006 + Math.random() * 0.014;    // vaivén muy lento
    p.speedJit = 0.75 + Math.random() * 0.5;    // variación individual
    const ll0 = map.containerPointToLatLng([p.x, p.y]);
    const w0 = windAt(ll0.lat, ll0.lng);
    p.head = Math.atan2(w0.vy, w0.vx) + (Math.random() - 0.5) * 0.6;
    p.trail = [];
    return p;
  }

  let rafId = null;
  function frame() {
    rafId = requestAnimationFrame(frame);
    if (state.windMode === 'off' || document.hidden) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      return;
    }
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (state.windMode === 'vectors') {
      drawVectors();
      return;
    }

    ctx.lineCap = 'round';
    flows.forEach((f, i) => {
      f.life -= 1;

      // Viento local interpolado en la posición actual de la corriente
      const ll = map.containerPointToLatLng([f.x, f.y]);
      const wv = windAt(ll.lat, ll.lng);
      const spdKmh = Math.hypot(wv.vx, wv.vy);
      const sp = Math.min(3.0, Math.max(0.35, spdKmh / 22)) * zoomScale * f.speedJit;

      // Giro SUAVE del rumbo hacia el viento local + vaivén lento (sin zigzag)
      const target = Math.atan2(wv.vy, wv.vx);
      let diff = target - f.head;
      while (diff > Math.PI) diff -= 2 * Math.PI;
      while (diff < -Math.PI) diff += 2 * Math.PI;
      f.head += diff * 0.06 + Math.sin(f.wob += f.wfreq) * 0.004;

      f.x += Math.cos(f.head) * sp;
      f.y += Math.sin(f.head) * sp;
      f.trail.push({ x: f.x, y: f.y });
      if (f.trail.length > TRAIL_MAX) f.trail.shift();

      if (f.life <= 0 || f.x < -40 || f.x > canvas.width + 40 ||
          f.y < -40 || f.y > canvas.height + 40) {
        flows[i] = spawn(f);
        return;
      }

      // Estela: segmentos con opacidad y grosor crecientes hacia la cabeza
      const tr = f.trail;
      for (let j = 1; j < tr.length; j++) {
        const k = j / tr.length;                 // 0 cola -> 1 cabeza
        ctx.strokeStyle = 'rgba(235, 255, 255, ' + (0.10 + 0.75 * k).toFixed(3) + ')';
        ctx.lineWidth = (0.8 + 1.8 * k) * Math.min(zoomScale, 1.6);
        ctx.beginPath();
        ctx.moveTo(tr[j - 1].x, tr[j - 1].y);
        ctx.lineTo(tr[j].x, tr[j].y);
        ctx.stroke();
      }
      // Cabeza luminosa de la corriente
      const head = tr[tr.length - 1];
      ctx.fillStyle = 'rgba(240, 255, 255, 0.95)';
      ctx.shadowColor = 'rgba(30, 136, 229, 0.95)';
      ctx.shadowBlur = 6 * Math.min(zoomScale, 1.5);
      ctx.beginPath();
      ctx.arc(head.x, head.y, 1.9 * Math.min(zoomScale, 1.5), 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;
    });
  }

  flows = Array.from({ length: N }, () => spawn());
  state.leaflet.restartWind = () => {
    if (state.windMode === 'off') { ctx.clearRect(0, 0, canvas.width, canvas.height); return; }
    if (!rafId) frame();
  };
  state.leaflet.stopWind = () => {
    if (rafId) cancelAnimationFrame(rafId);
    rafId = null;
  };
  state.leaflet.canvasResize = resize;
  frame();
}

/* Mapa estático SVG como respaldo cuando no hay conexión al CDN de Leaflet */
function renderLegacyMap(comm, allLocations) {
  const view = $('#view');
  const locs = (comm && comm.locations) || [];
  const W = 340, H = 300, PAD = 26;
  const project = (lat, lon) => ({
    x: +(PAD + (lon + 71.6) / 1.8 * (W - 2 * PAD)).toFixed(1),
    y: +(PAD + (-28.9 - lat) / 2.9 * (H - 2 * PAD)).toFixed(1),
  });

  const byId = {};
  locs.forEach(x => byId[x.location.id] = x);
  const pins = allLocations.map(l => {
    const d = byId[l.id];
    const color = d ? d.report.index.color : (l.color || '#94A0A8');
    const r = d ? 10 : 4;
    const p = project(l.lat, l.lon);
    return `<circle cx="${p.x}" cy="${p.y}" r="${r}" fill="${color}" opacity="${d ? 1 : .5}"
      stroke="#15181B" stroke-width="1.5"><title>${escapeHtml(l.name)}</title></circle>
      <text x="${p.x}" y="${p.y - r - 5}" text-anchor="middle" font-size="9" fill="#94A0A8">${escapeHtml(l.city)}</text>`;
  }).join('');

  view.innerHTML = `
    <h1 class="page-title">Mapa de puntos · Región de Atacama</h1>
    <div class="card">
      <div class="banner-inline muted">Modo sin conexión: mapa esquemático (capas satélite/relieve requieren internet).</div>
      <div class="map-wrap">
        <svg viewBox="0 0 ${W} ${H}">
          <rect width="${W}" height="${H}" rx="12" fill="#12171A"/>
          ${pins}
        </svg>
      </div>
    </div>
    <div class="card"><h2>Último dato aprobado por punto</h2>${pointListHTML(locs)}</div>`;
}

/* ── PROTOCOLO ──────────────────────────────────────────────── */
function accordionHTML(items) {
  return items.map(it => `
    <div class="acc">
      <div class="head">${it.t}</div>
      <div class="body">${it.b}</div>
    </div>`).join('');
}
function bindAccordions() {
  $$('.acc .head').forEach(h => h.addEventListener('click', () => {
    const a = h.parentElement;
    const was = a.classList.contains('open');
    $$('.acc').forEach(x => x.classList.remove('open'));
    if (!was) a.classList.add('open');
  }));
}

async function renderProtocol() {
  const view = $('#view');
  let videoUrl = '';
  try { videoUrl = (await api('/config')).video_url || ''; } catch (e) { /* sin video */ }
  const items = [
    { t: 'Objetivo', b: 'Detectar la posible deposición de partículas tipo microplástico en el aire del Desierto de Atacama (Copiapó y alrededores) usando ciencia escolar, y traducirla en recomendaciones de autocuidado para la comunidad.' },
    { t: 'Materiales', b: 'Placa Petri (Ø 90 mm aprox.), agua destilada congelada (40 mL), microscopio o lupa (100×–400×), Lugol al 5 %, azul de metileno 1 %, <b>alcohol 70° para sanitizar</b>, etiquetas y un celular para fotografiar.' },
    { t: 'Recolección pasiva', b: 'Verter 40 mL de agua destilada en la placa y congelarla. Colocar la placa DESTAPADA en el punto de muestreo (altura &gt; 1,5 m, alejada de fuentes). El hielo atrapa la deposición atmosférica mientras se derrite lentamente.' },
    { t: 'Exposición y control cerrado', b: 'Exponer 24–72 horas. En el mismo lote se deja una placa de CONTROL tapada durante toda la exposición (blanco analítico). Si el control tiene partículas, el lote puede estar contaminado.' },
    { t: 'Observación microscópica', b: 'Revisar el agua derretida por tramos (área ~4 cm²) y contar partículas por morfología: fibras, fragmentos, films/láminas y material mineral. Registrar lo dudoso como "incierto" con su foto.' },
    { t: 'Tinción por eliminación', b: 'Aplicar una de las tinciones limitadas: <b>Lugol</b> (presencia de almidón ⇒ origen biológico, color azul/violeta) o <b>azul de metileno</b> (contraste de estructuras). Por eliminación, lo que no tiñe ni parece orgánico/mineral se clasifica como potencial tipo microplástico. La app solo muestra las tinciones autorizadas por la administración.' },
    { t: 'Registro en la app', b: 'Elegir punto de muestreo, rellenar la ventana de exposición, subir la foto del campo, indicar la tinción y los conteos. Un/a administrador/a valida cada reporte antes de publicarlo en el mapa comunitario.' },
    { t: 'Réplicas y control de calidad', b: 'Por grupo de réplicas se recomiendan al menos 3 platos (ideal 1 control + 2 muestras). La app avisa si a un grupo le falta el blanco o si el control supera la tolerancia de 2 partículas.' },
    { t: 'Autocuidado e índice de exposición', b: 'Con la concentración (part./mL) se calcula un índice 0–11+ al estilo del índice UV solar. Junto al clima (viento, humedad, temperatura) la app entrega recomendaciones: mascarilla, evitar actividad al aire libre, hidratación y manejo de ventanas en ráfagas del desierto.' },
  ];
  view.innerHTML = `
    <h1 class="page-title">Protocolo escolar MicroAlerta</h1>
    <div class="card">
      <h2>Guía rápida para subir una muestra</h2>
      <ol class="guide-list">
        <li><b>Materiales:</b> placa Petri Ø 90 mm, 40 mL de agua destilada, marcador, alcohol 70° y celular.</li>
        <li><b>Sanitiza el material:</b> lava y desinfecta la placa (y la superficie de trabajo) con alcohol 70°, y lávate las manos antes de manipularla.</li>
        <li>Etiqueta la placa (punto y fecha) y congela los 40 mL de agua destilada.</li>
        <li>Colócala destapada, en altura (&gt;1,5 m) y lejos de fuentes, durante 24–72 h.</li>
        <li>Observa con microscopio (100–400×) y clasifica las morfologías.</li>
        <li>Aplica la tinción autorizada: Lugol o azul de metileno.</li>
        <li>Fotografía el campo y sube todo en “Reportar”.</li>
      </ol>
      ${videoUrl ? `<a class="btn green" href="${escapeHtml(videoUrl)}" target="_blank" rel="noopener">Ver video tutorial paso a paso</a>`
                 : '<div class="muted">Video tutorial en preparación.</div>'}
    </div>
    <div class="card">
      ${semaforoHTML({ label: 'Recolección + microscopio + tinción limitada', color: '#1E88E5',
        range: '', advice: 'Toca cada sección para ver los pasos exactos.' })}
      ${accordionHTML(items)}
    </div>
    <div class="footer-note">
      Basado en el proyecto previo “Microplásticos Aerotransportados” (Copiapó).<br>
      Comparte cada sección con tu curso o junta vecinal.
    </div>`;
  bindAccordions();
}

/* ── AUTOCUIDADO ────────────────────────────────────────────── */
/* Color del semáforo para una concentración dada (p/mL) */
function semColorOf(conc) {
  return conc < 0.5 ? '#2E9E5B' : conc < 2 ? '#F5C518' : conc < 5 ? '#F2711C' : '#E23B3B';
}

/* El círculo usa el color del nivel actual del semáforo */
function recCards(recommendations, levelColor) {
  const dot = levelColor || '#94A0A8';
  return recommendations.map(r => `
    <div class="rep">
      <span class="dot" style="background:${dot}"></span>
      <div class="body">
        <b>${escapeHtml(r.title)}</b>
        <div class="sub">${escapeHtml(r.detail)}</div>
      </div>
    </div>`).join('');
}

const SIM_EXPLAIN = [
  { t: '¿Qué es la concentración?', b: 'Es la cantidad de partículas potencialmente plásticas que quedaron depositadas en tu placa, dividida por el volumen de agua (40 mL). Se expresa en part./mL (o part./L) y es la métrica central del proyecto: permite comparar puntos, fechas y condiciones con una sola cifra.' },
  { t: '¿Por qué importa para la toma de datos?', b: 'Porque convierte un conteo manual en evidencia comparable: con los blancos validamos que no haya contaminación cruzada; con las réplicas confirmamos que el dato es estable; y con la serie de concentraciones detectamos patrones (días de viento fuerte, cercanía a fuentes, estaciones del año).' },
  { t: 'Humedad', b: 'Con humedad muy baja (&lt; 20 %) el aire seco levanta y mantiene partículas en suspensión. Con humedad alta tienden a depositarse con el rocío. Ajusta este valor según la lectura del clima actual.' },
  { t: 'Viento', b: 'El viento transporta partículas y, sobre 40 km/h, puede re-suspender polvo desde el suelo del desierto. Es el factor que más cambia la lectura entre días.' },
  { t: 'Temperatura', b: 'Influye en cuán rápido se derrite la placa congelada y en el confort respiratorio de la comunidad. Sobre 30 °C recomendamos reducir el esfuerzo al aire libre.' },
];

async function renderSelfcare() {
  const view = $('#view');
  const comm = await (state.community
    ? Promise.resolve(state.community)
    : api('/community').then(d => { state.community = d; return d; }).catch(() => null));
  await fetchWeather(false);
  startWxAutoRefresh();

  const locs = (comm && comm.locations) || [];
  let worst = null;
  locs.forEach(l => {
    const ix = l.report && l.report.index;
    if (ix && (!worst || ix.index > worst.index)) worst = ix;
  });

  const defaults = {
    conc: worst ? [0.02, 0.15, 0.7, 2.5, 6][Math.min(worst.index, 4)] : 0.1,
    hum: state.wx.data && state.wx.data.hum != null ? state.wx.data.hum : 40,
    wind: state.wx.data && state.wx.data.wind != null ? state.wx.data.wind : 15,
    temp: state.wx.data && state.wx.data.temp != null ? state.wx.data.temp : 18,
  };

  view.innerHTML = `
    <h1 class="page-title">Autocuidado comunitario</h1>
    <div class="card">
      <h2>Nivel actual (peor punto aprobado)</h2>
      ${worst ? semaforoHTML({
        label: worst.label, color: worst.color, range: fmtConc(worst.conc_p_ml),
        advice: 'Basado en el último reporte aprobado de la comunidad.',
      }, worst) : '<div class="muted">Aún no hay datos aprobados. Explora el simulador para entender la escala.</div>'}
      ${gaugeHTML(worst)}
      <div id="wxBlock">${wxBlockInner()}</div>
      <button class="btn ghost sm" type="button" onclick="refreshWxNow()">Actualizar clima ahora</button>
    </div>

    <div class="card">
      <h2>Entiende qué mides antes de simular</h2>
      ${accordionHTML(SIM_EXPLAIN)}
    </div>

    <div class="card">
      <h2>Simulador de condiciones</h2>
      <label>Concentración: <span id="vConc">${fmtConc(defaults.conc)}</span></label>
      <input id="slConc" type="range" min="0" max="8" step="0.05" value="${defaults.conc}">
      <div class="muted">Partículas potencialmente plásticas por mL de agua de la placa.</div>

      <label>Humedad relativa: <span id="vHum">${defaults.hum}</span> %</label>
      <input id="slHum" type="range" min="0" max="100" step="1" value="${defaults.hum}">
      <div class="muted">Bajo 20 % el aire seco favorece la dispersión del polvo.</div>

      <label>Viento: <span id="vWind">${fmtWind(defaults.wind)}</span></label>
      <input id="slWind" type="range" min="0" max="80" step="1" value="${defaults.wind}">
      <div class="muted">Sobre 40 km/h hay riesgo de re-suspensión desde el suelo.</div>

      <label>Temperatura: <span id="vTemp">${fmtTemp(defaults.temp)}</span></label>
      <input id="slTemp" type="range" min="-5" max="40" step="0.5" value="${defaults.temp}">
      <div class="muted">Afecta el derretimiento de la placa y el confort respiratorio.</div>

      <button id="btnRecalc" class="btn green" type="button">Calcular mis recomendaciones</button>
    </div>

    <div class="card">
      <h2>Recomendaciones</h2>
      <div id="recList"><div class="muted">Ajusta los controles y pulsa “Calcular mis recomendaciones”.</div></div>
    </div>`;

  const bindSlider = (id, lblId, fn) => $(id).addEventListener('input', e => {
    $(lblId).textContent = fn(parseFloat(e.target.value));
  });
  bindSlider('#slConc', '#vConc', v => fmtConc(v));
  bindSlider('#slHum', '#vHum', v => String(Math.round(v)));
  bindSlider('#slWind', '#vWind', v => fmtWind(v));
  bindSlider('#slTemp', '#vTemp', v => fmtTemp(v));
  bindAccordions();

  async function compute() {
    const p = new URLSearchParams({
      conc: $('#slConc').value, hum: $('#slHum').value,
      wind: $('#slWind').value, temp: $('#slTemp').value,
      utemp: state.settings.temp, uwind: state.settings.wind, uconc: state.settings.conc,
    });
    const d = await api('/selfcare?' + p.toString()).catch(() => ({ recommendations: [] }));
    const concSel = parseFloat($('#slConc').value) || 0;
    $('#recList').innerHTML = recCards(d.recommendations, semColorOf(concSel));
  }
  $('#btnRecalc').addEventListener('click', compute);
}

/* ── AJUSTES / UNIDADES ─────────────────────────────────────── */
const UNIT_OPTIONS = {
  temp: [['C', 'Celsius (°C)'], ['F', 'Fahrenheit (°F)']],
  wind: [['kmh', 'Kilómetros por hora (km/h)'], ['ms', 'Metros por segundo (m/s)'],
         ['mph', 'Millas por hora (mph)'], ['kn', 'Nudos (kt)']],
  conc: [['pml', 'Partículas por mililitro (part./mL)'], ['pl', 'Partículas por litro (part./L)']],
};
const UNIT_TITLES = { temp: 'Temperatura', wind: 'Velocidad del viento', conc: 'Concentración' };

function renderSettings() {
  const view = $('#view');
  const groups = Object.keys(UNIT_OPTIONS).map(key => `
    <div class="card">
      <h2>${UNIT_TITLES[key]}</h2>
      <div class="seg-group" data-key="${key}">
        ${UNIT_OPTIONS[key].map(([val, lbl]) => `
          <button type="button" class="seg-btn ${state.settings[key] === val ? 'on' : ''}"
                  data-val="${val}">${lbl}</button>`).join('')}
      </div>
      <div class="muted" style="margin-top:8px">Se guarda automáticamente al elegir una opción.</div>
    </div>`).join('');

  view.innerHTML = `
    <h1 class="page-title">Ajustes y unidades</h1>
    ${groups}
    <div class="card">
      <h2>Vista previa con tus unidades</h2>
      <div id="unitPreview">${unitPreviewHTML()}</div>
    </div>
    <div class="row2">
      <button id="resetUnits" class="btn ghost" type="button">Restablecer</button>
      <a href="#/home" class="btn green">Listo</a>
    </div>
    <p class="muted footer-note">Las unidades se guardan al instante en este dispositivo y se aplican
    a clima, simulador, mapa y resultados.</p>`;

  $$('.seg-group').forEach(group => {
    group.addEventListener('click', (ev) => {
      const btn = ev.target.closest('.seg-btn');
      if (!btn) return;
      const key = group.dataset.key;
      const val = btn.dataset.val;
      if (state.settings[key] === val) return;

      // Guardar al instante + reflejar selección
      state.settings[key] = val;
      saveSettings();
      syncPrefsToServer();
      $$('.seg-btn', group).forEach(b => b.classList.toggle('on', b === btn));
      $('#unitPreview').innerHTML = unitPreviewHTML();
      showBanner('Unidades guardadas: ' + UNIT_TITLES[key] + ' → ' + btn.textContent.trim(), 'ok');
    });
  });

  $('#resetUnits').addEventListener('click', () => {
    state.settings = { temp: 'C', wind: 'kmh', conc: 'pml' };
    saveSettings();
    syncPrefsToServer();
    renderSettings();
    showBanner('Unidades restablecidas a los valores recomendados', 'ok');
  });
}

function unitPreviewHTML() {
  return metricKeys([
    ['Temperatura de ejemplo', fmtTemp(20)],
    ['Viento de ejemplo', fmtWind(24)],
    ['Concentración de ejemplo', fmtConc(1.5)],
  ]);
}

/* ── PERFIL ─────────────────────────────────────────────────── */
function roleLabel(r) {
  return { admin: 'Administración', colegio: 'Equipo escolar', ciudadano: 'Vecino/a' }[r] || r;
}

async function renderProfile() {
  const view = $('#view');
  if (!state.user) { await renderLogin(); return; }
  const u = state.user;
  const isAdmin = u.role === 'admin';
  view.innerHTML = `
    <h1 class="page-title">Mi cuenta</h1>
    <div class="card">
      <div class="semaforo">
        <div class="circle" style="background:#1E88E5"><b>${escapeHtml(u.username.slice(0, 2).toUpperCase())}</b></div>
        <div>
          <div class="lbl">${escapeHtml(u.name)}</div>
          <div class="adv">${escapeHtml(u.school || '')} · ${roleLabel(u.role)}</div>
        </div>
      </div>
      <button id="logoutBtn" class="btn ghost" type="button">Cerrar sesión</button>
      ${isAdmin ? '<button class="btn green" type="button" onclick="location.hash=\'#/admin\'">Panel de administración</button>' : ''}
    </div>
    <a href="#/settings" class="btn ghost">Ajustes y unidades de medida</a>
    <div class="card">
      <h2>Instalar como app</h2>
      <p class="muted">
        <b>Android</b>: menú del navegador → “Añadir a pantalla de inicio”.<br>
        <b>iOS</b>: Compartir → “Añadir a pantalla de inicio”.<br>
        Así quedará instalada, con ícono propio y sin barra del navegador.
      </p>
    </div>
    <a href="#/report" class="btn">Reportar una muestra</a>
    <div class="footer-note">MicroAlerta · tu cuenta ${escapeHtml(u.username)}</div>`;

  $('#logoutBtn').addEventListener('click', async () => {
    await api('/logout', { method: 'POST' }).catch(() => {});
    state.user = null;
    updateBotnav();
    location.hash = '#/home';
    showBanner('Sesión cerrada');
  });
}

/* Acciones admin invocadas desde HTML generado */
async function adminAct(obsId, status) {
  const cmt = document.querySelector('#cmt-' + obsId);
  const comment = cmt ? cmt.value : '';
  try {
    await api(`/reports/${obsId}/review`, { method: 'POST', json: { status, comment } });
    showBanner(status === 'aprobado' ? 'Reporte aprobado y publicado' : 'Reporte rechazado',
               status === 'aprobado' ? 'ok' : '');
    await loadAdminTab();
  } catch (e) { showBanner(e.message, 'error'); }
}

async function toggleLoc(locId, active) {
  try {
    await api(`/locations/${locId}`, { method: 'PUT', json: { active } });
    showBanner('Punto actualizado', 'ok');
    await loadAdminTab();
  } catch (e) { showBanner(e.message, 'error'); }
}

/* ── ADMIN ──────────────────────────────────────────────────── */
let adminTab = 'pendientes';

async function renderAdmin() {
  const view = $('#view');
  if (!state.user) { await renderLogin(); return; }
  if (state.user.role !== 'admin') {
    view.innerHTML = '<div class="empty">Acceso restringido a administración.</div>';
    return;
  }
  view.innerHTML = `
    <h1 class="page-title">Panel de administración</h1>
    <div class="tabs-row" id="adminTabs">
      <button data-tab="pendientes" class="on">Pendientes</button>
      <button data-tab="tinciones">Tinciones</button>
      <button data-tab="ubicaciones">Puntos</button>
      <button data-tab="stats">Estadísticas</button>
    </div>
    <div id="adminContent"><div class="spinner">Cargando…</div></div>`;
  $$('#adminTabs button').forEach(b => b.addEventListener('click', () => {
    adminTab = b.dataset.tab;
    $$('#adminTabs button').forEach(x => x.classList.toggle('on', x === b));
    loadAdminTab();
  }));
  await loadAdminTab();
}

async function loadAdminTab() {
  const c = $('#adminContent');
  c.innerHTML = '<div class="spinner">Cargando…</div>';
  try {
    if (adminTab === 'tinciones') await loadTinciones();
    else if (adminTab === 'ubicaciones') await loadLocations();
    else if (adminTab === 'stats') await loadStats();
    else await loadPending();
  } catch (e) {
    c.innerHTML = '<div class="empty">' + escapeHtml(e.message) + '</div>';
  }
}

async function loadPending() {
  const d = await api('/pending');
  const wrap = $('#adminContent');
  if (!d.pending || !d.pending.length) {
    wrap.innerHTML = '<div class="empty">No hay reportes pendientes de revisión.</div>';
    return;
  }
  wrap.innerHTML = d.pending.map(p => `
    <div class="rep">
      ${p.image_path
        ? `<img class="thumb" src="${escapeHtml(p.image_path)}" alt="foto">`
        : `<span class="dot" style="background:${p.index.color}"></span>`}
      <div class="body">
        <b>${escapeHtml(p.location_name)}</b>
        <div class="sub">${fmtConc(p.metrics.conc_p_ml)} · ${p.n_observed} partículas · ${fmtDepo(p.metrics.depo_p_cm2)} · índice ${p.index.index_label}</div>
        <div class="sub">${stainLabel(p.stain)} · ${typeLabel(p.sample_type)} · reportó ${escapeHtml(p.user_name)}</div>
        <div style="margin-top:5px">
          <input id="cmt-${p.obs_id}" class="ta" placeholder="Comentario del/de la admin (opcional)">
        </div>
        <div class="row2">
          <button class="btn green sm" type="button" onclick="adminAct('${p.obs_id}','aprobado')">Aprobar</button>
          <button class="btn danger sm" type="button" onclick="adminAct('${p.obs_id}','rechazado')">Rechazar</button>
        </div>
      </div>
    </div>`).join('');
}

async function loadTinciones() {
  const d = await api('/stains?all=1');
  let vid = '';
  try { vid = (await api('/config')).video_url || ''; } catch (e) {}
  $('#adminContent').innerHTML = `
    <div class="card">
      <h2>Tinciones (variables limitadas del protocolo)</h2>
      <p class="muted">Solo las opciones activas aparecen en el formulario de reporte.</p>
      <div class="grid2">
        ${d.stains.map(s => `
          <label style="display:flex;align-items:center;gap:8px;margin:8px 0;cursor:pointer">
            <input type="checkbox" data-val="${s.value}" ${s.enabled ? 'checked' : ''}>
            <span>${escapeHtml(s.label)}</span>
          </label>`).join('')}
      </div>
      <button id="saveStains" class="btn" type="button">Guardar opciones</button>
    </div>
    <div class="card">
      <h2>Video tutorial de la guía</h2>
      <p class="muted">Enlace que verá la comunidad en “Protocolo”.</p>
      <label>URL de YouTube</label>
      <input id="vidUrl" value="${escapeHtml(vid)}" placeholder="https://youtu.be/...">
      <div class="row2" style="margin-top:10px">
        <button id="saveVid" class="btn green sm" type="button">Guardar enlace</button>
        ${vid ? `<a class="btn ghost sm" href="${escapeHtml(vid)}" target="_blank" rel="noopener">Probar</a>` : ''}
      </div>
    </div>`;
  $('#saveStains').addEventListener('click', async () => {
    const allowed = $$('#adminContent input[type=checkbox]')
      .filter(c => c.checked).map(c => c.dataset.val);
    try {
      const r = await api('/stains', { method: 'PUT', json: { allowed } });
      state.stains = r.stains;
      showBanner('Opciones de tinción guardadas', 'ok');
      await loadAdminTab();
    } catch (e) { showBanner(e.message, 'error'); }
  });
  $('#saveVid').addEventListener('click', async () => {
    const url = $('#vidUrl').value.trim();
    try {
      const r = await api('/config/video', { method: 'PUT', json: { url } });
      showBanner('Enlace del video actualizado', 'ok');
      $('#vidUrl').value = r.video_url;
    } catch (e) { showBanner(e.message, 'error'); }
  });
}

async function loadLocations() {
  const d = await api('/locations?include_inactive=1');
  const items = d.locations.map(l => `
    <div class="rep">
      <span class="dot" style="background:${l.color}"></span>
      <div class="body">
        <b>${escapeHtml(l.name)}</b>
        <div class="sub">${escapeHtml(l.city)} · ${l.lat}, ${l.lon} · ${l.active ? 'activo' : 'inactivo'}</div>
      </div>
      <button class="btn ghost sm" type="button" onclick="toggleLoc('${l.id}', ${l.active ? 0 : 1})">
        ${l.active ? 'Desactivar' : 'Activar'}
      </button>
    </div>`).join('');

  $('#adminContent').innerHTML = `
    <div class="card">
      <h2>Nuevo punto de muestreo</h2>
      <form id="locForm">
        <div class="input-row">
          <div><label class="req">Nombre</label><input name="name" required></div>
          <div><label>Ciudad/comuna</label><input name="city" value="Copiapó"></div>
        </div>
        <div class="input-row">
          <div><label class="req">Latitud</label><input name="lat" type="number" step="0.0001" required></div>
          <div><label class="req">Longitud</label><input name="lon" type="number" step="0.0001" required></div>
        </div>
        <label>Tipo</label>
        <select name="kind">
          <option value="comunidad">Comunidad</option>
          <option value="escuela">Escuela</option>
          <option value="referencia">Referencia</option>
        </select>
        <button class="btn green" type="submit">Agregar punto</button>
      </form>
    </div>
    <div class="card"><h2>Puntos existentes</h2>${items}</div>`;

  $('#locForm').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    try {
      await api('/locations', {
        method: 'POST',
        json: {
          name: fd.get('name'), city: fd.get('city'),
          lat: parseFloat(fd.get('lat')), lon: parseFloat(fd.get('lon')),
          kind: fd.get('kind'),
        },
      });
      showBanner('Punto agregado', 'ok');
      state.locations = [];
      await loadLocations();
    } catch (e) { showBanner(e.message, 'error'); }
  });
}

async function loadStats() {
  const d = await api('/stats');
  const s = d.stats || {};
  const overview = [
    ['Usuarios registrados', s.users],
    ['Puntos de muestreo', s.locations],
    ['Muestras (placas)', s.samples],
    ['Observaciones', s.observations],
    ['Pendientes de revisión', s.pending],
    ['Reportes aprobados', s.approved],
    ['Reportes rechazados', s.rejected],
    ['Conc. promedio aprobada', d.avg_conc_approved == null ? '—' : fmtConc(d.avg_conc_approved)],
  ];
  const morphLabels = { morph_fiber: 'Fibras', morph_fragment: 'Fragmentos',
                        morph_film: 'Films (láminas)', morph_mineral: 'Minerales / polvo' };

  const table = (head, rows) => rows.length
    ? `<table class="stat-table"><thead><tr>${head.map(h => `<th>${h}</th>`).join('')}</tr></thead>
       <tbody>${rows.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table>`
    : '<div class="empty">Sin datos aprobados todavía.</div>';

  $('#adminContent').innerHTML = `
    <div class="card">
      <h2>Totales</h2>
      <div class="stat-grid">
        ${overview.map(([lbl, num]) => `
          <div class="stat-card">
            <div class="stat-num">${typeof num === 'number' ? fmtNum(num) : escapeHtml(num)}</div>
            <div class="stat-lbl">${escapeHtml(lbl)}</div>
          </div>`).join('')}
      </div>
      <p class="muted">Números aislados con separador de miles; etiqueta independiente debajo.</p>
    </div>
    <div class="card">
      <h2>Por punto de muestreo</h2>
      ${table(['Punto', 'Comuna', 'Aprobados', 'Conc. promedio'],
        (d.by_location || []).map(r => [
          escapeHtml(r.name), escapeHtml(r.city || ''), fmtNum(r.n),
          r.avg_conc != null ? fmtConc(r.avg_conc) : '—']))}
    </div>
    <div class="card">
      <h2>Partículas por morfología</h2>
      ${table(['Morfología', 'Partículas'],
        Object.entries(d.by_morphology || {}).map(([k, v]) =>
          [morphLabels[k] || k, fmtNum(v)]))}
    </div>
    <div class="card">
      <h2>Por tinción utilizada</h2>
      ${table(['Tinción', 'Reportes aprobados'],
        Object.entries(d.by_stain || {}).map(([k, v]) =>
          [stainLabel(k), fmtNum(v)]))}
    </div>
    <div class="card">
      <h2>Excel de datos</h2>
      <p class="muted">El archivo <b>MicroAlerta_datos.xlsx</b> se actualiza solo cada vez que se
      registra, aprueba, edita o elimina una muestra. Incluye la hoja de muestras con todas las
      métricas y el clima, más gráficas listas (líneas, barras y torta).</p>
      <a class="btn green" href="/api/export.xlsx">Descargar Excel (.xlsx)</a>
      <div class="muted" style="margin-top:10px">En el servidor queda guardado en:
      <b>microalerta/data/MicroAlerta_datos.xlsx</b></div>
    </div>`;
}

/* ── PANEL ──────────────────────────────────────────────────
   Verificación del sistema + acciones + primeros pasos.     */
const QS_STEPS = [
  ['login', 'Inicia sesión con tu cuenta (colegio o ciudadano)'],
  ['protocol', 'Revisa el protocolo escolar: materiales y sanitización con alcohol 70°'],
  ['dish', 'Prepara la placa Petri: 40 mL de agua destilada congelada y expón 24 h'],
  ['report', 'Registra tu primera muestra en la pestaña Reportar'],
  ['approve', 'Espera la aprobación del administrador'],
  ['explore', 'Explora el resultado en el Mapa y el Autocuidado'],
  ['excel', 'Descarga el Excel de datos (admin → Estadísticas)'],
];
function qsLoadSteps() {
  try { return JSON.parse(localStorage.getItem('microalerta_qs_steps')) || {}; }
  catch (e) { return {}; }
}
function qsSaveSteps(o) {
  try { localStorage.setItem('microalerta_qs_steps', JSON.stringify(o)); } catch (e) {}
}

async function renderPanel() {
  const view = $('#view');
  const isAdmin = state.user && state.user.role === 'admin';
  const done = qsLoadSteps();
  view.innerHTML = `
    <h1 class="page-title">Panel</h1>
    <div class="card">
      <h2>Verificación del sistema</h2>
      <p class="muted">Comprueba en un paso que todo esté listo para muestrear: servidor,
      base de datos, sesión, tinciones, puntos, Excel y fuente de clima.</p>
      <button id="qsRun" class="btn green" type="button">Ejecutar verificación completa</button>
      <div id="qsResults" class="diag-list"></div>
    </div>
    <div class="card">
      <h2>Primeros pasos</h2>
      <p class="muted">Guía rápida para empezar a usar MicroAlerta; tu avance se guarda en este dispositivo.</p>
      <div class="steps-list" id="qsSteps">
        ${QS_STEPS.map((s, i) => `
          <div class="step-row ${done[s[0]] ? 'done' : ''}">
            <input type="checkbox" id="qs-step-${s[0]}" data-step="${s[0]}" ${done[s[0]] ? 'checked' : ''}>
            <label for="qs-step-${s[0]}"><span class="step-num">${i + 1}</span>${escapeHtml(s[1])}</label>
          </div>`).join('')}
      </div>
    </div>
    <div class="card">
      <h2>Acciones rápidas</h2>
      <div class="qa-grid">
        <button class="btn" type="button" data-go="report">Reportar muestra</button>
        <button class="btn" type="button" data-go="map">Ver mapa</button>
        <button class="btn" type="button" data-go="weather">Clima por lugares</button>
        <button class="btn" type="button" data-go="selfcare">Autocuidado</button>
        <button class="btn" type="button" data-go="protocol">Protocolo escolar</button>
        <button class="btn" type="button" data-go="settings">Ajustes y unidades</button>
        ${state.user ? '' : '<button class="btn green" type="button" data-go="profile">Iniciar sesión</button>'}
        ${isAdmin ? '<button class="btn" type="button" data-go="admin">Panel admin</button>' : ''}
      </div>
    </div>
    ${isAdmin ? `
    <div class="card">
      <h2>Mantenimiento (admin)</h2>
      <p class="muted">Acciones que mantienen al día el historial meteorológico y el Excel de datos.</p>
      <div class="qa-grid">
        <button class="btn" type="button" id="qsBackfill">Completar clima histórico</button>
        <button class="btn" type="button" id="qsXlsx">Regenerar Excel</button>
      </div>
      <div class="muted" id="qsMaint" style="margin-top:10px"></div>
    </div>` : ''}`;

  // Ejecutar verificación completa
  $('#qsRun').addEventListener('click', async () => {
    const box = $('#qsResults');
    box.innerHTML = spinnerHTML('Verificando sistema…');
    try {
      const d = await api('/diagnose');
      box.innerHTML = (d.checks || []).map(c => `
        <div class="diag-item">
          <span class="diag-dot ${escapeHtml(c.status)}"></span>
          <div>
            <div class="diag-name">${escapeHtml(c.name)}</div>
            <div class="diag-detail">${escapeHtml(c.detail)}</div>
          </div>
        </div>`).join('') +
        `<div class="muted" style="margin-top:6px">${d.ok
          ? 'Todo listo: la app está operativa.'
          : 'Hay elementos con error: revísalos antes de muestrear.'}</div>`;
      showBanner(d.ok ? 'Verificación completa: todo operativo'
                      : 'Verificación con observaciones', d.ok ? 'ok' : 'error');
    } catch (e) {
      box.innerHTML = '<div class="empty">No se pudo verificar: ' + escapeHtml(e.message) + '</div>';
    }
  });

  // Checklist de primeros pasos (guardado en el dispositivo)
  $('#qsSteps').addEventListener('change', (e) => {
    const cb = e.target.closest('input[type=checkbox]');
    if (!cb) return;
    const st = qsLoadSteps();
    st[cb.dataset.step] = cb.checked;
    qsSaveSteps(st);
    cb.closest('.step-row').classList.toggle('done', cb.checked);
  });

  // Acciones rápidas → navegación
  $$('.qa-grid [data-go]').forEach(b => b.addEventListener('click', () => {
    location.hash = '#/' + b.dataset.go;
  }));

  // Mantenimiento admin
  const maint = $('#qsMaint');
  async function runMaint(action, msg) {
    if (!maint) return;
    maint.textContent = msg + '…';
    try {
      const r = await api('/maintenance', { method: 'POST', json: { action } });
      maint.textContent = action === 'backfill_weather'
        ? ('Clima histórico completado: ' + (r.backfill && r.backfill.rellenadas || 0) +
           ' muestra(s) rellenadas · Excel regenerado.')
        : 'Excel regenerado y listo para descargar.';
      showBanner('Mantenimiento ejecutado', 'ok');
    } catch (e) { maint.textContent = 'Error: ' + e.message; }
  }
  const qb = $('#qsBackfill');
  if (qb) qb.addEventListener('click', () => runMaint('backfill_weather', 'Completando clima histórico'));
  const qx = $('#qsXlsx');
  if (qx) qx.addEventListener('click', () => runMaint('excel_sync', 'Regenerando Excel'));
}

/* ── Arranque ───────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  loadSettings();
  $$('#nav .tab').forEach(btn => btn.addEventListener('click', () => {
    location.hash = '#/' + btn.dataset.view;
  }));
  // Modal de información del semáforo (delegación: #view se re-renderiza)
  document.addEventListener('click', (e) => {
    const openBtn = e.target.closest('[data-sem-info]');
    if (openBtn) { openSemInfo(); return; }
    if (e.target.closest('[data-sem-info-close]')) { closeSemInfo(); return; }
    if (e.target.id === 'semInfo') { closeSemInfo(); }  // clic en el fondo
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeSemInfo(); });
  window.addEventListener('hashchange', route);
  bootstrap();
});

async function bootstrap() {
  loadPlaces();
  try { state.user = (await api('/session')).user; } catch (e) { /* sin sesión */ }
  if (state.user) await loadPrefsFromServer();
  try { state.stains = (await api('/stains')).stains; } catch (e) {}
  try { state.locations = (await api('/locations')).locations; } catch (e) {}
  if ('serviceWorker' in navigator) {
    try { navigator.serviceWorker.register('/static/sw.js'); } catch (e) { /* offline OK */ }
  }
  updateBotnav();
  route();
}