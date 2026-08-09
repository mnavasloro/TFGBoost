const reportNode = document.querySelector('#report');

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
}
function renderReport(report) {
  const metrics = Object.entries(report.metrics).map(([name, value]) => `<div class="metric"><span>${escapeHtml(name)}</span><strong>${value}/100</strong></div>`).join('');
  const findings = report.findings.length ? report.findings.map(item => `<article class="finding ${item.severity}"><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.explanation)}</p>${item.location ? `<p class="muted">Ubicación: ${escapeHtml(item.location)}</p>` : ''}<p class="suggestion"><strong>Para revisarlo:</strong> ${escapeHtml(item.suggestion)}</p></article>`).join('') : '<p class="muted">No se han encontrado alertas iniciales. Revisa igualmente la normativa y consulta el borrador con tu tutor.</p>';
  reportNode.innerHTML = `<div class="card"><div class="report-head"><div class="score">${report.maturity_score}<small>/100</small></div><div><p class="eyebrow">Diagnóstico inicial</p><h2>${escapeHtml(report.filename)}</h2><p class="muted">${report.word_count.toLocaleString('es-ES')} palabras · ${escapeHtml(report.disclaimer)}</p></div></div><h3>Métricas orientativas</h3><div class="metrics">${metrics}</div><h3>Checklist de estructura</h3><p><strong>Detectadas:</strong> ${report.sections_found.map(escapeHtml).join(', ') || 'ninguna'}<br><strong>Por comprobar:</strong> ${report.sections_missing.map(escapeHtml).join(', ') || 'ninguna'}</p><h3>Recomendaciones</h3>${findings}</div>`;
  reportNode.hidden = false; reportNode.scrollIntoView({behavior:'smooth', block:'start'});
}
const form = document.querySelector('#upload-form');
if (form) {
  const status = document.querySelector('#status');
  form.addEventListener('submit', async event => {
    event.preventDefault(); status.textContent = 'Analizando el borrador…';
    const button = form.querySelector('button'); button.disabled = true;
    try { const response = await fetch('/api/documents', {method:'POST', body:new FormData(form)}); const payload = await response.json(); if (!response.ok) throw new Error(payload.detail || 'No se pudo analizar el documento.'); renderReport(payload); status.textContent = 'Informe generado.'; }
    catch (error) { status.textContent = error.message; } finally { button.disabled = false; }
  });
}
document.querySelectorAll('[data-report-id]').forEach(button => button.addEventListener('click', async () => { const response = await fetch(`/api/reports/${button.dataset.reportId}`); if (response.ok) renderReport(await response.json()); }));
