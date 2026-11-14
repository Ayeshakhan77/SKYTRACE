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