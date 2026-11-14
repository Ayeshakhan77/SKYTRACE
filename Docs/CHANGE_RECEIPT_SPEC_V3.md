# SKYTRACE — Change Receipt Specification

**Document:** `CHANGE_RECEIPT_SPEC.md`  
**Project:** SKYTRACE — A SPHEREx Sky Exploration and Time-Based Image Comparison Tool  
**Version:** 3.0 — backend contract confirmed and frontend integration refined  
**Status:** Proposed for team review  
**Owner:** Kainat Nadeem  
**Backend reference:** SKYTRACE backend API schema `0.1`, `PreparedObservation`, and `examples/observations.json`  
**Primary purpose:** Transparent observation provenance, comparison-state communication, and scientifically responsible evidence display.

> **Core principle:** Every displayed observation must be traceable to its source. Every scientific claim must be supported by the validation actually completed for the selected comparison.

The Change Receipt is not a discovery certificate, an object-identification system, or an automatic declaration that something changed in the sky.

---

## 1. Purpose and boundaries

The Change Receipt explains which observations a user selected, where they came from, what their metadata and image-quality information show, which comparison checks have been performed, and what conclusions are justified.

For the MVP, the Receipt is a frontend view model derived from the existing backend records. It is **not** a second observation schema and does not replace the backend response. The frontend adapter must preserve the original record and must not assign scientific checks as passed merely because images were retrieved or previews rendered.

### Included in the MVP

- Search position and cutout size.
- Selected observation dates, wavelengths, detector labels, archive/product identifiers, and source links.
- Original FITS and preview references, retrieval time, byte count, and checksum.
- Image dimensions, units, WCS availability, query-position coverage, raw quality/variance summaries, display-stretch metadata, warnings, and limitations where returned.
- Explicit comparison mode and comparison status.
- Validation checks with explanations and evidence references where available.
- Separate visual observations from measured scientific findings.
- Consistent handling of archive-level and API-level errors.

### Not claimed as MVP capabilities

Unless implemented and validated separately, the Receipt must not claim automatic Planet X/Planet Nine detection, confirmed object identity, proper-motion tracking, transient classification, validated image differencing, image registration, PSF matching, photometric variability, detector-array coaddition, full 102-band spectral analysis, or Gaia/WISE cross-matching.

---

## 2. Confirmed backend contract and identifier meanings

The backend has several identifiers with different meanings. The Receipt and UI must label them accurately.

| Backend field | Confirmed meaning | User-facing label/use |
|---|---|---|
| `cutout_id` | Backend-generated ID for a retrieved and prepared cutout. | “Cutout ID”; use for SKYTRACE API asset routes. |
| `search_id` | Backend-generated ID for one saved archive search. | “Search ID”; useful for support/debugging, usually in details. |
| `source.observation_id` | First 24 hexadecimal characters of SHA-256 computed from the exact source URL. | Keep as `backendObservationId`; use as the backend selection key only. |
| `source.source_product_id` | Archive product identifier when supplied by IRSA, often a publisher DID. | “Archive product ID.” |
| `source.metadata.obs_id` | IRSA metadata observation identifier when present. | “Archive observation ID,” only when this field is present. |
| `source.source_url` | Original IRSA product URL. | “Original archive product.” |
| `retrieval.url` | Exact URL used to retrieve the spatial cutout. | “Retrieved cutout URL” in technical details. |
| `assets.preview_png_url` | Backend-relative route to a display-only preview. | Display image; do not treat it as science data. |
| `assets.original_fits_url` | Backend-relative route to the retrieved FITS cutout. | Link to original scientific data product. |

### 2.1 `source.observation_id` semantics

Loco confirmed that:

- The value is generated from the exact source URL.
- It consists of the first 24 hexadecimal characters of the SHA-256 hash.
- It is stable when the exact source URL remains unchanged.
- It is a backend selection key, not an archive identifier.
- It is not a permanent cross-release identifier.
- As a truncated hash, it has no absolute uniqueness guarantee.

Frontend requirements:

1. Preserve the value exactly as returned.
2. Store it under a clearly named field such as `backendObservationId`.
3. Never label it as an IRSA observation ID.
4. Do not independently regenerate it in the frontend.
5. Do not assume it remains the same if the source URL changes.
6. Do not use it as a permanent global identifier or sole long-term identity key.

The archive observation ID must continue to come only from `source.metadata.obs_id` when supplied.

### 2.2 Preparation and metadata-search limits

Loco confirmed two separate limits:

- **Preparation endpoint:** accepts one or two products per request.
- **Metadata search:** the 500-row limit applies to metadata-search results, not to the preparation endpoint.

The MVP must support one selected observation or a two-observation comparison using the existing preparation endpoint.

The 500-row metadata-search limit must not be presented as the number of products that can be prepared in one request.

