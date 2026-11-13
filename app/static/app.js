'use strict';
const ROLE = document.body.dataset.role;
const reportNode = document.querySelector('#report');
const STATUS_LABEL = {cumple: 'Cumple', por_revisar: 'Por revisar', no_cumple: 'No cumple', no_evaluable: 'No evaluable', manual: 'Revisión manual'};
const LIGHT_LABEL = {verde: 'Listo para tutoría', ambar: 'Necesita revisión', rojo: 'Borrador poco maduro'};
const RESPONSE_LABEL = {corregido: 'Lo he corregido', no_aplica: 'No aplica', pendiente: 'Pendiente'};
const OPEN = new Set(['por_revisar', 'no_cumple']);
const SEVERITY_ORDER = {no_cumple: 0, por_revisar: 1, manual: 2, no_evaluable: 3, cumple: 4};
let checklistDef = null;
let current = null; // {report, text, view, category, showAll}

function esc(value) { return String(value ?? '').replace(/[&<>'"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'}[c])); }
function fmtDate(iso) { return iso ? new Date(iso).toLocaleString('es-ES', {dateStyle: 'short', timeStyle: 'short'}) : ''; }
async function api(url, options = {}) {
  const response = await fetch(url, options);
  const isJson = (response.headers.get('content-type') || '').includes('json');
  const payload = isJson ? await response.json() : await response.text();
  if (!response.ok) { const error = new Error(payload?.detail?.message || payload?.detail || 'Error inesperado.'); error.detail = payload?.detail; error.status = response.status; throw error; }
  return payload;
}
async function getChecklist() { if (!checklistDef) checklistDef = await api('/api/checklist'); return checklistDef; }
function catColor(key) { return checklistDef?.categories?.[key]?.color || '#5146e5'; }
function catLabel(key) { return checklistDef?.categories?.[key]?.label || key; }

// --- Informe -------------------------------------------------------------------
async function openReport(id) {
  await getChecklist();
  const report = await api(`/api/reports/${encodeURIComponent(id)}`);
  current = {report, text: null, view: 'checklist', category: null, showAll: false};
  renderReport();
  reportNode.hidden = false;
  reportNode.scrollIntoView({behavior: 'smooth', block: 'start'});
}

