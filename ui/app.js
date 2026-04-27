/* ============================================================
   RAKSH — Client Logic
   Talks to the ingestion API. No framework. No build step.
   ============================================================ */

const API = window.location.hostname === 'localhost'
  ? 'http://localhost:8001'
  : window.location.origin;

const API_KEY = 'local-dev-key-change-in-prod';

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ---- State ----

let currentExtractions = [];
let currentIngestId = null;
let currentStoragePath = null;
let currentDocType = null;
let currentContentHash = null;
let currentMemberId = 'demo-member-001';

// ---- Init ----

document.addEventListener('DOMContentLoaded', () => {
  checkHealth();
  setupDropZone();
  setupButtons();
});

// ---- Health Check ----

async function checkHealth() {
  const dot = $('#status-dot');
  const text = $('#status-text');

  try {
    const res = await fetch(`${API}/health`);
    const data = await res.json();

    if (data.status === 'healthy') {
      dot.className = 'status-dot connected';
      text.textContent = 'connected';
    } else {
      dot.className = 'status-dot degraded';
      text.textContent = data.status;
    }
  } catch {
    dot.className = 'status-dot';
    text.textContent = 'offline';
  }
}

// ---- Drop Zone ----

function setupDropZone() {
  const zone = $('#drop-zone');
  const input = $('#file-input');

  zone.addEventListener('click', () => input.click());
  zone.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      input.click();
    }
  });

  input.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      handleFile(e.target.files[0]);
    }
  });

  zone.addEventListener('dragover', (e) => {
    e.preventDefault();
    zone.classList.add('drag-over');
  });

  zone.addEventListener('dragleave', () => {
    zone.classList.remove('drag-over');
  });

  zone.addEventListener('drop', (e) => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    if (e.dataTransfer.files.length > 0) {
      handleFile(e.dataTransfer.files[0]);
    }
  });
}

// ---- File Upload ----

async function handleFile(file) {
  const progress = $('#upload-progress');
  const fill = $('#progress-fill');
  const text = $('#progress-text');

  progress.classList.remove('hidden');
  fill.style.width = '0%';
  text.textContent = 'Uploading...';

  // Simulate progress during upload
  let pct = 0;
  const progressInterval = setInterval(() => {
    pct = Math.min(pct + Math.random() * 15, 85);
    fill.style.width = pct + '%';
  }, 200);

  const formData = new FormData();
  formData.append('file', file);
  formData.append('member_id', currentMemberId);

  try {
    const res = await fetch(`${API}/ingest/upload`, {
      method: 'POST',
      headers: { 'x-api-key': API_KEY },
      body: formData,
    });

    clearInterval(progressInterval);

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      fill.style.width = '100%';
      text.textContent = `Error: ${err.detail || err.error || 'Upload failed'}`;
      return;
    }

    fill.style.width = '100%';
    text.textContent = 'Extracting...';

    const data = await res.json();

    currentExtractions = data.extractions || [];
    currentIngestId = data.ingest_id;
    currentStoragePath = data.storage_path;
    currentDocType = data.doc_type;
    currentContentHash = data.content_hash;

    text.textContent = `Done — ${currentExtractions.length} fields extracted`;

    setTimeout(() => {
      showResults(data);
    }, 400);

  } catch (err) {
    clearInterval(progressInterval);
    fill.style.width = '100%';
    text.textContent = `Network error: ${err.message}`;
  }
}

// ---- Results Display ----