A timeline containing more than two prepared observations requires an intentional backend workflow or multiple preparation requests. It must not be assumed to work through a single preparation request.

### 2.3 Processing version

There is currently no dedicated processing-version field in the backend response.

Therefore:

- Normalize `processingVersion` as `null` when no dedicated field is supplied.
- Display **“Processing version unavailable.”**
- Do not parse the version from `source.source_url`, source-product paths, or display strings as a permanent frontend dependency.
- If the backend later exposes a dedicated field, update the adapter mapping and this specification together.

The source URL remains available in technical details for provenance.

---

## 3. Receipt lifecycle and scientific comparison status

The Receipt has separate states for assembly, scientific comparison, and individual assets. These states must never be collapsed into one status.

### 3.1 Receipt loading status

`receiptStatus` describes whether the frontend assembled the requested Receipt view.

- `ready` — every selected observation record is available and the Receipt can be assembled without losing required provenance. Missing optional image assets do not make the Receipt partial.
- `partial` — at least one selected observation record or required provenance value is missing, but the remaining records can still be shown.

Required provenance for readiness:

- Selected cutout ID.
- Query position and cutout size.
- Source URL and collection.
- Exact retrieval URL.
- SHA-256 checksum.
- Byte count.
- Retrieval time.

An archive product ID is included when supplied.

Nullable metadata such as an unavailable observation date, wavelength, archive observation ID, or product ID may be shown as unavailable without making the Receipt partial, provided the backend explicitly returned it as missing.

Preview and FITS asset availability are tracked separately in each observation's `assets` object.

An empty successful archive search or an empty observation selection is handled outside Receipt creation. It is a search/selection state, not a Receipt with zero observations.

A failed archive request must never be represented as “no observations found.” Technical failures are represented by the surrounding API/UI error state, not by a fabricated Receipt payload.

### 3.2 Scientific comparison status

`comparison.status` describes the evidence-processing state.

- `not_assessed` — no scientific comparison has been performed. This is the current backend state.
- `processing` — an implemented comparison process is in progress.
- `completed` — the required checks for the selected method have been assessed and passed their stated acceptance criteria.
- `inconclusive` — processing completed, but the evidence does not support a reliable conclusion.
- `failed` — the comparison process failed technically.

The user can still view or blink two previews when `comparison.status` is `not_assessed`.

This means the **visual experience is available**, not that a scientific comparison has passed.

### 3.3 Individual check status

Each check uses exactly one of these values:

- `not_assessed`
- `pending`
- `passed`
- `failed`
- `not_applicable`

`not_assessed` is not equivalent to `false`.

A `not_applicable` check must include a reason. Each check explanation is required in the normalized Receipt model so the UI cannot accidentally show an unexplained green tick.

Do not introduce an `incompatible` status unless it is added consistently to the types and acceptance rules. Describe incompatibility in the check explanation and set that check to `failed`; set the overall comparison to `inconclusive` when processing completed but cannot support a reliable conclusion.

### 3.4 Current backend state

For the current implementation:

- Quality review remains `not_assessed`.
- Cross-image alignment remains `not_assessed`.
- Scientific comparison remains `not_assessed`.
- No difference product is generated or available.
- Preview availability does not imply scientific validation.
- FITS retrieval does not imply scientific validation.

The frontend must preserve these states unless a real backend processing method is implemented and its output is validated.

---

## 4. Comparison mode determines required checks

A single generic checklist is not sufficient for all uses. Record the method the user or system is attempting, and assess only the checks relevant to that method.

### Supported MVP display modes

- `visual_blink` — display selected previews in time order. This is an exploratory visualization, not a validated measurement.
- `visual_side_by_side` — display selected previews together. This is an exploratory visualization, not a validated measurement.

### Future analysis modes, only after implementation

- `same_band_difference` — quantitative or pixel-level difference image for spectrally compatible observations.
- `photometric_change` — measured brightness change for an identified source using an appropriate method and uncertainty treatment.
- `motion_assessment` — astrometric assessment of a source's position across observations.
- `spectral_comparison` — comparison of measurements across wavelengths; this is not automatically a temporal-change claim.

For a visual blink or side-by-side view:

- Scientific checks remain `not_assessed` unless an actual assessment has been performed.
- The UI must not imply that a difference image or measurement exists.
- `visualChange` remains `not_assessed` by default.
- A human may explicitly record a preview-level visual observation, attributed to `human_review`.
- A human visual note must not be converted into a measured astronomical finding.

For a future analysis mode, the processing implementation must define its required checks and acceptance criteria before it can report `completed`.