function renderReport() {
  const r = current.report;
  if (!r.items) { reportNode.innerHTML = renderLegacy(r); return; }
  const usage = r.usage && ROLE === 'tutor' ? ` · ${r.usage.calls} llamadas, ${(r.usage.input_tokens + r.usage.cache_read_tokens + r.usage.cache_write_tokens).toLocaleString('es-ES')} tokens de entrada${r.usage.cost_usd ? `, ~${r.usage.cost_usd.toFixed(3)} US$` : ''}` : '';
  const evolution = r.evolution ? `<div class="banner ${r.evolution.score_delta >= 0 ? 'good' : 'bad'}"><strong>${r.evolution.score_delta >= 0 ? '+' : ''}${r.evolution.score_delta} puntos</strong> respecto a la versión anterior · ${r.evolution.resolved.length} avisos resueltos · ${r.evolution.persisting.length} persisten · ${r.evolution.new.length} nuevos${r.evolution.claimed_fixed_but_persisting.length ? `<br><span class="warn-text">Marcaste como corregidos ${r.evolution.claimed_fixed_but_persisting.map(esc).join(', ')}, pero se siguen detectando.</span>` : ''}</div>` : '';
  const llmErrors = r.llm_errors?.length ? `<div class="banner bad"><strong>El modelo no completó todas las comprobaciones.</strong> Los puntos afectados aparecen como «no evaluable».<details><summary>Detalles</summary><ul>${r.llm_errors.map(e => `<li>${esc(e)}</li>`).join('')}</ul></details></div>` : '';
  const tutorFeedback = r.tutor_review ? `<div class="banner info"><strong>Feedback del tutor</strong><p class="pre">${esc(r.tutor_review.comments)}</p>${r.tutor_review.stored_filename ? `<a class="file-link" href="/api/reports/${encodeURIComponent(r.document_id)}/reviews/latest/document" target="_blank">Abrir documento comentado</a>` : ''}</div>` : '';
  const revision = r.revision_check ? `<div class="banner ${r.revision_check.status === 'attention' ? 'bad' : 'info'}"><strong>¿Se aplicó el feedback anterior del tutor?</strong> ${esc(r.revision_check.message)}<details><summary>${r.revision_check.addressed.length} sugerencias con indicios de cambio · ${r.revision_check.pending.length} sin indicios</summary><ul>${r.revision_check.pending.map(p => `<li>Sin indicios: ${esc(p.suggestion)}</li>`).join('')}${r.revision_check.addressed.map(p => `<li>Con indicios (${esc(p.evidence_terms.join(', '))}): ${esc(p.suggestion)}</li>`).join('')}</ul></details></div>` : '';
  const categories = Object.entries(r.categories).filter(([, c]) => c.evaluated || c.open).map(([key, c]) => `
    <button class="cat-card ${current.category === key ? 'active' : ''}" data-category="${esc(key)}" style="--cat:${catColor(key)}">
      <span>${esc(c.label)}</span><strong>${c.score ?? '–'}${c.score != null ? '<small>/100</small>' : ''}</strong>
      <span class="bar"><i style="width:${c.score ?? 0}%"></i></span><small>${c.open} aviso${c.open === 1 ? '' : 's'} abierto${c.open === 1 ? '' : 's'}</small>
    </button>`).join('');
  reportNode.innerHTML = `<div class="card report">
    <div class="report-head">
      <div class="score ${esc(r.traffic_light)}">${r.maturity_score}<small>/100</small></div>
      <div><p class="eyebrow">${esc(LIGHT_LABEL[r.traffic_light] || 'Diagnóstico')}</p><h2>${esc(r.filename)}</h2>
      <p class="muted">${(r.word_count || 0).toLocaleString('es-ES')} palabras · ${esc(r.model_label)} · ${r.duration_seconds ?? '?'} s${usage}</p>
      <p class="muted small">${esc(r.disclaimer)} Cada aviso indica si procede de las <span class="src regla">Reglas</span> automáticas o de un modelo de <span class="src ia">IA</span> (y de cuál).</p>
      ${ROLE === 'tutor' ? `<p class="small"><a href="/api/reports/${encodeURIComponent(r.document_id)}/results.xlsx">Descargar resultado en Excel</a> · <a href="/tutor/reports/${encodeURIComponent(r.document_id)}/trace" target="_blank">Ver traza del análisis (prompts y respuestas del modelo)</a></p>` : ''}</div>
    </div>
    ${evolution}${llmErrors}${tutorFeedback}${revision}
    ${ROLE === 'student' ? renderSubmitBox(r) : renderSubmissionInfo(r)}
    <h3>Resumen por categoría</h3><div class="cat-grid">${categories}</div>
    <div class="tabs" role="tablist"><button role="tab" data-view="checklist" class="${current.view === 'checklist' ? 'active' : ''}">Checklist</button><button role="tab" data-view="document" class="${current.view === 'document' ? 'active' : ''}">Borrador con comentarios</button></div>
    <div id="report-view"></div>
  </div>`;
  reportNode.querySelectorAll('[data-category]').forEach(b => b.addEventListener('click', () => { current.category = current.category === b.dataset.category ? null : b.dataset.category; renderReport(); }));
  reportNode.querySelectorAll('[data-view]').forEach(b => b.addEventListener('click', () => { current.view = b.dataset.view; renderReport(); }));
  reportNode.querySelector('#submit-button')?.addEventListener('click', submitToTutor);
  renderView();
}

function renderSubmissionInfo(r) {
  return r.submitted_at ? `<p class="muted">Enviado al tutor el ${fmtDate(r.submitted_at)}.</p>` : `<p class="muted">El estudiante aún no ha enviado esta versión.</p>`;
}

