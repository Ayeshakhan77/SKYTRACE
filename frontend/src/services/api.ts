import { NormalizedObservation } from '../types/observation';
import { WISE_0855_FIXTURE } from '../data/fixtures';

// Reads from .env if configured, otherwise defaults to local FastAPI port
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') || 'http://127.0.0.1:8000';

export interface SearchResponse {
  searchId: string;
  observations: NormalizedObservation[];
  truncated: boolean;
  isOfflineMock: boolean;
}

/**
 * Resolves relative asset paths (/assets/...) against the configured API base URL.
 * Leaves full external URLs (http/https) untouched.
 */
export function resolveAssetUrl(path?: string | null): string | undefined {
  if (!path) return undefined;
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path;
  }
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${cleanPath}`;
}

/**
 * Normalizes raw backend JSON objects into the strict frontend Observation contract.
 */
export function normalizeObservation(
  raw: any,
  searchId?: string
): NormalizedObservation {
  const source = raw.source || raw;
  const metadata = source.metadata || raw.metadata || {};

  const resolvedPreview = resolveAssetUrl(raw.preview_url || raw.previewUrl);
  const resolvedFits = resolveAssetUrl(raw.fits_url || raw.fitsUrl);

  return {
    backendSelectionKey:
      source.observation_id || raw.backendSelectionKey || 'unknown_key',
    archiveObservationId:
      metadata.obs_id || raw.archiveObservationId || undefined,
    sourceProductId:
      source.product_id || raw.sourceProductId || metadata.product_id || 'unknown_product',
    searchId: searchId || raw.search_id || raw.searchId,
    observationTime:
      metadata.observation_time || metadata.date_obs || raw.observationTime,
    wavelength:
      typeof metadata.wavelength === 'number'
        ? metadata.wavelength
        : raw.wavelength,
    bandwidth:
      typeof metadata.bandwidth === 'number'
        ? metadata.bandwidth
        : raw.bandwidth,
    detector: metadata.detector || raw.detector,
    // Never extract processing version from URL; keep null if absent[cite: 2]
    processingVersion:
      metadata.processing_version ?? raw.processingVersion ?? null,
    previewUrl: resolvedPreview,
    fitsUrl: resolvedFits,
    previewStatus: resolvedPreview ? 'available' : 'unavailable',
    fitsStatus: resolvedFits ? 'available' : 'unavailable',
    provenance: {
      sourceUrl: source.url || raw.provenance?.sourceUrl,
      checksum: source.checksum || raw.provenance?.checksum,
      collection: metadata.collection || raw.provenance?.collection,
    },
    qualityStatus: raw.quality_status || raw.qualityStatus || 'not_assessed',
  };
}

/**
 * Searches the SPHEREx backend archive, falling back cleanly to offline fixtures
 * if the backend server is not yet running.
 */
export async function searchObservations(params: {
  targetName: string;
  ra: string;
  dec: string;
  radiusDeg: number;
  useOfflineFallback?: boolean;
}): Promise<SearchResponse> {
  if (params.useOfflineFallback) {
    await new Promise((r) => setTimeout(r, 400)); // Simulate realistic network latency
    return {
      searchId: `srch_offline_${Date.now()}`,
      observations: WISE_0855_FIXTURE,
      truncated: false,
      isOfflineMock: true,
    };
  }

  try {
    const response = await fetch(`${API_BASE_URL}/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        target_name: params.targetName,
        ra: params.ra,
        dec: params.dec,
        radius: params.radiusDeg,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const detail =
        typeof errorData.detail === 'string'
          ? errorData.detail
          : `Archive search failed with HTTP ${response.status}`;
      throw new Error(detail);
    }

    const data = await response.json();
    const searchId = data.search_id || `srch_${Date.now()}`;
    const rawResults = Array.isArray(data.results)
      ? data.results
      : Array.isArray(data.observations)
      ? data.observations
      : [];

    return {
      searchId,
      observations: rawResults.map((item: any) =>
        normalizeObservation(item, searchId)
      ),
      truncated: Boolean(data.truncated || rawResults.length >= 500),
      isOfflineMock: false,
    };
  } catch (err: any) {
    // If network fails because backend isn't started locally yet, inform caller clearly
    throw new Error(
      err.message || 'Unable to reach SKYTRACE backend API. Switch to Offline Fixture Mode to test UI.'
    );
  }
}

/**
 * Submits 1 or 2 selected observations to /prepare to fetch preview images & FITS paths[cite: 2].
 */
export async function prepareObservations(
  selected: NormalizedObservation[],
  isOfflineMock: boolean
): Promise<NormalizedObservation[]> {
  if (selected.length === 0 || selected.length > 2) {
    throw new Error('Select 1 or 2 observations to prepare.');
  }

  if (isOfflineMock) {
    await new Promise((r) => setTimeout(r, 500));
    return selected.map((obs) => ({
      ...obs,
      previewStatus: obs.previewUrl ? 'available' : 'unavailable',
      fitsStatus: obs.fitsUrl ? 'available' : 'unavailable',
    }));
  }

  const response = await fetch(`${API_BASE_URL}/prepare`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      items: selected.map((obs) => ({
        search_id: obs.searchId,
        observation_id: obs.backendSelectionKey,
      })),
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const detail =
      typeof errorData.detail === 'string'
        ? errorData.detail
        : `Observation preparation failed (HTTP ${response.status})`;
    throw new Error(detail);
  }

  const data = await response.json();
  const preparedList = Array.isArray(data.prepared)
    ? data.prepared
    : Array.isArray(data.observations)
    ? data.observations
    : [];

  return preparedList.map((item: any, idx: number) =>
    normalizeObservation(item, selected[idx]?.searchId)
  );
}