| Check | What it assesses | Typical relevance |
|---|---|---|
| `wavelength_compatibility` | Whether observations are comparable at the relevant sky position and for the intended method. | Required for same-band photometric/difference claims. |
| `calibration_compatibility` | Whether processing/calibration differences are understood and acceptable for the method. | Required for quantitative difference or photometric claims. |
| `wcs_registration` | Whether images are mapped to a common sky coordinate grid. WCS being present in both images does not mean registration has been performed. | Required for image subtraction and defensible position comparisons. |
| `pixel_grid_compatibility` | Whether image dimensions, scale, orientation, and sampling are handled by the method. | Required for pixel-level comparison. |
| `psf_matching` | Whether differences in point-spread function are accounted for when needed. | Required for supported source-flux and image-difference methods. |
| `quality_review` | Whether relevant FLAGS, VARIANCE, and other quality information has been interpreted. | Required for scientific measurement. |
| `target_association` | Whether measurements in multiple images correspond to the same intended object rather than only the same fixed sky coordinate. | Required for target-specific motion or variability claims. |
| `astrometric_validation` | Whether positions and uncertainties support a motion assessment. | Required for a motion claim. |
| `photometric_validation` | Whether flux measurements and uncertainties support a brightness-change result. | Required for a photometric claim. |

A validation policy must list `requiredChecks` for the selected `comparisonMode`.

`comparison.status` may be `completed` only when all required checks have been assessed and pass. A failed required check cannot be overridden by a visual impression or user vote.

---

## 5. Normalized frontend Receipt model

This model is a presentation view derived from backend responses. It must not be sent to the existing backend or used as a substitute for the backend's `PreparedObservation` schema.

```typescript
export type AssessmentStatus =
  | "not_assessed"
  | "pending"
  | "passed"
  | "failed"
  | "not_applicable";

export type ReceiptStatus = "ready" | "partial";

export type AssetAvailability =
  | "available"
  | "unavailable"
  | "not_requested"
  | "error";

export interface ReceiptAsset {
  // available = asset request succeeded and the asset can be used.
  // not_requested = a reference exists but has not been fetched.
  // unavailable = backend has confirmed the resource is absent.
  // error = an asset request was attempted and failed.
  status: AssetAvailability;

  // May be a backend-relative path. Resolve against the configured API base URL.
  // A URL/reference alone does not prove that the asset is available.
  url: string | null;

  errorCode?: string;
}

export type ComparisonStatus =
  | "not_assessed"
  | "processing"
  | "completed"
  | "inconclusive"
  | "failed";

export type ComparisonMode =
  | "visual_blink"
  | "visual_side_by_side"
  | "same_band_difference"
  | "photometric_change"
  | "motion_assessment"
  | "spectral_comparison";

export type CheckName =
  | "wavelength_compatibility"
  | "calibration_compatibility"
  | "wcs_registration"
  | "pixel_grid_compatibility"
  | "psf_matching"
  | "quality_review"
  | "target_association"
  | "astrometric_validation"
  | "photometric_validation";

// MVP supports only unconfirmed.
// Extend only after a documented identification/review workflow exists.
export type IdentityStatus = "unconfirmed";

export interface CheckResult {
  status: AssessmentStatus;
  explanation: string;
  evidenceRefs?: string[];
}

export interface ReceiptObservation {
  cutoutId: string;

  // Backend-generated selection key. Not an archive ID or permanent global ID.
  backendObservationId: string;

  observationId: string | null;       // source.metadata.obs_id, if supplied
  sourceProductId: string | null;     // source.source_product_id
  sourceUrl: string;
  collection: string;

  dateObs: string | null;             // FITS header value
  dateEnd: string | null;
  timeSystem: string | null;
  mjdStart: number | null;             // archive metadata; keep distinct from FITS time
  mjdEnd: number | null;

  wavelengthCenterUm: number | null;  // evaluated at fixed query position
  bandwidthUm: number | null;
  wavelengthStatus: string;
  bandpassName: string | null;

  // No dedicated backend field currently exists.
  // Keep null and display "Processing version unavailable."
  processingVersion: string | null;

  assets: {
    preview: ReceiptAsset;
    originalFits: ReceiptAsset;
  };

  retrievalUrl: string;
  sha256: string;
  retrievedAtUtc: string;
  byteCount: number;

  imageWidth: number;
  imageHeight: number;
  imageUnit: string | null;
  hasCelestialWcs: boolean;
  queryPositionWithinCutout: boolean | null;
  alignmentStatus: string;

  quality: {
    status: string;
    nonfiniteFraction: number | null;
    flagsPresent: boolean;
    nonzeroFlagFraction: number | null;
    flagCounts: Array<{
      name: string;
      bit: number;
      count: number;
      description: string;
    }>;
    variance: {
      present: boolean;
      unit: string | null;
      nonfiniteFraction: number | null;
      negativeFraction: number | null;
    };
  };

  display: {
    mode: string;
    percentileLow: number;
    percentileHigh: number;
    valueLow: number;
    valueHigh: number;
    brightnessComparisonValidated: false;
  };

  warnings: string[];
  limitations: string[];
}

export interface ChangeReceipt {
  receiptId: string;
  receiptVersion: "3.0";
  generatedAtUtc: string;
  receiptStatus: ReceiptStatus;

  query: {
    raDeg: number;
    decDeg: number;
    sizeDeg: number;
    identityStatus: IdentityStatus;
  };

  selection: {
    comparisonMode: ComparisonMode;
    cutoutIds: string[];
    selectedObservationCount: number;
  };

  observations: ReceiptObservation[];

  comparison: {
    status: ComparisonStatus;
    method: string | null;
    methodVersion: string | null;
    requiredChecks: CheckName[];
    checks: Partial<Record<CheckName, CheckResult>>;
    differenceProduct: {
      available: boolean;
      validationStatus: AssessmentStatus;
      assetUrl: string | null;
    };
  };

  findings: {
    visualChange:
      | "not_assessed"
      | "visible"
      | "not_visible"
      | "inconclusive";

    measuredChange:
      | "not_assessed"
      | "change_detected"
      | "no_change_detected"
      | "inconclusive";

    interpretation: string;
    interpretationSource:
      | "system_rule"
      | "human_review"
      | "not_assessed";
  };

  limitations: string[];
  unverifiedChecks: string[];
  reviewNotes: string[];

  // Keep the raw backend records available for traceability and debugging.
  originalRecords?: unknown[];
}

export interface NormalizedApiError {
  kind: "archive_error" | "api_error";
  message: string;
  httpStatus?: number;
  retryable?: boolean;
  raw: unknown;
}

export type ReceiptResult =
  | { kind: "receipt"; receipt: ChangeReceipt }
  | { kind: "error"; error: NormalizedApiError };
```