function renderSubmitBox(r) {
  if (r.submitted_at) return `<div class="submit-box sent">✓ Enviado a tu tutor el ${fmtDate(r.submitted_at)}.</div>`;
  const threshold = r.submit_threshold;
  const pending = (r.blocking_items || []).filter(id => r.responses?.[id]?.status !== 'no_aplica');
  const ready = r.maturity_score >= threshold && !pending.length;
  const reasons = [];
  if (r.maturity_score < threshold) reasons.push(`La madurez debe ser al menos ${threshold}/100 (ahora ${r.maturity_score}).`);
  if (pending.length) reasons.push(`Resuelve en una nueva versión, o justifica como «no aplica», los puntos imprescindibles: ${pending.map(esc).join(', ')}.`);
  return `<div class="submit-box ${ready ? 'ready' : ''}"><div><strong>${ready ? 'Este borrador puede enviarse a tu tutor.' : 'Antes de enviarlo a tu tutor:'}</strong>${reasons.length ? `<ul>${reasons.map(x => `<li>${x}</li>`).join('')}</ul>` : ''}<p id="submit-status" class="muted" role="status"></p></div><button id="submit-button" ${ready ? '' : 'disabled'}>Enviar al tutor</button></div>`;
}

async function submitToTutor() {
  const status = document.querySelector('#submit-status');
  try {
    const result = await api(`/api/reports/${encodeURIComponent(current.report.document_id)}/submit`, {method: 'POST'});
    current.report.submitted_at = result.submitted_at;
    renderReport();
    const cell = document.querySelector(`tr[data-row-id="${current.report.document_id}"] td:nth-child(5)`);
    if (cell && !cell.querySelector('details')) cell.innerHTML = '<span class="badge info">Enviado</span>';
  } catch (error) {
    status.innerHTML = error.detail?.reasons ? error.detail.reasons.map(esc).join('<br>') : esc(error.message);
  }
}

function renderView() {
  const view = reportNode.querySelector('#report-view');
  if (current.view === 'document') { renderDocument(view); return; }
  const r = current.report;
  const items = r.items.filter(i => !current.category || i.category === current.category);
  const visible = current.showAll ? items : items.filter(i => OPEN.has(i.status) || i.status === 'manual');
  const hidden = items.length - visible.length;
  visible.sort((a, b) => (SEVERITY_ORDER[a.status] - SEVERITY_ORDER[b.status]) || (b.must_fix - a.must_fix) || (b.weight - a.weight));
  view.innerHTML = `<div class="view-toolbar">${current.category ? `<span class="chip" style="--cat:${catColor(current.category)}">${esc(catLabel(current.category))} <button class="link-button" data-clear>✕</button></span>` : '<span class="muted">Ordenado por prioridad (frecuencia y esfuerzo según la encuesta a tutores).</span>'}
    ${hidden || current.showAll ? `<button class="link-button" data-toggle-all>${current.showAll ? 'Mostrar solo avisos abiertos' : `Mostrar también ${hidden} puntos superados o no evaluables`}</button>` : ''}</div>
    ${visible.map(renderItem).join('') || '<p class="muted">No hay avisos abiertos en esta categoría.</p>'}`;
  view.querySelector('[data-clear]')?.addEventListener('click', () => { current.category = null; renderReport(); });
  view.querySelector('[data-toggle-all]')?.addEventListener('click', () => { current.showAll = !current.showAll; renderView(); });
  view.querySelectorAll('[data-goto]').forEach(b => b.addEventListener('click', () => { current.view = 'document'; current.focus = b.dataset.goto; renderReport(); }));
  view.querySelectorAll('[data-respond]').forEach(b => b.addEventListener('click', () => respond(b)));
  view.querySelectorAll('[data-show-note]').forEach(b => b.addEventListener('click', () => { b.closest('.respond').querySelector('.note-form').hidden = false; }));
}