function showResults(data) {
  const section = $('#section-results');
  const body = $('#results-body');
  const docType = $('#result-doc-type');
  const count = $('#result-count');

  section.classList.remove('hidden');

  docType.textContent = formatDocType(data.doc_type);
  count.textContent = `${data.extractions.length} fields`;

  body.innerHTML = '';

  data.extractions.forEach((ext, i) => {
    const tr = document.createElement('tr');

    const conf = ext.confidence || 0;
    const confPct = Math.round(conf * 100);
    const flagClass = ext.flag || 'normal';

    tr.innerHTML = `
      <td>${escapeHtml(ext.name || 'unknown')}</td>
      <td>${ext.requires_manual_entry
        ? `<span class="manual-tag">needs review</span>`
        : escapeHtml(String(ext.value ?? '—'))
      }</td>
      <td>${escapeHtml(ext.unit || '—')}</td>
      <td>
        <span class="confidence-bar"><span class="confidence-fill" style="width:${confPct}%"></span></span>
        ${confPct}%
      </td>
      <td><span class="flag-dot ${flagClass}" title="${flagClass}"></span></td>
    `;

    body.appendChild(tr);
  });

  section.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ---- Confirm / Discard ----

function setupButtons() {
  $('#btn-confirm').addEventListener('click', handleConfirm);
  $('#btn-discard').addEventListener('click', handleDiscard);
  $('#btn-refresh-docs').addEventListener('click', loadDocuments);
  $('#btn-close-trend').addEventListener('click', () => {
    $('#section-trend').classList.add('hidden');
  });
}

async function handleConfirm() {
  const btn = $('#btn-confirm');
  const errorBox = $('#confirm-error');
  const successBox = $('#confirm-success');
  const fastingStatus = $('#fasting-select').value;

  errorBox.classList.add('hidden');
  successBox.classList.add('hidden');

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Saving...';

  const parameters = currentExtractions.map((ext) => ({
    parameter_name: ext.name || 'unknown',
    value: ext.value,
    value_numeric: ext.value_numeric ?? null,
    unit: ext.unit || null,
    flag: ext.flag || null,
    confidence: ext.confidence || 0,
    requires_manual_entry: ext.requires_manual_entry || false,
    fasting_status: fastingStatus,
  }));

  const payload = {
    ingest_id: currentIngestId,
    member_id: currentMemberId,
    storage_path: currentStoragePath,
    doc_type: currentDocType,
    content_hash: currentContentHash,
    ingest_channel: 'upload',
    parameters,
  };

  try {
    const res = await fetch(`${API}/ingest/confirm`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': API_KEY,
      },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));

      if (err.detail?.error === 'fasting_status_required') {
        errorBox.textContent = `Fasting status required for: ${err.detail.affected_parameters.join(', ')}`;
      } else {
        errorBox.textContent = err.detail?.message || err.detail || 'Confirmation failed';
      }
      errorBox.classList.remove('hidden');
      btn.disabled = false;
      btn.textContent = 'Confirm & Save';
      return;
    }

    const data = await res.json();

    successBox.textContent = `Saved — ${data.parameters_saved} parameters confirmed`;
    successBox.classList.remove('hidden');

    btn.textContent = 'Confirmed';

    setTimeout(() => {
      resetUpload();
      loadDocuments();
    }, 1500);

  } catch (err) {
    errorBox.textContent = `Network error: ${err.message}`;
    errorBox.classList.remove('hidden');
    btn.disabled = false;
    btn.textContent = 'Confirm & Save';
  }
}

function handleDiscard() {
  resetUpload();
}

function resetUpload() {
  currentExtractions = [];
  currentIngestId = null;
  currentStoragePath = null;
  currentDocType = null;
  currentContentHash = null;

  $('#section-results').classList.add('hidden');
  $('#upload-progress').classList.add('hidden');
  $('#confirm-error').classList.add('hidden');
  $('#confirm-success').classList.add('hidden');
  $('#file-input').value = '';
  $('#btn-confirm').disabled = false;
  $('#btn-confirm').textContent = 'Confirm & Save';
  $('#progress-fill').style.width = '0%';
}

// ---- Documents List ----

async function loadDocuments() {
  const list = $('#docs-list');
  const empty = $('#docs-empty');

  try {
    const res = await fetch(
      `${API}/documents?member_id=${currentMemberId}&page=1&page_size=20`,
      { headers: { 'x-api-key': API_KEY } }
    );

    if (!res.ok) {
      list.classList.add('hidden');
      empty.classList.remove('hidden');
      empty.querySelector('p').textContent = 'Could not load documents.';
      return;
    }

    const data = await res.json();

    if (!data.documents || data.documents.length === 0) {
      list.classList.add('hidden');
      empty.classList.remove('hidden');
      empty.querySelector('p').textContent = 'No confirmed documents yet.';
      return;
    }

    empty.classList.add('hidden');
    list.classList.remove('hidden');
    list.innerHTML = '';

    data.documents.forEach((doc) => {
      const card = document.createElement('div');
      card.className = 'doc-card';
      card.innerHTML = `
        <div class="doc-card-left">
          <span class="doc-card-type">${formatDocType(doc.doc_type)}</span>
          <span class="doc-card-date">${formatDate(doc.test_date || doc.created_at)}</span>
        </div>
        <div class="doc-card-right">
          <span class="doc-card-params">${doc.parameters_count || '—'} params</span>
          <span class="doc-card-arrow">→</span>
        </div>
      `;
      card.addEventListener('click', () => viewDocument(doc.id));
      list.appendChild(card);
    });

  } catch {
    list.classList.add('hidden');
    empty.classList.remove('hidden');
    empty.querySelector('p').textContent = 'Could not connect to server.';
  }
}

async function viewDocument(docId) {
  try {
    const res = await fetch(`${API}/documents/${docId}/parameters`, {
      headers: { 'x-api-key': API_KEY },
    });
    if (!res.ok) return;

    const params = await res.json();
    if (!params.length) return;

    // Show trend for first parameter
    showTrend(params[0].parameter_name);

  } catch {
    // silent
  }
}

// ---- Trend Chart ---- 