### Type-model rules

- `receiptStatus` is about assembling/displaying the Receipt. `comparison.status` is about scientific assessment. Never collapse them into one field.
- MVP `identityStatus` is always `unconfirmed`.
- Do not expose `candidate_under_review` or `verified` until a candidate-generation/human-review or identification workflow is implemented, documented, and validated.
- For the current API, `differenceProduct.available` must be `false`, and `validationStatus` must be `not_assessed`.
- Do not set difference-product availability from the presence of two previews.
- The current preparation endpoint accepts one or two products per request. Do not assume a single request supports a longer timeline.
- Optional or absent backend fields must remain `null` or be omitted as specified by the adapter. Do not convert missing values into `0`, `false`, a guessed band, or a guessed status.
- `originalRecords` is optional for the UI, but the adapter or application state must retain an accessible reference to the original records.
- `brightnessComparisonValidated` remains `false` for the current MVP. It may become a general boolean only when a validated measurement implementation exists and the model is updated accordingly.

---

## 6. Backend-to-Receipt field mapping

| Receipt field | Backend mapping | Important note |
|---|---|---|
| `query.raDeg`, `query.decDeg` | `query_position.ra_deg`, `query_position.dec_deg` | Fixed sky position only in the current prototype. |
| `query.sizeDeg` | `size_deg` | Requested cutout size, not necessarily the full archive footprint. |
| `selection.cutoutIds[]` | Selected `cutout_id` values | Exact inputs to the current Receipt. |
| `observations[].backendObservationId` | `source.observation_id` | SHA-256 prefix selection key; not IRSA `obs_id`. |
| `observations[].observationId` | `source.metadata.obs_id` | Nullable IRSA metadata value. |
| `observations[].sourceProductId` | `source.source_product_id` | Preserve as provided. |
| `observations[].sourceUrl` | `source.source_url` | Original source product URL. |
| `observations[].dateObs`, `dateEnd`, `timeSystem` | `inspection.observation_time.*` | FITS header values and declared time system. |
| `observations[].mjdStart`, `mjdEnd` | `source.mjd_start`, `source.mjd_end` | Archive values; do not silently replace FITS header times with these. |
| Wavelength fields | `inspection.wavelength.*` | Local spectral WCS at the fixed query coordinate; not just broad product bounds. |
| `processingVersion` | No dedicated field currently available | Set to `null`; show “Processing version unavailable.” Do not parse source URLs. |
| Preview/FITS asset paths | `assets.preview_png_url`, `assets.original_fits_url` | Backend-relative routes; resolve using the configured API base URL. |
| `retrievalUrl` | `retrieval.url` | Exact request URL used for the spatial FITS cutout. |
| Checksum / byte count | `retrieval.sha256`, `retrieval.byte_count` (also repeated in `assets`) | Preserve one canonical mapping; verify duplicates agree. |
| Image and spatial fields | `inspection.image.*`, `inspection.spatial.*` | WCS availability is not evidence images were registered together. |
| Quality details | `inspection.quality.*` | Retain raw flag counts and variance details. |
| Display metadata | `inspection.display.*` | Per-image asinh stretch is display-only; brightness comparison is not validated. |
| Warnings | `inspection.warnings` | Preserve and surface relevant warnings. |
| Limitations | `limitations` | Preserve; add comparison-specific limitations without overwriting backend limitations. |
| Current comparison status | `comparison_status` | Currently `not_assessed`; do not infer a pass from retrieval. |