function shortModel(id) { return String(id || '').replace(/^(anthropic|ollama):/, ''); }
function srcBadge(c) {
  return c.source === 'ia'
    ? `<span class="src ia" title="Generado por el modelo ${esc(c.model || '')}">IA${c.model ? ' · ' + esc(shortModel(c.model)) : ''}</span>`
    : '<span class="src regla" title="Comprobación automática con reglas deterministas">Regla</span>';
}
function renderProvenance(item) {
  const p = item.provenance;
  if (!p || !p.sources?.length) return '';
  const parts = p.sources.map(s => `<span class="src ${s.source}">${s.source === 'regla' ? 'Reglas' : `IA${s.model ? ' · ' + esc(shortModel(s.model)) : ''}`}</span> <span class="badge ${esc(s.status)}">${STATUS_LABEL[s.status]}</span>`);
  const decided = p.decided_by?.length ? ` → estado final decidido por ${p.decided_by.map(d => d === 'regla' ? 'las reglas' : 'la IA').join(' y ')}` : '';
  return `<p class="source-line">Procedencia: ${parts.join(' · ')}${decided}</p>`;
}

function renderItem(item) {
  const response = current.report.responses?.[item.id];
  const comments = item.comments.map((c, index) => `<li class="comment">
      ${c.quote ? `<blockquote>${esc(c.quote)}</blockquote>` : ''}<p>${esc(c.feedback)}</p>
      <p class="meta">${srcBadge(c)}${c.location ? ` · ${esc(c.location)}` : ''}
      ${c.verified === false ? ' · <span class="warn-text" title="El modelo citó un texto que no aparece en el borrador: puede ser una alucinación.">cita no localizada en el borrador</span>' : ''}
      ${c.anchor ? ` · <button class="link-button" data-goto="${esc(item.id)}:${index}">Ver en el borrador</button>` : ''}</p></li>`).join('');
  let respond = '';
  if (ROLE === 'student' && (OPEN.has(item.status) || item.status === 'manual')) {
    respond = `<div class="respond" data-item="${esc(item.id)}">
      ${response ? `<p class="muted">Tu respuesta: <strong>${esc(RESPONSE_LABEL[response.status])}</strong>${response.note ? ` — «${esc(response.note)}»` : ''}</p>` : ''}
      <button class="small ghost" data-respond="corregido">Lo he corregido</button>
      <button class="small ghost" data-show-note>No aplica…</button>
      <div class="note-form" hidden><textarea rows="2" placeholder="Explica por qué este aviso no aplica a tu trabajo (lo verá tu tutor)."></textarea><button class="small" data-respond="no_aplica">Guardar justificación</button></div>
    </div>`;
  } else if (response) {
    respond = `<p class="student-response">Respuesta del estudiante: <strong>${esc(RESPONSE_LABEL[response.status])}</strong>${response.note ? ` — «${esc(response.note)}»` : ''} <span class="muted">(${fmtDate(response.created_at)})</span></p>`;
  }
  return `<article class="item ${esc(item.status)}" style="--cat:${catColor(item.category)}" id="item-${esc(item.id)}">
    <header><span class="badge ${esc(item.status)}">${STATUS_LABEL[item.status]}</span><h4><span class="item-id">${esc(item.id)}</span> ${esc(item.title)}</h4>
    ${item.must_fix ? '<span class="tag" title="Los tutores piden corregirlo siempre antes de enviar el borrador">Imprescindible</span>' : ''}<span class="cat-label">${esc(catLabel(item.category))}</span></header>
    ${renderProvenance(item)}
    ${item.evidence ? `<p class="evidence">${esc(item.evidence)}</p>` : ''}
    ${comments ? `<ul class="comments">${comments}</ul>` : ''}
    <details class="guidance"><summary>Por qué importa y cómo revisarlo</summary><p>${esc(item.guidance)}</p></details>
    ${respond}
  </article>`;
}

async function respond(button) {
  const box = button.closest('.respond');
  const status = button.dataset.respond;
  const note = box.querySelector('textarea')?.value || '';
  try {
    const saved = await api(`/api/reports/${encodeURIComponent(current.report.document_id)}/responses`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({item_id: box.dataset.item, status, note: status === 'no_aplica' ? note : ''})});
    current.report.responses = {...(current.report.responses || {}), [saved.item_id]: saved};
    renderReport();
  } catch (error) { alert(error.message); }
}

