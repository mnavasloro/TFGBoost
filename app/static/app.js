const reportNode = document.querySelector('#report');
function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char])); }
function renderReport(report) {
  const metrics = Object.entries(report.metrics).map(([name, value]) => `<div class="metric"><span>${escapeHtml(name)}</span><strong>${value}/100</strong></div>`).join('');
  const findings = report.findings.length ? report.findings.map(item => `<article class="finding ${item.severity}"><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.explanation)}</p>${item.location ? `<p class="muted">Ubicación: ${escapeHtml(item.location)}</p>` : ''}<p class="suggestion"><strong>Para revisarlo:</strong> ${escapeHtml(item.suggestion)}</p></article>`).join('') : '<p class="muted">No se han encontrado alertas iniciales. Revisa igualmente la normativa y consulta el borrador con tu tutor.</p>';
  const tutorFeedback = report.tutor_review ? `<section class="revision-check review"><h3>Feedback del tutor</h3><p>${escapeHtml(report.tutor_review.comments)}</p>${report.tutor_review.stored_filename ? `<a class="file-link" href="/api/reports/${encodeURIComponent(report.document_id)}/reviews/latest/document" target="_blank">Abrir documento comentado</a>` : ''}</section>` : '';
  const revisionCheck = report.revision_check ? `<section class="revision-check ${escapeHtml(report.revision_check.status)}"><h3>Comprobación de la revisión anterior</h3><p>${escapeHtml(report.revision_check.message)}</p><p class="muted">Términos nuevos detectados: ${report.revision_check.added_terms}. Evidencias posibles: ${report.revision_check.addressed.length}; sugerencias por revisar: ${report.revision_check.pending.length}.</p></section>` : '';
  const checklist = (report.checklist || []).map(item => `<article class="finding ${escapeHtml(item.status === 'cumple' ? 'info' : item.status === 'por_revisar' ? 'warning' : 'attention')}"><h3>${escapeHtml(item.item)}</h3><p><strong>Estado:</strong> ${escapeHtml(item.status.replace('_', ' '))}</p><p>${escapeHtml(item.evidence)}</p><p class="suggestion"><strong>Para revisarlo:</strong> ${escapeHtml(item.feedback)}</p></article>`).join('');
  reportNode.innerHTML = `<div class="card"><div class="report-head"><div class="score">${report.maturity_score}<small>/100</small></div><div><p class="eyebrow">Diagnóstico inicial</p><h2>${escapeHtml(report.filename)}</h2><p class="muted">${report.word_count.toLocaleString('es-ES')} palabras · ${escapeHtml(report.disclaimer)}</p></div></div><h3>Métricas orientativas</h3><div class="metrics">${metrics}</div><h3>Checklist de estructura</h3><p><strong>Detectadas:</strong> ${report.sections_found.map(escapeHtml).join(', ') || 'ninguna'}<br><strong>Por comprobar:</strong> ${report.sections_missing.map(escapeHtml).join(', ') || 'ninguna'}</p>${checklist ? `<h3>Checklist revisada por Qwen3 8B</h3>${checklist}` : ''}<h3>Recomendaciones</h3>${findings}${tutorFeedback}${revisionCheck}</div>`;
  reportNode.hidden = false; reportNode.scrollIntoView({behavior:'smooth', block:'start'});
}
async function loadReport(button) { const response = await fetch(`/api/reports/${button.dataset.reportId}`); if (response.ok) renderReport(await response.json()); }
function bindReportButton(button) { button.addEventListener('click', () => loadReport(button)); }
function addHistoryRow(report) {
  const historyBody = document.querySelector('.history-card tbody'); const historyCount = document.querySelector('.history-card .section-heading .muted');
  if (!historyBody || !historyCount) return;
  const nextVersion = Array.from(historyBody.rows).filter(row => row.cells.length > 1).length + 1;
  if (nextVersion === 1) historyBody.innerHTML = '';
  const timestamp = new Date(report.created_at).toLocaleString('es-ES', {dateStyle:'short', timeStyle:'short'});
  const row = document.createElement('tr');
  row.innerHTML = `<td>V${nextVersion}</td><td>${escapeHtml(report.filename)}</td><td>${timestamp}</td><td><strong>${report.maturity_score}/100</strong></td><td class="actions"><button class="small" data-report-id="${escapeHtml(report.document_id)}">Ver feedback</button><a class="file-link" href="/api/reports/${encodeURIComponent(report.document_id)}/document" target="_blank">Abrir archivo</a></td>`;
  historyBody.prepend(row); historyCount.textContent = `${nextVersion} entrega${nextVersion === 1 ? '' : 's'}`; bindReportButton(row.querySelector('[data-report-id]'));
}
const form = document.querySelector('#upload-form');
if (form) {
  const status = document.querySelector('#status'); const fileInput = document.querySelector('#document-input'); const dropZone = document.querySelector('#drop-zone'); const selectedFile = document.querySelector('#selected-file');
  const showSelectedFile = file => { selectedFile.textContent = file ? `Seleccionado: ${file.name}` : ''; };
  fileInput.addEventListener('change', () => showSelectedFile(fileInput.files[0]));
  ['dragenter', 'dragover'].forEach(eventName => dropZone.addEventListener(eventName, event => { event.preventDefault(); dropZone.classList.add('drag-active'); }));
  ['dragleave', 'drop'].forEach(eventName => dropZone.addEventListener(eventName, event => { event.preventDefault(); dropZone.classList.remove('drag-active'); }));
  dropZone.addEventListener('drop', event => { const file = event.dataTransfer.files[0]; if (!file) return; const transfer = new DataTransfer(); transfer.items.add(file); fileInput.files = transfer.files; showSelectedFile(file); });
  form.addEventListener('submit', async event => { event.preventDefault(); status.textContent = 'Analizando el borrador…'; const button = form.querySelector('button'); button.disabled = true; try { const response = await fetch('/api/documents', {method:'POST', body:new FormData(form)}); const payload = await response.json(); if (!response.ok) throw new Error(payload.detail || 'No se pudo analizar el documento.'); renderReport(payload); addHistoryRow(payload); status.textContent = 'Informe generado y añadido al historial.'; } catch (error) { status.textContent = error.message; } finally { button.disabled = false; } });
}
document.querySelectorAll('[data-report-id]').forEach(bindReportButton);