### 6.1 Relative asset URL handling

The preview and FITS paths returned by the backend are relative to the API base URL.

The frontend must:

1. Keep the configured API base URL in one configuration location.
2. Resolve relative preview and FITS paths against that base URL.
3. Avoid hardcoding the backend host separately in viewer, Receipt, and download components.
4. Preserve the original relative path in the normalized record when useful for traceability.
5. Treat the resolved URL as a request location, not proof that the asset exists or is accessible.
6. Mark an asset `available` only after a successful asset response.

Do not concatenate URL strings in multiple UI components. Use one shared URL-resolution helper and handle trailing/leading slashes consistently.

### 6.2 Time and wavelength rules

Use `inspection.observation_time.date_obs` and `date_end` for human-readable FITS observation times.

Keep `source.mjd_start` and `mjd_end` separately for archive traceability and precise ordering, noting their source. Do not assume one representation replaces the other.

Use `inspection.wavelength.target_center_um` and `target_bandwidth_um` for the selected query position when available.

Do not substitute broad `source.wavelength_min_m` and `wavelength_max_m` product coverage for the local wavelength measurement.

Different local wavelengths may be useful for labelled spectral exploration, but they must not be presented as interchangeable same-band brightness observations.

---

## 7. API error normalization

The frontend adapter must handle both error response forms identified by the backend owner:

1. **Archive-level `error` response.**
2. **FastAPI `detail` response**, including input-validation or cache-related failures.

These are distinct response sources and must not be treated as successful empty search results.

### 7.1 Normalization requirements

The adapter should:

- Detect an archive-level `error` response.
- Detect a FastAPI error response containing `detail`.
- Normalize both into a consistent application-level error result.
- Preserve the original response payload for debugging and traceability.
- Preserve HTTP status information when available.
- Avoid assuming that `error` or `detail` always has one exact internal shape unless the API schema guarantees it.
- Avoid inventing error codes or retryability.
- Set `retryable` only when it can be determined from the response or an explicit application rule.
- Keep technical errors separate from scientific comparison findings.

Illustrative normalization behavior:

```typescript
function normalizeApiError(
  payload: unknown,
  httpStatus?: number
): NormalizedApiError {
  // Inspect the actual response defensively.
  // Archive-level `error` and FastAPI `detail` are distinct sources.
  // Preserve the original payload in `raw`.
  // Do not assume every error is retryable.
  // Return a consistent application-level error object.
}
```

This is an adapter behavior requirement, not a claim that the backend already returns the `NormalizedApiError` interface.

### 7.2 Error-state distinctions

| Situation | Normalized UI behavior |
|---|---|
| Archive-level `error` | `kind: "archive_error"`; show archive/retrieval failure. |
| FastAPI `detail` | `kind: "api_error"`; show API/input/cache failure as appropriate. |
| Successful search with zero rows | Show an empty-result state, not an error. |
| No observations selected | Show a selection prompt outside Receipt creation. |
| Preview request fails | Set preview asset to `error`; preserve the Receipt if required provenance is intact. |
| FITS request fails | Set FITS asset to `error`; preserve the Receipt if required provenance is intact. |
| Scientific comparison not performed | Keep `comparison.status` at `not_assessed`. |
| Scientific processing fails | Set comparison to `failed`; do not present the technical error as a scientific finding. |

A failed request must never be silently converted into an empty result.

---

## 8. Quality, warnings, and display interpretation

Preserve the entire `flag_counts` array, including bit, count, name, and description.

A nonzero flag is not automatically an unusable pixel. Flags have different meanings and can overlap, so counts need not sum to the number of flagged pixels.

`nonzeroFlagFraction` must not be labelled “bad-pixel percentage.”

If FLAGS are absent, quality is unknown, not clear.

The current backend quality state remains `not_assessed`. Listing raw flags does not constitute quality review.

The existing backend renders each image with its own 1st–99th percentile asinh stretch. This is useful for visual exploration, but preview pixel values and brightness cannot support a cross-image photometric claim.

Keep display metadata separate from scientific measurements.

The UI should distinguish:

1. **Observation warnings:** issues associated with an individual observation or its provenance.
2. **Comparison limitations:** issues that affect comparing the selected records.
3. **Identity limitations:** uncertainty about whether the target object has been identified or tracked.

