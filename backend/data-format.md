# JSON contract, version 0.1

The generated OpenAPI and JSON Schema are authoritative for field types. This
document explains their meaning. Missing measurements are JSON `null`, never
zero, NaN, or an invented estimate. Observation dates retain the original FITS
header value and its declared time system. Retrieval times are explicit UTC.

## Search record

| Field | Meaning |
|---|---|
| `schema_version` | `0.1` |
| `search_id` | Generated local identifier for this search |
| `query` | Fixed ICRS coordinates in degrees, circle radius, collection and row limit |
| `query_url`, `queried_at_utc` | Exact upstream query and completion time |
| `total_rows`, `truncated` | Returned upstream table count and whether all rows are retained; a server overflow is also truncation |
| `observations[]` | Candidate image products, not confirmed target detections |
| `observations[].observation_id` | Stable SHA-256 prefix derived from the original product URL |
| `source_product_id`, `source_url`, `collection` | Preserved archive identity, original FITS URL and release |
| `mjd_start`, `mjd_end` | Original SIA time values in days; separate from more precise FITS header times |
| `wavelength_min_m`, `wavelength_max_m` | Whole-product wavelength coverage in **meters**, not the wavelength at a chosen pixel |
| `metadata` | Original JSON-safe SIA column values for provenance; do not display unescaped as HTML |

## Prepared observation / Change Receipt

| Field | Meaning |
|---|---|
| `cutout_id`, `search_id` | Generated identifiers; different cutout requests can share a source product |
| `query_position`, `size_deg` | Exact fixed center and requested square cutout size |
| `source` | Search observation, including original metadata and processing-version-bearing URL |
| `retrieval` | Exact cutout URL, UTC acquisition time, byte count and SHA-256 of the returned FITS |
| `inspection.image` | Measured IMAGE dimensions and physical unit |
| `inspection.observation_time` | Raw header start/end values, time system and field provenance |
| `inspection.spatial` | Whether celestial WCS exists and whether the fixed query coordinate falls inside this cutout |
| `inspection.wavelength.target_center_um` | Spectral WCS evaluated at the fixed query position, in **micrometers**; nullable |
| `inspection.wavelength.target_bandwidth_um` | Corresponding local bandwidth; nullable. This is not a proven common filter between observations |
| `inspection.quality` | Raw flags, variance and nonfinite-pixel summaries; scientific quality status stays `not_assessed` |
| `inspection.extensions` | Actual FITS extension names/shapes |
| `inspection.display` | Per-image 1st–99th percentile asinh grayscale rendering, lower origin |
| `assets` | Backend-relative preview/source routes, source hash and byte count |
| `comparison_status` | `not_assessed`; retrieving two images does not authorize a change claim |
| `limitations`, `inspection.warnings` | Explicit missing checks for the viewer to preserve |

`quality.nonzero_flag_fraction` is **not** a bad-pixel percentage. Some flags, such
as SOURCE, are informational. `flag_counts` preserves bit names, positions,
descriptions and counts; bits can overlap, so counts need not sum to the number
of affected pixels. Missing FLAGS means unknown quality, not an all-clear mask.

PNG orientation follows the original detector image with lower-origin display.
The PNGs have not been reprojected onto a shared north-up grid. They are separately
stretched for visibility and must not be used to measure brightness changes.

## Frontend behavior

- Label the exact observation dates and wavelength units.
- Use the preview route for display; offer the original FITS and source link for inspection.
- Keep unknown values visibly unknown.
- Preserve quality and comparison status beside the image; a successful download
  is not a green scientific check.
- Keep automatic differencing/motion claims disabled until a scientific comparison
  pipeline has validated alignment, wavelength, calibration, masks and object identity.

## Errors

Archive error example:

```json
{"error":{"code":"archive_timeout","message":"IRSA cutout request timed out.","retryable":true}}
```

Only transport/time-out errors are labeled retryable. Malformed metadata,
unexpected source URLs, invalid FITS and oversized responses need investigation.
Input/cache errors use FastAPI's `detail` shape (documented in OpenAPI); do not
interpret either error shape as an empty successful search.