// --- Borrador con comentarios al margen -------------------------------------------
async function renderDocument(view) {
  if (current.text === null) {
    view.innerHTML = '<p class="muted">Cargando el texto del borrador…</p>';
    try { current.text = await api(`/api/reports/${encodeURIComponent(current.report.document_id)}/text`); }
    catch (error) { view.innerHTML = `<p class="muted">${esc(error.message)}</p>`; return; }
  }
  const text = current.text;
  const notes = [];
  current.report.items.forEach(item => item.comments.forEach((c, index) => {
    if (c.anchor && (!current.category || item.category === current.category)) notes.push({key: `${item.id}:${index}`, item, c, start: c.anchor[0], end: c.anchor[1]});
  }));
  notes.sort((a, b) => a.start - b.start);
  let html = '', cursor = 0, lastMark = null;
  for (const note of notes) {
    if (note.start < cursor) { note.mark = lastMark; continue; } // empieza dentro del último pasaje resaltado: comparte su marca
    note.markId = `mark-${note.key.replace(':', '-')}`;
    note.mark = lastMark = note.markId;
    html += esc(text.slice(cursor, note.start)) + `<mark id="${note.markId}" class="${esc(note.item.status)}" style="--cat:${catColor(note.item.category)}" data-note="${esc(note.key)}" title="${esc(note.item.title)}">${esc(text.slice(note.start, note.end))}</mark>`;
    cursor = note.end;
  }
  html += esc(text.slice(cursor));
  const margin = notes.map(n => `<button class="margin-note" data-key="${esc(n.key)}" data-mark="${esc(n.mark || '')}" style="--cat:${catColor(n.item.category)}">
      <span class="meta"><span class="item-id">${esc(n.item.id)}</span> ${esc(catLabel(n.item.category))} · ${srcBadge(n.c)}</span>
      <span>${esc(n.c.feedback)}</span></button>`).join('');
  const legend = Object.keys(checklistDef.categories).map(k => `<button class="chip ${current.category === k ? 'active' : ''}" data-filter="${esc(k)}" style="--cat:${catColor(k)}">${esc(catLabel(k))}</button>`).join('');
  view.innerHTML = `<div class="view-toolbar"><div class="legend">${legend}</div><span class="muted">${notes.length} comentarios localizados en el texto</span></div>
    <div class="doc-layout"><div class="doc-text" id="doc-text">${html}</div><aside class="doc-margin" id="doc-margin">${margin || '<p class="muted">No hay comentarios con ubicación para este filtro.</p>'}</aside></div>
    <p class="muted small">El texto mostrado es el extraído automáticamente del archivo: el formato, las figuras y la paginación del original no se conservan.</p>`;
  view.querySelectorAll('[data-filter]').forEach(b => b.addEventListener('click', () => { current.category = current.category === b.dataset.filter ? null : b.dataset.filter; renderReport(); }));
  const docText = view.querySelector('#doc-text'), docMargin = view.querySelector('#doc-margin');
  // Desplaza `container` para que `target` quede a `margin` px de su borde superior.
  // Se usan posiciones en pantalla: offsetTop depende del contenedor posicionado y fallaba.
  const scrollWithin = (container, target, margin) => {
    const top = target.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop - margin;
    container.scrollTo({top: Math.max(0, top), behavior: 'smooth'});
  };
  const focusMark = (markId, noteKey) => {
    view.querySelectorAll('.focused').forEach(el => el.classList.remove('focused'));
    // Que el panel del borrador esté a la vista antes de desplazarse dentro de él.
    const layout = view.querySelector('.doc-layout');
    const box = layout.getBoundingClientRect();
    if (box.top < 0 || box.bottom > window.innerHeight) layout.scrollIntoView({behavior: 'smooth', block: 'start'});
    const mark = markId && view.querySelector(`#${CSS.escape(markId)}`);
    if (mark) { scrollWithin(docText, mark, 80); mark.classList.add('focused'); }
    // Un pasaje puede tener varios comentarios: se resaltan todos y se lleva al pulsado (o al primero).
    const cards = markId ? [...view.querySelectorAll(`.margin-note[data-mark="${CSS.escape(markId)}"]`)] : [];
    const card = view.querySelector(`.margin-note[data-key="${CSS.escape(noteKey)}"]`) || cards[0];
    new Set([...cards, card].filter(Boolean)).forEach(el => el.classList.add('focused'));
    if (card) scrollWithin(docMargin, card, 20);
  };
  view.querySelectorAll('.margin-note').forEach(card => card.addEventListener('click', () => focusMark(card.dataset.mark, card.dataset.key)));
  view.querySelectorAll('mark[data-note]').forEach(mark => mark.addEventListener('click', () => focusMark(mark.id, mark.dataset.note)));
  if (current.focus) { const note = notes.find(n => n.key === current.focus); current.focus = null; if (note) requestAnimationFrame(() => focusMark(note.mark, note.key)); }
}