Do not hide warnings because a PNG exists. The FITS remains the source product; the PNG is a visualization asset.

Cross-image alignment remains `not_assessed` unless an actual alignment process is implemented and assessed. WCS availability in individual records does not establish cross-image registration.

---

## 9. Findings and user-facing language

### 9.1 Findings fields

- `visualChange` describes a human-visible difference in displayed previews, not a physical conclusion about the sky.
- `measuredChange` describes the output of a validated measurement method. Keep it `not_assessed` until such a method runs.
- `interpretation` is plain-language text and must be generated from known Receipt fields or reviewed by a person.
- `interpretationSource` records whether text comes from a system rule, human review, or has not been assessed.

For the MVP, `visualChange` remains `not_assessed` by default. If a person explicitly records a visual observation, attribute it to `human_review` and clearly label it as a preview-level observation.

A visible image difference is not automatically an astronomical change.

A measured `no_change_detected` result is only allowed after a validated measurement method ran and met its acceptance criteria. It must not be used as a default for an empty or failed result.

### 9.2 Acceptable MVP language

- “Two SPHEREx observations are available for this requested sky position.”
- “The displayed previews look different; a scientific comparison has not been completed.”
- “The observations use different wavelengths at the query position.”
- “The images have not been registered to a common sky grid.”
- “The preview uses a separate display stretch for each image.”
- “The available evidence is insufficient to establish a brightness change or object motion.”
- “This fixed-position search does not confirm that the named object is present in both images.”
- “Processing version unavailable because the current backend response does not expose a dedicated field.”

### 9.3 Do not use without supporting validation

- “A new object has appeared.”
- “The source is moving.”
- “The object got brighter or dimmer.”
- “This is a confirmed transient.”
- “Planet X has been detected.”

The word **candidate** is reserved for an implemented candidate-generation or review process. A visual difference alone does not make an object a candidate.

---

## 10. User interface structure

The Receipt opens from the image viewer through a clearly labelled **View Change Receipt** action and reflects the exact selected cutouts, date pair, and comparison mode.

### A. Receipt header

Show:

- “SKYTRACE Change Receipt”
- Receipt ID
- Receipt version
- UTC generation time
- `receiptStatus`

Display comparison status separately and use text labels in addition to color.

### B. Investigated position and selection

Show:

- RA
- Dec
- Search size
- Identity status
- Comparison mode
- Selected observation count

Label the position as a **fixed sky coordinate** when no time-dependent target position has been applied.

Provide a copy-coordinate action if supported.

### C. Observation provenance

Show each observation in chronological order with:

- FITS observation date/time.
- Local wavelength and bandwidth.
- Detector/bandpass label.
- Collection.
- Processing version only if a dedicated backend field is supplied.
- Archive observation ID if present.
- Archive product ID.
- Original source link.
- Cutout ID.
- Preview asset state.
- Original FITS asset state/link.

Do not show a backend selection key as the archive ID.

If `source.metadata.obs_id` is missing, show “Archive observation ID unavailable.”

If no dedicated processing-version field exists, show “Processing version unavailable.”

### D. Quality and technical details

Provide an expandable panel for:

- Image dimensions.
- Physical units.
- WCS availability.
- Query pixel coordinates.
- Whether the query falls within the cutout.
- Quality status.
- Flag counts and descriptions.
- Variance.
- Display scaling.
- Retrieval time.
- Checksum.
- Original source metadata.

### E. Comparison validation

Show:

- Selected mode.
- Comparison status.
- Method/version if one ran.
- Required checks.
- Each check state.
- Explanation for each check.

`not_assessed` and `pending` must be visually neutral. A warning or failure must not be styled as a pass. A `not_applicable` check must say why.

### F. Findings and limits

Separate **What the previews show** from **What has been measured**.

If no validated comparison exists, say so plainly.

Show observation, comparison, and identity limitations separately, retaining backend warnings.

---

## 11. Error and empty states

| Situation | Expected UI behavior |
|---|---|
| Successful search with zero rows | “No matching archive records were returned for this query.” This is not a claim that no object exists. |
| No observations selected | Show a selection prompt outside Receipt creation; do not create a zero-observation Receipt. |
| Archive-level `error` response | Normalize as an archive error; preserve original payload and show retrieval failure. |
| FastAPI `detail` response | Normalize as an API error; preserve original payload and show the relevant input/cache/API failure. |
| Archive request failed | Show retrieval error and retryability only when known; do not show empty results. |
| Search is truncated | State that only part of the result set is shown; preserve the truncated indicator. |
| Preview not requested yet | Set that asset to `not_requested`; keep Receipt status based on records and required provenance. |
| Preview not supplied or known to be absent | Set that asset to `unavailable`; keep metadata and Receipt status if required provenance is intact. |
| Preview request fails | Set that asset to `error`; keep metadata and Receipt status if required provenance is intact. |
| FITS not requested, unavailable, or request fails | Set the FITS asset to `not_requested`, `unavailable`, or `error` as applicable; do not automatically change Receipt status. |
| Selected observation record or required provenance is missing | Set Receipt to `partial`; show available records and identify which record/provenance is missing. |
| Comparison not performed | Set comparison to `not_assessed`; allow visual viewing without claiming a measurement. |
| Required compatibility check fails | Explain which analysis is unsupported; do not claim a validated result. |
| Comparison processing fails | Set comparison to `failed`; show technical error separately from scientific interpretation. |
| Comparison completes without reliable evidence | Set comparison to `inconclusive`; explain why. |

