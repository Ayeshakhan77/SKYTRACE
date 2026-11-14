const params = new URLSearchParams(window.location.search);
const API_BASE = (params.get('api') || 'http://127.0.0.1:8765').replace(/\/$/, '');
const $ = (selector) => document.querySelector(selector);

const state = { targets: [], search: null, selected: new Set(), preparing: false };
const connectionPill = $('#connection-pill');
const searchButton = $('#search-button');
const prepareButton = $('#prepare-button');
const resultsPanel = $('#results-panel');
const preparedPanel = $('#prepared-panel');

$('#api-docs-link').href = `${API_BASE}/docs`;

function setError(element, message = '') {
  element.textContent = message;
  element.hidden = !message;
}

function apiErrorText(payload, fallback) {
  const detail = payload?.error?.message || payload?.error?.code || payload?.detail?.message || payload?.detail?.code || payload?.detail;
  return typeof detail === 'string' ? detail : fallback;
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
  });
  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json') ? await response.json() : null;
  if (!response.ok) throw new Error(apiErrorText(payload, `API request failed (${response.status})`));
  return payload;
}

function make(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function formatNumber(value, digits = 7) {
  return Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : 'Not available';
}

function formatMjd(value) {
  return value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value))
    ? `MJD ${Number(value).toFixed(5)}`
    : 'Date not available';
}

function assetUrl(path) {
  return new URL(path, `${API_BASE}/`).toString();
}

async function loadTargets() {
  try {
    const payload = await request('/v1/targets');
    state.targets = Array.isArray(payload?.targets) ? payload.targets : [];
    const select = $('#target-select');
    select.replaceChildren();
    if (!state.targets.length) {
      select.add(new Option('No presets supplied by backend', ''));
      $('#target-count').textContent = 'No curated presets';
    } else {
      state.targets.forEach((target) => select.add(new Option(target.name || target.id, target.id)));
      $('#target-count').textContent = `${state.targets.length} preset${state.targets.length === 1 ? '' : 's'} available`;
      select.value = state.targets[0].id;
      select.dispatchEvent(new Event('change'));
    }
    connectionPill.textContent = 'API connected';
    connectionPill.classList.add('online');
  } catch (error) {
    $('#target-select').replaceChildren(new Option('API presets unavailable · enter coordinates', ''));
    $('#target-count').textContent = 'API unavailable';
    connectionPill.textContent = 'API offline';
    connectionPill.classList.add('offline');
    setError($('#search-error'), `Could not load presets from ${API_BASE}. You can still enter coordinates if the API comes online. ${error.message}`);
  }
}

$('#target-select').addEventListener('change', (event) => {
  const target = state.targets.find((item) => item.id === event.currentTarget.value);
  if (!target) return;
  $('#ra-input').value = target.ra_deg;
  $('#dec-input').value = target.dec_deg;
  $('#preset-note').textContent = target.coordinate_note || 'Fixed sky coordinate. The preset is not a confirmed object detection.';
});

function renderResults() {
  const list = $('#results-list');
  list.replaceChildren();
  const observations = state.search?.observations || [];
  $('#result-count').textContent = `${observations.length}${state.search?.truncated ? '+' : ''} returned${state.search?.total_rows != null ? ` · ${state.search.total_rows} total` : ''}`;
  if (!observations.length) {
    const empty = make('div', 'empty-state', 'No archive records overlapped this fixed search position. Try the other collection or a slightly larger radius.');
    list.append(empty);
  }
  observations.forEach((observation) => {
    const label = make('label', 'result-card');
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.value = observation.observation_id;
    checkbox.checked = state.selected.has(observation.observation_id);
    checkbox.setAttribute('aria-label', `Select product ${observation.source_product_id || observation.observation_id}`);
    checkbox.addEventListener('change', () => {
      if (checkbox.checked) {
        if (state.selected.size >= 2) {
          checkbox.checked = false;
          return;
        }
        state.selected.add(observation.observation_id);
      } else {
        state.selected.delete(observation.observation_id);
      }
      updateSelection();
    });
    const detail = make('div');
    const productId = make('div', 'product-id', observation.source_product_id || observation.observation_id);
    const localDate = [formatMjd(observation.mjd_start), formatMjd(observation.mjd_end)].filter((value, index) => index === 0 || value !== 'Date not available').join(' – ');
    const coverage = [observation.wavelength_min_m, observation.wavelength_max_m].every((value) => value != null)
      ? `${formatNumber(observation.wavelength_min_m * 1e6, 3)}–${formatNumber(observation.wavelength_max_m * 1e6, 3)} µm product coverage`
      : 'Product wavelength bounds unavailable';
    const meta = make('div', 'result-meta', `${localDate} · ${coverage} · broad coverage only`);
    detail.append(productId, meta);
    const tag = make('span', 'collection-tag', observation.collection || 'SPHEREx');
    label.append(checkbox, detail, tag);
    list.append(label);
  });
  resultsPanel.hidden = false;
  updateSelection();
}

