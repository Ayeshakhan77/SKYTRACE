# SKYTRACE backend prototype

A small local API for Ayesha's SpaceLensers team: search public SPHEREx products,
retrieve a small FITS cutout, inspect its metadata, and serve a browser PNG preview.

## What was actually tested on 3 November 2026

- Target: the **fixed WISE 0855 coordinates in the challenge**, RA 133.7951291667°, Dec −7.2451472222°.
- Search radius: 0.01°. QR3 returned **0 records**; QR2 returned **256 records**.
- Two genuine QR2/D1 cutouts downloaded: **6 May 2025** and **5 May 2026**.
- Each cutout has an **18 × 18 IMAGE** plane, FLAGS, VARIANCE, ZODI, PSF and WCS-WAVE.
- Actual source sizes: **5,060,160** and **5,063,040 bytes**. Most bytes are ancillary PSF data, not the tiny sky crop.
- Local spectral WCS at the fixed query position gives **0.993667 µm** and **0.962969 µm**. A shared D1 label does not make these equal-wavelength observations.
- The real HTTP API search returned 256 records; one live HTTP cutout request, PNG delivery and original-file SHA-256 verification succeeded. An earlier two-cutout HTTP request hit a transport failure and returned a structured 502; the successful two-file CLI retrieval is separately preserved.

This establishes **data access and preview generation**. It does not establish a
confirmed WISE 0855 detection, a registered image pair, measured motion, or a
validated brightness change. The coordinate epoch/proper motion was not propagated.
The two products also have different processing versions (v20 and v24).

## Run locally

Use Python 3.12 or newer. From this directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m pip install -e . --no-deps
cp -R examples/cache/. data/
.venv/bin/python -m uvicorn skytrace.api:app --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765/docs` for the interactive API. The bundled example
records/previews work without contacting IRSA after copying the example cache.
`examples/observations.json` contains their API asset paths. Live searches and
new cutouts contact IRSA. Omit the copy command for a clean cache.

The server binds to localhost, accepts local frontend origins on port 3000, has
no account system, and is not deployed. Use `SKYTRACE_DATA_DIR` to choose another
cache directory. Requests are bounded to 500 metadata rows, 0.05° search radius,
two cutouts per request, 0.1° cutout size, 32 MiB per cutout, and one archive
operation at a time. The local cache has a 256 MiB budget, 64 searches and 32
prepared cutouts. When full, use a new cache directory; the API does not delete
old observations automatically.

## API flow for Husnain's viewer

1. `GET /v1/targets` gives the one curated target and coordinate provenance.
2. `POST /v1/searches` returns candidate products and a generated `search_id`.
3. `POST /v1/searches/{search_id}/cutouts` prepares one or two selected product IDs.
4. Each result includes `assets.preview_png_url` for display and
   `assets.original_fits_url` for the preserved scientific source.
5. `GET /v1/cutouts/{cutout_id}` returns the metadata for a Change Receipt.

Example search:

```sh
curl -sS http://127.0.0.1:8765/v1/searches \
  -H 'Content-Type: application/json' \
  -d '{"ra_deg":133.7951291667,"dec_deg":-7.2451472222,"radius_deg":0.01,"collection":"spherex_qr2","limit":500}'
```

Use returned IDs, not a caller-supplied source URL:

```text
POST /v1/searches/{returned_search_id}/cutouts
{"observation_ids":["a_returned_observation_id"],"size_deg":0.03}
```

An empty successful search is distinct from an archive failure. Network failures
produce `502` with an error code and retryability; invalid caller inputs produce
`422`; an unknown saved ID produces `404`; an in-progress operation produces `429`.
There is no automatic retry loop. A caller may retry a transient failure with
bounded backoff. Batch preparation rolls back unpublished results if either item fails.

See [data-format.md](data-format.md), [openapi.json](openapi.json),
[observation.schema.json](observation.schema.json), and
[examples/observations.json](examples/observations.json).

## Repeat the retrieval and run checks

```sh
.venv/bin/python run_retrieval.py --output evidence-new-run
.venv/bin/python -m pytest -q
```

The retrieval command tries QR3, then QR2 if QR3 has no records. It downloads at
most two cutouts. It uses the first/last observation dates from one detector to
test retrieval, **not** to choose a science-ready pair. It saves raw metadata,
exact query URLs, acquisition times, product IDs, source URLs, bytes and hashes.
An archive failure is reported as a failure, not converted to zero observations.

## Next work for the team

1. Agree this JSON contract with Seerat and Husnain.
2. Select observations with compatible wavelength at the sky position, usable
   quality masks, and suitable processing/calibration—not merely a shared detector.
3. Propagate the target position appropriately and validate object identification.
4. Register images onto a common sky grid and assess PSF/photometric differences
   before enabling difference overlays or interpreting changes.

## Sources and credit

- [Official challenge](https://www.spaceappschallenge.org/2026/challenges/planet-x-and-spherex/)
- [IRSA data access](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-access/)
- [IRSA cutout service](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/cutout_tool.html)
- [IRSA FITS/WCS/flag tutorial](https://caltech-ipac.github.io/irsa-tutorials/spherex-intro/)

SPHEREx source data are served by NASA/IPAC IRSA; keep original product IDs and
source links with every preview. The SKYTRACE/Change Receipt concept was shared
by Kainat; this package is Bruhadev's local retrieval and API prototype building
on that proposal. It is included here under `backend/` for the team's viewer
integration. The recorded live retrieval and scientific limitations above are
unchanged; repository integration does not imply deployment or scientific
validation.