An asset is `unavailable` only when the backend or a reliable response confirms that the resource is absent. A failed network request or server error must not automatically be interpreted as proof that the asset does not exist.

---

## 12. Golden integration example: WISE 0855 fixed-position search

Use the supplied two-record example as the integration fixture. It is a query around the challenge's WISE 0855 coordinates, not confirmation that WISE 0855 was detected in either image.

| Property | First record | Second record |
|---|---|---|
| FITS observation date | 2025-05-06 | 2026-05-05 |
| Collection / detector | QR2 / D1 | QR2 / D1 |
| Local center wavelength at query position | 0.993667 µm | 0.962969 µm |
| Quality review | `not_assessed` | `not_assessed` |
| Cross-image alignment | `not_assessed` | `not_assessed` |
| Scientific comparison | `not_assessed` | `not_assessed` |
| Preview brightness comparison | Not validated | Not validated |
| Processing version | Unavailable from dedicated backend field | Unavailable from dedicated backend field |

The supplied source-product paths contain version-like strings, but the frontend contract must not depend on parsing those paths. Display a processing version only when a dedicated backend field is supplied.

### Expected Receipt values

- `receiptStatus: "ready"` when both selected backend records and required provenance are available, regardless of whether optional preview/FITS assets have been requested or successfully loaded.
- Track preview and original FITS assets independently.
- Set an asset to `available` only after a successful asset response.
- Set an asset to `error` after a failed request.
- Set an asset to `unavailable` only when the resource is known to be absent.
- `selection.comparisonMode: "visual_blink"` or `"visual_side_by_side"`.
- `query.identityStatus: "unconfirmed"`.
- `comparison.status: "not_assessed"`.
- Quality, alignment, and comparison checks remain `not_assessed`.
- `comparison.differenceProduct.available: false`.
- `comparison.differenceProduct.validationStatus: "not_assessed"`.
- `findings.visualChange: "not_assessed"` unless a human explicitly records a preview-level observation.
- `findings.measuredChange: "not_assessed"`.
- Any human visual note must be attributed as `human_review` and phrased as a preview-level observation, not an astronomical conclusion.

### Suggested interpretation

> Two SPHEREx observations are available for the requested fixed sky position. They were captured on different dates and have different wavelengths at that position. The current backend does not expose a dedicated processing-version field, so processing versions are shown as unavailable. The previews use independent display scaling, and cross-image registration, PSF matching, quality review, object association, and photometric comparison have not been completed. No difference product is currently available. The images may be explored visually, but this Receipt establishes neither WISE 0855's presence in both images nor a motion or brightness change.

This fixture validates data mapping and careful language. It must not be hardcoded as permanent behavior for other target fields or future releases.

---

## 13. Frontend integration and acceptance criteria

The adapter should:

1. Accept the existing `PreparedObservation` records without modifying them.
2. Normalize backend names to the Receipt view model in one location.
3. Preserve nulls, optional fields, all warnings, all limitations, original records, and provenance values.
4. Derive the Receipt from the exact observations currently selected by the user.
5. Keep Receipt loading state separate from scientific comparison state.
6. Normalize both archive-level `error` and FastAPI `detail` responses.
7. Preserve original error payloads for debugging.
8. Resolve preview and FITS paths against the configured API base URL through one shared helper.
9. Never mark a scientific check as passed or identity as anything other than `unconfirmed` based only on archive metadata or preview availability.

### MVP acceptance criteria

**Data integrity**

- Receipt coordinates and size match the selected backend search/cutouts.
- Every selected `cutout_id` and backend selection key maps to the right record.
- `source.observation_id` is treated as a backend selection key, not an archive identifier.
- Archive observation ID is taken only from `source.metadata.obs_id` when available.
- FITS header times and archive MJD values remain distinguishable.
- Local wavelength values come from `inspection.wavelength`; broad product bounds are not shown as local spectral measurements.
- Preview, FITS, source URL, checksum, and retrieval metadata map correctly.
- Relative asset paths resolve against the configured API base URL.
- A URL alone does not imply that an asset is available.
- Processing version is shown as unavailable unless a dedicated backend field is supplied.
- Missing optional fields do not crash the UI or become invented values.

