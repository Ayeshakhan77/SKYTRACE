# SKYTRACE
A SPHEREx sky exploration and time-based image comparison web tool.

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