function renderLegacy(r) {
  const findings = (r.findings || []).map(f => `<article class="item por_revisar"><h4>${esc(f.title)}</h4><p>${esc(f.explanation)}</p><p class="evidence">${esc(f.suggestion)}</p></article>`).join('');
  return `<div class="card report"><div class="report-head"><div class="score">${r.maturity_score}<small>/100</small></div><div><p class="eyebrow">Informe de una versión anterior de TFGBoost</p><h2>${esc(r.filename)}</h2><p class="muted">Vuelve a subir el borrador para obtener el informe con la checklist actual.</p></div></div>${findings}</div>`;
}

// --- Historial y seguimiento del análisis en segundo plano ----------------------------
function bindRow(row) {
  bindActions(row);
  if (row.dataset.status === 'processing') poll(row.dataset.rowId, false);
}

function bindActions(row) {
  row.querySelector('[data-report-id]')?.addEventListener('click', event => openReport(event.currentTarget.dataset.reportId));
  row.querySelector('[data-delete-id]')?.addEventListener('click', async event => {
    if (!confirm('¿Borrar esta versión, su informe y el archivo? No se puede deshacer.')) return;
    try { await api(`/api/reports/${encodeURIComponent(event.currentTarget.dataset.deleteId)}`, {method: 'DELETE'}); row.nextElementSibling?.classList.contains('review-row') && row.nextElementSibling.remove(); row.remove(); if (current?.report?.document_id === event.currentTarget.dataset.deleteId) reportNode.hidden = true; }
    catch (error) { alert(error.message); }
  });
}

async function poll(id, openWhenDone) {
  const row = document.querySelector(`tr[data-row-id="${CSS.escape(id)}"]`);
  try {
    const report = await api(`/api/reports/${encodeURIComponent(id)}`);
    const cell = row?.querySelector('.score-cell');
    if (report.status === 'processing') {
      const p = report.progress;
      if (cell) cell.innerHTML = `<span class="muted progress-text">${p && p.total ? `Analizando ${p.done}/${p.total}<br><small>${esc(p.label)}</small>` : esc(p?.label || 'Analizando…')}</span>`;
      setTimeout(() => poll(id, openWhenDone), 3000);
      return;
    }
    if (row) row.dataset.status = report.status;
    if (report.status === 'error') {
      if (cell) cell.innerHTML = `<span class="badge no_cumple" title="${esc(report.error)}">Error</span>`;
      if (openWhenDone) document.querySelector('#status').textContent = report.error;
      return;
    }
    if (cell) cell.innerHTML = `<span class="light ${esc(report.traffic_light)}"></span><strong>${report.maturity_score}/100</strong>`;
    const button = row?.querySelector('[data-report-id]'); if (button) button.disabled = false;
    const actions = row?.querySelector('.actions');
    if (ROLE === 'tutor' && actions && !actions.querySelector('.excel-link')) actions.querySelector('[data-delete-id]')?.insertAdjacentHTML('beforebegin', `<a class="file-link excel-link" href="/api/reports/${encodeURIComponent(id)}/results.xlsx" title="Resultado en Excel">Excel</a>`);
    if (openWhenDone) { document.querySelector('#status').textContent = 'Informe generado.'; openReport(id); }
  } catch (error) { setTimeout(() => poll(id, openWhenDone), 6000); }
}