async function showTrend(parameterName) {
  const section = $('#section-trend');
  const title = $('#trend-title');
  const canvas = $('#trend-canvas');
  const legend = $('#trend-legend');

  title.textContent = formatParamName(parameterName);
  section.classList.remove('hidden');
  section.scrollIntoView({ behavior: 'smooth', block: 'start' });

  try {
    const res = await fetch(
      `${API}/parameters/trend?member_id=${currentMemberId}&parameter_name=${encodeURIComponent(parameterName)}&limit=50`,
      { headers: { 'x-api-key': API_KEY } }
    );

    if (!res.ok) return;

    const data = await res.json();
    drawTrend(canvas, data);

    legend.innerHTML = `
      <div class="trend-legend-item">
        <span class="trend-legend-dot" style="background:#111"></span>
        <span>Value</span>
      </div>
      <div class="trend-legend-item">
        <span class="trend-legend-dot" style="background:#ccc"></span>
        <span>Normal range</span>
      </div>
    `;

  } catch {
    // silent
  }
}

function drawTrend(canvas, data) {
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();

  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);

  const w = rect.width;
  const h = rect.height;
  const pad = { top: 24, right: 20, bottom: 32, left: 48 };
  const plotW = w - pad.left - pad.right;
  const plotH = h - pad.top - pad.bottom;

  ctx.clearRect(0, 0, w, h);

  const points = data.data_points || [];
  if (points.length === 0) {
    ctx.fillStyle = '#999';
    ctx.font = '13px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('No trend data available', w / 2, h / 2);
    return;
  }

  const values = points.map((p) => p.value_numeric).filter(Boolean);
  const rangeLow = data.reference_range?.low ?? Math.min(...values) * 0.8;
  const rangeHigh = data.reference_range?.high ?? Math.max(...values) * 1.2;

  const allY = [...values, rangeLow, rangeHigh];
  const yMin = Math.min(...allY) * 0.9;
  const yMax = Math.max(...allY) * 1.1;

  const xScale = (i) => pad.left + (i / Math.max(points.length - 1, 1)) * plotW;
  const yScale = (v) => pad.top + plotH - ((v - yMin) / (yMax - yMin)) * plotH;

  // Normal range band
  const bandTop = yScale(rangeHigh);
  const bandBottom = yScale(rangeLow);
  ctx.fillStyle = 'rgba(0,0,0,0.03)';
  ctx.fillRect(pad.left, bandTop, plotW, bandBottom - bandTop);

  // Range lines
  ctx.strokeStyle = '#e0e0e0';
  ctx.lineWidth = 1;
  ctx.setLineDash([4, 4]);
  [rangeLow, rangeHigh].forEach((v) => {
    const y = yScale(v);
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(pad.left + plotW, y);
    ctx.stroke();
  });
  ctx.setLineDash([]);

  // Data line
  ctx.strokeStyle = '#111';
  ctx.lineWidth = 1.5;
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  ctx.beginPath();
  points.forEach((p, i) => {
    if (p.value_numeric == null) return;
    const x = xScale(i);
    const y = yScale(p.value_numeric);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Data dots
  points.forEach((p, i) => {
    if (p.value_numeric == null) return;
    const x = xScale(i);
    const y = yScale(p.value_numeric);
    ctx.fillStyle = '#111';
    ctx.beginPath();
    ctx.arc(x, y, 3, 0, Math.PI * 2);
    ctx.fill();
  });

  // Y-axis labels
  ctx.fillStyle = '#999';
  ctx.font = '10px Inter, sans-serif';
  ctx.textAlign = 'right';
  const yTicks = 5;
  for (let i = 0; i <= yTicks; i++) {
    const v = yMin + (i / yTicks) * (yMax - yMin);
    const y = yScale(v);
    ctx.fillText(v.toFixed(1), pad.left - 6, y + 3);
  }

  // X-axis labels (first and last date)
  ctx.textAlign = 'center';
  ctx.fillStyle = '#999';
  if (points.length > 0) {
    ctx.fillText(formatDateShort(points[0].test_date), xScale(0), h - 8);
    if (points.length > 1) {
      ctx.fillText(formatDateShort(points[points.length - 1].test_date), xScale(points.length - 1), h - 8);
    }
  }
}

// ---- Utilities ----

function formatDocType(type) {
  if (!type) return 'Unknown';
  return type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatParamName(name) {
  if (!name) return 'Unknown';
  return name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatDate(dateStr) {
  if (!dateStr) return '—';
  try {
    return new Date(dateStr).toLocaleDateString('en-IN', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return dateStr;
  }
}

function formatDateShort(dateStr) {
  if (!dateStr) return '';
  try {
    return new Date(dateStr).toLocaleDateString('en-IN', {
      day: 'numeric',
      month: 'short',
    });
  } catch {
    return '';
  }
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