**API and error handling**

- Archive-level `error` responses are recognized and normalized.
- FastAPI `detail` responses are recognized and normalized.
- Original error payloads remain available for debugging.
- Successful empty results are distinguishable from failed requests.
- Input/cache errors are not misrepresented as empty archive results.
- Asset request errors do not automatically make the Receipt partial.
- Retryability is not invented when it cannot be determined.

**Scientific integrity**

- Unassessed checks never appear as passed.
- Quality, alignment, and comparison remain `not_assessed` unless real assessment is performed.
- No difference product is represented as available in the current MVP.
- Different wavelengths and per-image display scaling are disclosed when relevant.
- Visual differences are separated from validated measured changes.
- Object identity is not inferred from query coordinates, product names, or `target_name` alone.
- WCS availability is not confused with cross-image registration.
- Raw flags are not converted into an unsupported quality score.
- No discovery claim can be produced from previews alone.

**User experience**

- Receipt opens from the viewer and updates when selected observations or comparison mode changes.
- The MVP supports one observation or the agreed two-observation comparison.
- A single preparation request never assumes support for more than two products.
- The 500-row metadata-search limit is not confused with the preparation endpoint limit.
- `ready` remains possible when optional preview or FITS assets are `not_requested`, `unavailable`, or `error`, provided all selected records and required provenance are present.
- Preview and FITS assets expose separate availability states.
- Observation cards are chronologically ordered when usable dates exist; unknown dates remain labelled unknown.
- Users can inspect provenance, quality details, and limitations.
- Archive failures, API errors, empty search results, partial results, missing previews, and comparison failures are distinguishable.
- Cached example previews can be viewed without a live IRSA request.

---

## 14. Team responsibilities and handoff

| Responsibility | Owner |
|---|---|
| Change Receipt view model, evidence interpretation, product flow, and scientific UX validation | Kainat Nadeem |
| IRSA retrieval, FITS inspection, source metadata, and backend API | Bruhadev (Loco) |
| Receipt UI/UX, information hierarchy, status presentation, and responsive design | Seerat Fatima |
| Viewer implementation, observation selection, API integration, and Receipt components | Husnain |
| Product coordination, repository integration, and team task tracking | Ayesha Khan |

### Handoff from Kainat

- Share the confirmed identifier mapping and normalized types.
- Align the frontend adapter with Loco's confirmed API behavior.
- Ensure the frontend handles both archive `error` and FastAPI `detail` responses.
- Ensure asset URLs resolve against the configured API base URL.
- Give the frontend team the WISE 0855 golden example and expected interpretation.
- Review the UI for neutral unassessed states, accurate IDs, visible limitations, and no unsupported claim language.
- Validate that the Receipt follows selection changes and API error/partial-result states.
- Keep future science-processing features separate from the MVP until their method and acceptance criteria are agreed.

### Backend contract confirmation

The following points have been confirmed by Loco:

- `source.observation_id` is a 24-character SHA-256 prefix derived from the exact source URL, stable for an unchanged URL but not an archive ID or permanent cross-release identifier.
- The preparation endpoint accepts one or two products per request.
- The 500-row limit applies to metadata searches.
- No dedicated processing-version field currently exists.
- Preview and FITS paths are relative to the API base URL.
- Both archive `error` and FastAPI `detail` responses must be handled.
- Quality, alignment, and comparison remain `not_assessed`.
- No difference product currently exists.

No backend schema change is required for the current viewer and Receipt integration.

---

## 15. Future enhancements

| Enhancement | Prerequisite |
|---|---|
| Validated difference image | Defined method, compatible data, registered common grid, quality handling, and documented acceptance criteria. |
| Quantitative brightness change | Target association, compatible measurement, calibration/PSF treatment, and uncertainty handling. |
| Motion assessment | Multi-epoch position measurements, time-aware target association, astrometric validation, and appropriate coordinate propagation. |
| Multi-observation timeline | Backend support for multiple prepared cutouts, a defined retrieval strategy, and frontend behavior for missing/incomplete epochs. |
| Spectral fingerprint | Validated local spectral measurements and clear separation from temporal change. |
| Gaia/WISE cross-reference | Catalog retrieval, coordinate/epoch handling, cross-match method, and match uncertainty. |
| Shareable/exportable Receipt | Stable selection provenance, reproducible method metadata, durable asset links, and attribution. |

These features must not delay the first complete, reliable viewing experience.

---

## 16. Final product principle

SKYTRACE should make astronomical data approachable without making scientific claims stronger than the evidence allows.

**The backend tells us what data exists. The viewer shows users what they can explore. The Change Receipt explains what the evidence supports, what remains uncertain, and why.**