function addHistoryRow(upload) {
  const body = document.querySelector('.history-card tbody');
  const count = document.querySelector('.history-card .section-heading .muted');
  body.querySelector('.empty-row')?.remove();
  const version = body.querySelectorAll('tr[data-row-id]').length + 1;
  const row = document.createElement('tr');
  row.dataset.rowId = upload.document_id; row.dataset.status = 'processing';
  row.innerHTML = `<td>V${version}</td><td>${esc(upload.filename)}<br><small class="muted">${esc(upload.model.replace('anthropic:', '').replace('ollama:', ''))}</small></td><td>${fmtDate(upload.created_at)}</td><td class="score-cell"><span class="muted progress-text">En cola…</span></td><td><span class="muted">No enviado</span></td><td class="actions"><button class="small" data-report-id="${esc(upload.document_id)}" disabled>Ver informe</button><a class="file-link" href="/api/reports/${encodeURIComponent(upload.document_id)}/document" target="_blank">Archivo</a><button class="link-button danger" data-delete-id="${esc(upload.document_id)}">Borrar</button></td>`;
  body.prepend(row);
  count.textContent = `${version} entrega${version === 1 ? '' : 's'}`;
  bindActions(row);
}

const form = document.querySelector('#upload-form');
if (form) {
  const status = document.querySelector('#status'), fileInput = document.querySelector('#document-input'), dropZone = document.querySelector('#drop-zone'), selected = document.querySelector('#selected-file');
  const modelSelect = document.querySelector('#model-select'), consent = document.querySelector('#remote-consent');
  const syncConsent = () => {
    const option = modelSelect.selectedOptions[0];
    consent.hidden = option?.dataset.remote !== 'true';
    // La prioridad rápido/barato solo se aplica a OpenRouter; si no, ni se muestra ni se envía.
    const routing = document.querySelector('#routing-choice');
    if (routing) { routing.hidden = option?.dataset.provider !== 'OpenRouter'; routing.disabled = routing.hidden; }
    const name = document.querySelector('#remote-provider'); if (name) name.textContent = option?.dataset.provider || 'un proveedor externo';
  };
  modelSelect.addEventListener('change', syncConsent); syncConsent();
  const showSelected = file => { selected.textContent = file ? `Seleccionado: ${file.name}` : ''; };
  fileInput.addEventListener('change', () => showSelected(fileInput.files[0]));
  ['dragenter', 'dragover'].forEach(name => dropZone.addEventListener(name, event => { event.preventDefault(); dropZone.classList.add('drag-active'); }));
  ['dragleave', 'drop'].forEach(name => dropZone.addEventListener(name, event => { event.preventDefault(); dropZone.classList.remove('drag-active'); }));
  dropZone.addEventListener('drop', event => { const file = event.dataTransfer.files[0]; if (!file) return; const transfer = new DataTransfer(); transfer.items.add(file); fileInput.files = transfer.files; showSelected(file); });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true; status.textContent = 'Subiendo y extrayendo el texto…';
    try {
      const upload = await api('/api/documents', {method: 'POST', body: new FormData(form)});
      addHistoryRow(upload);
      status.textContent = 'Analizando el borrador. Con modelos locales puede tardar varios minutos; puedes cerrar la página y consultar el informe más tarde en tu historial.';
      form.reset(); showSelected(null); syncConsent();
      poll(upload.document_id, true);
    } catch (error) { status.textContent = error.message; }
    finally { button.disabled = false; }
  });
}

document.querySelectorAll('tr[data-row-id]').forEach(bindRow);
getChecklist().catch(() => {});
