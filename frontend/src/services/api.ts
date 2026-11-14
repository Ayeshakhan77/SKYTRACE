import { NormalizedObservation, ValidationStatus } from '../types/observation';
import { WISE_0855_FIXTURE_RECORDS, FIXTURE_PREVIEW_PATH } from '../data/fixtures';

/**
 * Adapter for the SKYTRACE FastAPI backend (backend/openapi.json, schema_version 0.1).
 *
 *   GET  /v1/targets
 *   POST /v1/searches                        { ra_deg, dec_deg, radius_deg, collection, limit }
 *   GET  /v1/searches/{search_id}
 *   POST /v1/searches/{search_id}/cutouts    { observation_ids: [1..2], size_deg }
 *   GET  /v1/cutouts/{cutout_id}
 *   GET  /v1/cutouts/{cutout_id}/preview.png | source.fits
 *
 * Backend limits: radius_deg <= 0.05, limit <= 500, size_deg <= 0.1, 2 cutouts per request,
 * one archive operation at a time (429 archive_busy).
 */

// Backend README runs uvicorn on 8765. Override with VITE_API_BASE_URL.
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') || 'http://127.0.0.1:8765';

export const DEFAULT_COLLECTION = 'spherex_qr2';
export const MAX_RADIUS_DEG = 0.05;
export const DEFAULT_CUTOUT_SIZE_DEG = 0.03;

export interface SearchResponse {
  searchId: string;
  observations: NormalizedObservation[];
  truncated: boolean;
  totalRows?: number;
  queryUrl?: string;
  queriedAtUtc?: string;
  interpretation?: string;
  isOfflineMock: boolean;
}

/** Error carrying the backend's machine-readable code so the UI can tell
 *  "archive down, retry" apart from "your input is invalid". */
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
    public retryable = false
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

const ERROR_MESSAGES: Record<string, string> = {
  archive_unavailable: 'The NASA/IPAC archive (IRSA) could not be reached. Try again shortly.',
  archive_timeout: 'The NASA/IPAC archive (IRSA) timed out. Try again shortly.',
  archive_busy: 'Another archive request is already running. Wait a moment and retry.',
  not_found: 'That search or cutout no longer exists on the server.',
  observation_not_in_search: 'This observation belongs to a different search. Re-run the search.',
  duplicate_observation: 'The same observation was selected twice.',
  cache_budget: 'The server cache is full. Ask the backend owner to clear it.',
  search_budget: 'The server cache is full. Ask the backend owner to clear it.',
  cutout_budget: 'The server cache is full. Ask the backend owner to clear it.',
  unsupported_fits: 'The archive product could not be read as a supported FITS file.',
};

/** Handles both `{error:{code,message,retryable}}` (archive 502s) and
 *  FastAPI `{detail: string | {code,message} | ValidationError[]}`. */
async function toApiError(response: Response, fallback: string): Promise<ApiError> {
  const body: any = await response.json().catch(() => ({}));
  const err = body?.error;
  if (err && typeof err === 'object') {
    return new ApiError(
      ERROR_MESSAGES[err.code] || err.message || fallback,
      response.status,
      err.code,
      Boolean(err.retryable)
    );
  }
  const detail = body?.detail;
  if (typeof detail === 'string') return new ApiError(detail, response.status);
  if (Array.isArray(detail)) {
    const msg = detail.map((d: any) => `${(d.loc || []).slice(1).join('.')}: ${d.msg}`).join('; ');
    return new ApiError(`Invalid request — ${msg}`, response.status, 'validation_error');
  }
  if (detail && typeof detail === 'object') {
    return new ApiError(
      ERROR_MESSAGES[detail.code] || detail.message || fallback,
      response.status,
      detail.code,
      response.status === 429
    );
  }
  return new ApiError(`${fallback} (HTTP ${response.status})`, response.status);
}

async function request(path: string, init: RequestInit | undefined, fallback: string) {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw new ApiError(
      `Cannot reach the SKYTRACE backend at ${API_BASE_URL}. Is it running? (Offline Fixture Mode still works.)`,
      0,
      'backend_unreachable',
      true
    );
  }
  if (!response.ok) throw await toApiError(response, fallback);
  return response.json();
}

