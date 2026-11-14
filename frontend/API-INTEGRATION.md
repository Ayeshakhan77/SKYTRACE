# API integration notes for the viewer

These examples are excerpts from the backend's saved request/response fixtures,
not newly generated live results. Full payloads remain in
[`../backend/examples/observations.json`](../backend/examples/observations.json),
the cached search under `../backend/examples/cache/searches/`, and
[`../backend/openapi.json`](../backend/openapi.json).

## Search

`POST /v1/searches`

```json
{
  "ra_deg": 133.7951291667,
  "dec_deg": -7.2451472222,
  "radius_deg": 0.01,
  "collection": "spherex_qr2",
  "limit": 500
}
```

The saved QR2 response used this fixed WISE 0855 position and returned 256 rows
without truncation. The equivalent saved QR3 query returned 0 rows. An archive
row excerpt:

```json
{
  "observation_id": "7f169ac45d22df30c60dd4ef",
  "source_product_id": "ivo://irsa.ipac/spherex_qr2?2025W19_1B_0241_1/D1",
  "source_url": "https://irsa.ipac.caltech.edu/ibe/data/spherex/qr2/level2/2025W19_1B/l2b-v20-2025-242/1/level2_2025W19_1B_0241_1D1_spx_l2b-v20-2025-242.fits",
  "collection": "spherex_qr2",
  "mjd_start": 60801.514177,
  "mjd_end": 60801.515509,
  "wavelength_min_m": 7.455e-7,
  "wavelength_max_m": 1.1167e-6,
  "bandpass_name": "SPHEREx-D1"
}
```

The response wrapper also contains `schema_version`, `search_id`, the exact
`query`, `query_url`, `queried_at_utc`, `truncated`, `total_rows`, and an
`interpretation` string. Archive metadata may include additional fields under
`metadata`; clients should ignore unknown fields and preserve the source IDs and
URL. Wavelength minimum/maximum are broad product bounds in **meters**, not a
measurement at the target pixel.

## Prepare one or two products

`POST /v1/searches/{search_id}/cutouts`

```json
{
  "observation_ids": ["7f169ac45d22df30c60dd4ef"],
  "size_deg": 0.03
}
```

The endpoint returns an array of `PreparedObservation` objects. It accepts one
or two IDs from the saved search; IDs outside that search are rejected. Prepared
record excerpt from the 6 May 2025 observation:

```json
{
  "schema_version": "0.1",
  "cutout_id": "e3a440b1023a5200908226705840183d",
  "search_id": "ae25b7204ad740579de50a6da78d0755",
  "query_position": {"ra_deg": 133.7951291667, "dec_deg": -7.2451472222},
  "size_deg": 0.03,
  "retrieval": {
    "byte_count": 5060160,
    "sha256": "822f99bfc107a86453f522ae52352a5c61bc85c0a03ea9c9041c913db1d3bf51",
    "retrieved_at_utc": "2026-11-03T12:04:40+00:00"
  },
  "inspection": {
    "image": {"width": 18, "height": 18, "unit": "MJy / sr", "image_extension": "IMAGE"},
    "observation_time": {
      "date_obs": "2025-05-06T12:20:24.888",
      "date_end": "2025-05-06T12:22:20.006",
      "time_system": "UTC",
      "status": "header_value"
    },
    "spatial": {
      "has_celestial_wcs": true,
      "query_position_within_cutout": true,
      "alignment_status": "not_assessed"
    },
    "wavelength": {
      "target_center_um": 0.9936670117685139,
      "target_bandwidth_um": 0.026386620568176006,
      "status": "spectral_wcs_evaluated",
      "position_basis": "fixed_query_position"
    },
    "quality": {
      "status": "not_assessed",
      "flags_present": true,
      "nonzero_flag_fraction": 0.33641975308641975,
      "variance": {"present": true, "unit": "MJy2 / sr2"}
    },
    "display": {
      "mode": "per_image_asinh",
      "percentile_low": 1,
      "percentile_high": 99,
      "brightness_comparison_validated": false
    },
    "warnings": ["Display-only preview; WCS alignment, spectral compatibility and scientific quality are not assessed."]
  },
  "assets": {
    "original_fits_url": "/v1/cutouts/e3a440b1023a5200908226705840183d/source.fits",
    "preview_png_url": "/v1/cutouts/e3a440b1023a5200908226705840183d/preview.png",
    "sha256": "822f99bfc107a86453f522ae52352a5c61bc85c0a03ea9c9041c913db1d3bf51",
    "byte_count": 5060160
  },
  "comparison_status": "not_assessed",
  "limitations": ["No cross-image registration, PSF matching, photometric comparison or motion detection was performed."]
}
```

The real response carries more detail than this excerpt, including complete
source metadata, individual FITS extension summaries, raw flag counts,
variance statistics, retrieval URL, percentile display bounds, and warnings.
The UI reads the response record directly and keeps those statuses visible.

## What the backend can report today

| Available from current response | Still awaiting scientific or team validation |
|---|---|
| Exact fixed query coordinates and query parameters | Five target preset IDs/names/coordinates; only WISE 0855 is currently configured in `GET /v1/targets` |
| Archive product IDs, collection, source URL, observation MJD and broad wavelength coverage | Live API response samples for the other four preset positions |
| Cutout dimensions, brightness unit, header observation times, WCS and whether the fixed query point falls in the cutout | Proper-motion propagation and whether WISE 0855 is actually in any cutout |
| Local spectral WCS wavelength/bandwidth at the query coordinate, when evaluable | A science-approved matched observation pair, common-grid registration, PSF/calibration compatibility and interpretation of quality masks |
| Raw FLAGS/VARIANCE summaries, image extension list, preview and original FITS with SHA-256 | Motion, transient identity or brightness-change claims |
| Retrieval and cache errors with distinct status/error codes | Public deployment and integration into an existing team frontend; no frontend source exists in the current repository snapshot |

## WISE 0855 pair candidate for the demo

I inspected four additional QR2 detector-D1 products from the saved 256-row
WISE 0855 search. Among those sampled candidates, the 6 May 2025 product
`2025W19_1B_0241_1/D1` and the 4 May 2026 product
`2026W19_1A_0201_1/D1` look like the best **visual/demo candidate** so far:
both fixed coordinates land inside the 18×18 cutouts, their local wavelengths
are 0.993667 µm and 0.970521 µm (about 0.023146 µm apart), and their observations
are about a year apart. The second candidate has 0.39198 of pixels carrying at
least one flag; the first has 0.33642. These are raw nonzero-flag fractions,
not bad-pixel percentages. The 2025 and 2026 source paths use processing v20 and
v24, respectively.

This is a provisional choice from a small sampled subset, **not** an all-256
ranking or a scientifically approved like-for-like comparison. The API still
marks quality and comparison `not_assessed`. Calibration/version effects,
quality-flag meanings, registration, PSF treatment, target association, and
brightness interpretation remain unresolved. The previously bundled 5 May 2026
example (0.962969 µm) is less close in local wavelength to the 2025 example.
The new candidate's raw cutout and inspection are saved outside the repository
at `work/irsa-pair-evaluation-2026-11-14/` until the team agrees to add it as an
example fixture.

The other four preset searches cannot be performed until the team supplies
their IDs/names and coordinates. Only WISE 0855 is documented in the current
backend target catalog.
