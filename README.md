# SKYTRACE
A SPHEREx sky exploration and time-based image comparison web tool.

## Local MVP

The `backend/` folder contains the local IRSA search and cutout API. A lightweight
browser viewer is in [`frontend/`](frontend/README.md). Run the API first, then
serve the frontend on port 3000 as described there. The viewer loads target
presets from `GET /v1/targets`; the current backend exposes only the confirmed
WISE 0855 fixed-coordinate preset. Add the remaining preset coordinates only
after the team supplies them.

The field-by-field request/response handoff and current WISE 0855 demo-pair
assessment are in [`frontend/API-INTEGRATION.md`](frontend/API-INTEGRATION.md).

## Backend prototype

The [backend](backend/README.md) searches public NASA/IPAC IRSA SPHEREx
products, downloads selected FITS cutouts, and serves browser previews with
observation metadata. Python 3.12 or newer is required; follow the
[local setup instructions](backend/README.md#run-locally) to run it.

- [API flow and endpoints](backend/README.md#api-flow-for-husnains-viewer)
- [Data contract](backend/data-format.md), [OpenAPI](backend/openapi.json), and
  [observation schema](backend/observation.schema.json)
- [Two real observation examples](backend/examples/observations.json) and a
  bundled cache for frontend development without a live IRSA request
- [Retrieval results and limitations](backend/RESULTS.md)

The prototype verifies archive retrieval and preview generation. The example
pair has not been registered or scientifically validated, and it does not prove
object identity, motion, or a brightness change. The API is local-only and is
not deployed.

The SKYTRACE and Change Receipt concept was proposed by Kainat. Bruhadev's
backend prototype builds on that proposal for the team's viewer integration.
