export type AssetAvailability = 'available' | 'unavailable';

export type ValidationStatus =
  | 'not_assessed'
  | 'pending'
  | 'passed'
  | 'failed'
  | 'not_applicable';

export interface ObservationProvenance {
  sourceUrl?: string;
  checksum?: string;
  collection?: string;
}

export interface NormalizedObservation {
  // Backend 24-char SHA-256 selection key (distinct from archive obs_id)
  backendSelectionKey: string;
  // Archive observation identifier (source.metadata.obs_id)
  archiveObservationId?: string;
  sourceProductId: string;
  searchId?: string;
  observationTime?: string; // ISO date string
  wavelength?: number; // Microns (µm)
  bandwidth?: number; // Microns (µm)
  detector?: string;
  // Must display as unavailable if null/missing — never parse from URL
  processingVersion?: string | null;
  previewUrl?: string;
  fitsUrl?: string;
  previewStatus: AssetAvailability;
  fitsStatus: AssetAvailability;
  provenance: ObservationProvenance;
  qualityStatus: ValidationStatus;

  // --- Fields added to match the real backend (bruhadev/skytrace-viewer-integration) ---
  // Prepared cutout ID (only present after POST /v1/searches/{id}/cutouts)
  cutoutId?: string;
  // Where `wavelength` came from: the local spectral WCS at the query position
  // (prepared cutouts) or absent. Search rows only carry the broad product range.
  wavelengthBasis?: 'spectral_wcs_at_query_position' | 'unavailable';
  // Broad product wavelength range from archive metadata, converted m -> µm
  wavelengthRangeUm?: { min: number; max: number };
  // Raw fraction of pixels with any FLAGS bit set (not a bad-pixel percentage)
  nonzeroFlagFraction?: number;
  // Whether the query position falls inside the cutout footprint
  queryPositionInCutout?: boolean;
  alignmentStatus?: ValidationStatus;
  comparisonStatus?: ValidationStatus;
  // e.g. 'per_image_asinh' — per-image stretch means brightness can't be compared
  displayMode?: string;
  brightnessComparisonValidated?: boolean;
  imageSize?: { width: number; height: number; unit?: string };
  warnings?: string[];
  limitations?: string[];
}

export interface TargetPreset {
  id: string;
  name: string;
  ra: string;
  dec: string;
  epoch: string;
  frame: string;
  radiusDeg: number;
  notes: string;
}

export interface ChangeReceiptData {
  receiptId: string;
  specVersion: string;
  generatedAt: string;
  readinessStatus: 'ready' | 'partial';
  targetName: string;
  requestedRa: string;
  requestedDec: string;
  comparisonMode: 'blink' | 'side_by_side' | 'single';
  observations: NormalizedObservation[];
  validationChecks: {
    identityAssessment: ValidationStatus;
    wavelengthCompatibility: ValidationStatus;
    calibrationCompatibility: ValidationStatus;
    wcsRegistration: ValidationStatus;
    psfMatching: ValidationStatus;
    photometricValidation: ValidationStatus;
    dataQualityReview: ValidationStatus;
  };
}