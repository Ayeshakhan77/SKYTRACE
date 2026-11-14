# SKYTRACE viewer integration

This is a dependency-free browser MVP wired to the existing local API. It can
load backend targets, search a selected fixed sky coordinate, display search
rows, prepare one or two selected products, show browser PNG previews, and link
to the original FITS and IRSA product.

## Run it

Start the backend using the setup in [`../backend/README.md`](../backend/README.md).
In another terminal, from the repository root, run:

```sh
python3 -m http.server 3000 --directory frontend
```

Then open `http://localhost:3000`. The API address defaults to
`http://127.0.0.1:8765`. To use another local address, add `?api=http://HOST:PORT`
to the viewer URL. The backend currently permits browser requests from
`localhost:3000` and `127.0.0.1:3000`.

The current `/v1/targets` response contains one confirmed preset: WISE 0855 at
RA 133.7951291667°, Dec −7.2451472222°. This is a fixed challenge coordinate;
proper motion has not been propagated. The UI lets a user enter coordinates,
but it does not invent the four additional target presets mentioned by the
team; their IDs/names and coordinates still need to be supplied.

## Data behavior

- Search rows represent archive footprints that overlap the fixed query
  direction, not confirmed detections of the named object.
- A result may be selected for preview only when it came back from the current
  saved search. The browser sends returned observation IDs to the prepare route;
  it never supplies a FITS URL to the backend.
- Search results are limited to 500 and one prepare request accepts one or two
  products. Longer timelines need multiple requests and a deliberate UI flow.
- Product wavelength bounds are shown as archive metadata only. The prepared
  response's local spectral WCS value is shown separately in micrometers.
- The viewer preserves the API's `comparison_status`, quality status, and
  warnings. It does not compute differences, motion, or brightness changes.

## Contract examples

The exact cached search and prepared-observation records are in
[`../backend/examples/observations.json`](../backend/examples/observations.json).
The complete endpoint shapes are in [`../backend/openapi.json`](../backend/openapi.json)
and the field meanings are in [`../backend/data-format.md`](../backend/data-format.md).