/** Resolves relative asset paths (/v1/cutouts/...) against the API base URL. */
export function resolveAssetUrl(path?: string | null): string | undefined {
  if (!path) return undefined;
  if (/^https?:\/\//.test(path)) return path;
  return `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`;
}

// ---------- coordinate + unit helpers ----------

/** Accepts decimal degrees ("133.795") or sexagesimal ("08h 55m 10.8s", "08:55:10.8"). */
export function parseRa(input: string): number {
  const s = input.trim();
  if (/^[+-]?\d+(\.\d+)?$/.test(s)) return validateRange(Number(s), 0, 360, 'RA');
  const parts = s.match(/[\d.]+/g)?.map(Number);
  if (!parts || parts.length < 1 || parts.length > 3) throw new ApiError(`Unrecognised RA "${input}"`, 0, 'invalid_input');
  const [h, m = 0, sec = 0] = parts;
  return validateRange((h + m / 60 + sec / 3600) * 15, 0, 360, 'RA');
}

export function parseDec(input: string): number {
  const s = input.trim();
  if (/^[+-]?\d+(\.\d+)?$/.test(s)) return validateRange(Number(s), -90, 90, 'Dec');
  const sign = /^\s*[-−–]/.test(s) ? -1 : 1;
  const parts = s.match(/[\d.]+/g)?.map(Number);
  if (!parts || parts.length < 1 || parts.length > 3) throw new ApiError(`Unrecognised Dec "${input}"`, 0, 'invalid_input');
  const [d, m = 0, sec = 0] = parts;
  return validateRange(sign * (d + m / 60 + sec / 3600), -90, 90, 'Dec');
}

function validateRange(v: number, lo: number, hi: number, label: string): number {
  if (!Number.isFinite(v) || v < lo || v > hi) {
    throw new ApiError(`${label} must be between ${lo} and ${hi} degrees`, 0, 'invalid_input');
  }
  return v;
}

/** Modified Julian Date -> ISO 8601 UTC string. */
export function mjdToIso(mjd?: number): string | undefined {
  if (typeof mjd !== 'number' || !Number.isFinite(mjd)) return undefined;
  return new Date((mjd - 40587) * 86_400_000).toISOString();
}

/** Backend header times are UTC but carry no "Z"; without it, Date() parses
 *  them as the viewer's local time and shifts every date. */
function utcIso(value?: string, timeSystem?: string): string | undefined {
  if (!value) return undefined;
  if (/[zZ]|[+-]\d\d:?\d\d$/.test(value)) return value;
  return !timeSystem || timeSystem.toUpperCase() === 'UTC' ? `${value}Z` : value;
}

const mToUm = (m?: number) => (typeof m === 'number' ? m * 1e6 : undefined);
const round = (v: number | undefined, dp = 4) =>
  typeof v === 'number' ? Number(v.toFixed(dp)) : undefined;

function detectorFrom(source: any): string | undefined {
  const band: string | undefined = source?.bandpass_name || source?.metadata?.energy_bandpassname;
  const m = band?.match(/D(\d)/);
  if (m) return `D${m[1]}`;
  return source?.source_product_id?.match(/\/(D\d)$/)?.[1];
}

const asStatus = (v: any): ValidationStatus =>
  ['not_assessed', 'pending', 'passed', 'failed', 'not_applicable'].includes(v) ? v : 'not_assessed';

// ---------- normalizers ----------

/** ArchiveObservation (a row from POST/GET /v1/searches). */
export function normalizeSearchRow(row: any, searchId: string): NormalizedObservation {
  const md = row.metadata || {};
  const min = mToUm(row.wavelength_min_m ?? md.em_min);
  const max = mToUm(row.wavelength_max_m ?? md.em_max);
  return {
    backendSelectionKey: row.observation_id,
    archiveObservationId: md.obs_id,
    sourceProductId: row.source_product_id,
    searchId,
    observationTime: mjdToIso(row.mjd_start),
    // Search rows have no per-pixel wavelength; don't present the band range as one.
    wavelength: undefined,
    wavelengthBasis: 'unavailable',
    wavelengthRangeUm: min !== undefined && max !== undefined ? { min: round(min)!, max: round(max)! } : undefined,
    bandwidth: undefined,
    detector: detectorFrom(row),
    processingVersion: null, // no dedicated field yet; never parse from URL
    previewUrl: undefined,
    fitsUrl: undefined,
    previewStatus: 'unavailable',
    fitsStatus: 'unavailable',
    provenance: { sourceUrl: row.source_url, collection: row.collection },
    qualityStatus: 'not_assessed',
  };
}

/** PreparedObservation (from POST /v1/searches/{id}/cutouts or GET /v1/cutouts/{id}). */
export function normalizePrepared(p: any): NormalizedObservation {
  const src = p.source || {};
  const insp = p.inspection || {};
  const wl = insp.wavelength || {};
  const t = insp.observation_time || {};
  const assets = p.assets || {};
  const preview = resolveAssetUrl(assets.preview_png_url);
  const fits = resolveAssetUrl(assets.original_fits_url);
  const base = normalizeSearchRow(src, p.search_id);
  const hasWcsWave = typeof wl.target_center_um === 'number';

  return {
    ...base,
    cutoutId: p.cutout_id,
    observationTime: utcIso(t.date_obs, t.time_system) ?? base.observationTime,
    wavelength: hasWcsWave ? round(wl.target_center_um) : undefined,
    bandwidth: typeof wl.target_bandwidth_um === 'number' ? round(wl.target_bandwidth_um) : undefined,
    wavelengthBasis: hasWcsWave ? 'spectral_wcs_at_query_position' : 'unavailable',
    previewUrl: preview,
    fitsUrl: fits,
    previewStatus: preview ? 'available' : 'unavailable',
    fitsStatus: fits ? 'available' : 'unavailable',
    provenance: {
      sourceUrl: src.source_url,
      collection: src.collection,
      checksum: assets.sha256 || p.retrieval?.sha256,
    },
    qualityStatus: asStatus(insp.quality?.status),
    nonzeroFlagFraction: insp.quality?.nonzero_flag_fraction,
    queryPositionInCutout: insp.spatial?.query_position_within_cutout,
    alignmentStatus: asStatus(insp.spatial?.alignment_status),
    comparisonStatus: asStatus(p.comparison_status),
    displayMode: insp.display?.mode,
    brightnessComparisonValidated: Boolean(insp.display?.brightness_comparison_validated),
    imageSize: insp.image ? { width: insp.image.width, height: insp.image.height, unit: insp.image.unit } : undefined,
    warnings: insp.warnings || [],
    limitations: p.limitations || [],
  };
}

/** The two real cached cutouts, normalized exactly like live responses, but with
 *  previews served by the frontend and FITS marked unavailable (no backend). */
function offlineFixture(): NormalizedObservation[] {
  return WISE_0855_FIXTURE_RECORDS.map((rec) => {
    const obs = normalizePrepared(rec);
    return {
      ...obs,
      previewUrl: FIXTURE_PREVIEW_PATH(rec.cutout_id),
      previewStatus: 'available' as const,
      fitsUrl: undefined,
      fitsStatus: 'unavailable' as const,
    };
  });
}

// ---------- API calls ----------

export async function searchObservations(params: {
  targetName: string;
  ra: string;
  dec: string;
  radiusDeg: number;
  collection?: string;
  useOfflineFallback?: boolean;
}): Promise<SearchResponse> {
  if (params.useOfflineFallback) {
    await new Promise((r) => setTimeout(r, 400));
    return {
      searchId: 'ae25b7204ad740579de50a6da78d0755',
      observations: offlineFixture(),
      truncated: false,
      isOfflineMock: true,
    };
  }

  const body = {
    ra_deg: parseRa(params.ra),
    dec_deg: parseDec(params.dec),
    radius_deg: Math.min(params.radiusDeg, MAX_RADIUS_DEG),
    collection: params.collection || DEFAULT_COLLECTION,
    limit: 500,
  };
  const data = await request(
    '/v1/searches',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) },
    'Archive search failed'
  );
  return searchRecordToResponse(data);
}