function updateSelection() {
  $('#selection-count').textContent = `${state.selected.size} of 2 selected`;
  prepareButton.disabled = state.selected.size === 0 || state.preparing;
}

$('#search-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  setError($('#search-error'));
  setError($('#prepare-error'));
  state.search = null;
  state.selected.clear();
  resultsPanel.hidden = true;
  preparedPanel.hidden = true;
  searchButton.disabled = true;
  searchButton.textContent = 'Searching…';
  try {
    const body = {
      ra_deg: Number($('#ra-input').value),
      dec_deg: Number($('#dec-input').value),
      radius_deg: Number($('#radius-input').value),
      collection: $('#collection-select').value,
      limit: 500,
    };
    state.search = await request('/v1/searches', { method: 'POST', body: JSON.stringify(body) });
    renderResults();
    resultsPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) {
    setError($('#search-error'), error.message);
  } finally {
    searchButton.disabled = false;
    searchButton.textContent = 'Search archive ↗';
  }
});

function addMeta(container, label, value) {
  const item = make('div', 'meta-item');
  item.append(make('span', 'meta-label', label), make('div', 'meta-value', value ?? 'Not available'));
  container.append(item);
}

function renderPrepared(records) {
  const list = $('#prepared-list');
  list.replaceChildren();
  records.forEach((record) => {
    const card = make('article', 'prepared-card');
    const image = document.createElement('img');
    image.className = 'prepared-image';
    image.src = assetUrl(record.assets.preview_png_url);
    image.alt = `Display preview for SPHEREx product ${record.source.source_product_id || record.source.observation_id}; not registered for scientific comparison`;
    image.loading = 'lazy';
    const info = make('div', 'prepared-info');
    info.append(make('h3', 'prepared-title', record.source.source_product_id || record.cutout_id));
    const metadata = make('div', 'prepared-meta');
    addMeta(metadata, 'Observation time · UTC', record.inspection.observation_time.date_obs || 'Not in FITS header');
    addMeta(metadata, 'Local wavelength · µm', record.inspection.wavelength.target_center_um == null ? 'Not available' : formatNumber(record.inspection.wavelength.target_center_um, 6));
    addMeta(metadata, 'Image size', `${record.inspection.image.width} × ${record.inspection.image.height} ${record.inspection.image.unit || ''}`.trim());
    addMeta(metadata, 'Quality review', record.inspection.quality.status || 'Not assessed');
    addMeta(metadata, 'WCS at query position', record.inspection.spatial.query_position_within_cutout == null ? 'Not available' : record.inspection.spatial.query_position_within_cutout ? 'Inside cutout' : 'Outside cutout');
    addMeta(metadata, 'Comparison', record.comparison_status || 'Not assessed');
    const links = make('div', 'asset-links');
    const previewLink = make('a', '', 'Open preview');
    previewLink.href = assetUrl(record.assets.preview_png_url);
    previewLink.target = '_blank';
    previewLink.rel = 'noreferrer';
    const fitsLink = make('a', '', 'Original FITS');
    fitsLink.href = assetUrl(record.assets.original_fits_url);
    fitsLink.target = '_blank';
    fitsLink.rel = 'noreferrer';
    const sourceLink = make('a', '', 'IRSA source product');
    sourceLink.href = record.source.source_url;
    sourceLink.target = '_blank';
    sourceLink.rel = 'noreferrer';
    links.append(previewLink, fitsLink, sourceLink);
    info.append(metadata, links);
    const warnings = Array.isArray(record.inspection.warnings) ? record.inspection.warnings : [];
    if (warnings.length) {
      const warningList = make('ul', 'warning-list');
      warnings.forEach((warning) => warningList.append(make('li', '', warning)));
      info.append(warningList);
    }
    card.append(image, info);
    list.append(card);
  });
  $('#comparison-state').textContent = records.every((record) => record.comparison_status === 'not_assessed') ? 'Comparison not assessed' : 'Review required';
  preparedPanel.hidden = false;
  preparedPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

prepareButton.addEventListener('click', async () => {
  if (!state.search?.search_id || state.selected.size === 0) return;
  setError($('#prepare-error'));
  state.preparing = true;
  updateSelection();
  prepareButton.textContent = 'Preparing…';
  try {
    const records = await request(`/v1/searches/${encodeURIComponent(state.search.search_id)}/cutouts`, {
      method: 'POST',
      body: JSON.stringify({ observation_ids: [...state.selected], size_deg: 0.03 }),
    });
    renderPrepared(records);
  } catch (error) {
    setError($('#prepare-error'), error.message);
  } finally {
    state.preparing = false;
    prepareButton.textContent = 'Prepare selected cutout(s)';
    updateSelection();
  }
});

loadTargets();