/** Re-open a saved search (works without archive access if it's in the server cache). */
export async function getSearch(searchId: string): Promise<SearchResponse> {
  return searchRecordToResponse(await request(`/v1/searches/${searchId}`, undefined, 'Could not load search'));
}

function searchRecordToResponse(data: any): SearchResponse {
  const rows: any[] = Array.isArray(data.observations) ? data.observations : [];
  return {
    searchId: data.search_id,
    observations: rows.map((r) => normalizeSearchRow(r, data.search_id)),
    truncated: Boolean(data.truncated),
    totalRows: data.total_rows,
    queryUrl: data.query_url,
    queriedAtUtc: data.queried_at_utc,
    interpretation: data.interpretation,
    isOfflineMock: false,
  };
}

/** Prepares 1–2 observations. Observations from different searches are sent as
 *  separate requests under their own search_id, then returned in input order. */
export async function prepareObservations(
  selected: NormalizedObservation[],
  isOfflineMock: boolean,
  sizeDeg = DEFAULT_CUTOUT_SIZE_DEG
): Promise<NormalizedObservation[]> {
  if (selected.length === 0 || selected.length > 2) {
    throw new ApiError('Select 1 or 2 observations to prepare.', 0, 'invalid_input');
  }
  if (isOfflineMock) {
    await new Promise((r) => setTimeout(r, 500));
    return selected;
  }

  const bySearch = new Map<string, NormalizedObservation[]>();
  for (const obs of selected) {
    if (!obs.searchId) throw new ApiError('Observation is missing its search ID. Re-run the search.', 0, 'invalid_input');
    bySearch.set(obs.searchId, [...(bySearch.get(obs.searchId) || []), obs]);
  }

  const prepared: NormalizedObservation[] = [];
  // Sequential on purpose: the backend allows one archive operation at a time.
  for (const [searchId, group] of bySearch) {
    const data = await request(
      `/v1/searches/${searchId}/cutouts`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ observation_ids: group.map((o) => o.backendSelectionKey), size_deg: sizeDeg }),
      },
      'Observation preparation failed'
    );
    (Array.isArray(data) ? data : []).forEach((p: any) => prepared.push(normalizePrepared(p)));
  }

  const order = selected.map((s) => s.backendSelectionKey);
  return prepared.sort((a, b) => order.indexOf(a.backendSelectionKey) - order.indexOf(b.backendSelectionKey));
}

export async function getCutout(cutoutId: string): Promise<NormalizedObservation> {
  return normalizePrepared(await request(`/v1/cutouts/${cutoutId}`, undefined, 'Could not load cutout'));
}
