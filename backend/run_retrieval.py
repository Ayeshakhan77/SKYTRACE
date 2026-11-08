"""Run a real, bounded single-target SPHEREx retrieval and save evidence.

From the project folder: python run_retrieval.py --output ../irsa-live-test-2026-11-03
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from astropy.io import fits

from skytrace.irsa import IRSAError, download_cutout, parse_metadata, search_images, validate_capture_request

RA_DEG = 133.7951291667
DEC_DEG = -7.2451472222
CHALLENGE_URL = "https://www.spaceappschallenge.org/2026/challenges/planet-x-and-spherex/"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("evidence"))
    parser.add_argument("--reuse-captures", action="store_true", help="Reuse already saved successful metadata responses; cutout downloads are still live.")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    searches = []
    chosen = None
    for collection in ("spherex_qr3", "spherex_qr2"):
        raw_path = output / f"{collection}-response.xml"
        if args.reuse_captures:
            prefix = "initial-query" if collection == "spherex_qr3" else "qr2-query"
            raw_path = output / f"{prefix}-response.xml"
            request = json.loads((output / f"{prefix}-request.json").read_text())
            validate_capture_request(request, RA_DEG, DEC_DEG, 0.01, collection)
            observations, total, overflow = parse_metadata(raw_path.read_bytes(), collection, 500)
            result = {"query_url": request["url"], "queried_at_utc": datetime.fromtimestamp(raw_path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds"), "timestamp_basis": "Successful raw response capture file modification time, not request start time.", "total_rows": total, "truncated": overflow or total > 500, "upstream_truncated": overflow, "observations": observations}
        else:
            result = search_images(RA_DEG, DEC_DEG, 0.01, collection, 500, raw_path=raw_path)
        result["collection"] = collection
        result["raw_metadata_path"] = str(raw_path)
        searches.append(result)
        print(f"{collection}: {result['total_rows']} rows; retained {len(result['observations'])}", flush=True)
        if result["observations"]:
            chosen = result
            break
    (output / "search.json").write_text(json.dumps(searches, indent=2, allow_nan=False) + "\n")
    report = {
        "executed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target": {
            "name": "WISE 0855",
            "ra_deg": RA_DEG,
            "dec_deg": DEC_DEG,
            "coordinate_source": CHALLENGE_URL,
            "coordinate_text": "RA 08h55m10.831s, Dec -7d14m42.53s",
            "position_interpretation": "Fixed challenge coordinates; object identification and proper-motion propagation not performed.",
        },
        "query_radius_deg": 0.01,
        "cutout_size_deg": 0.03,
        "searches": [{key: value for key, value in result.items() if key != "observations"} for result in searches],
        "downloaded_observations": [],
        "comparison_status": "not_assessed",
        "limitations": [
            "A metadata match means the image footprint overlaps the query circle, not a confirmed detection of WISE 0855.",
            "Shared detector label does not establish equal wavelength at the target; SPHEREx wavelength varies across pixels.",
            "Alignment, proper motion, calibration compatibility and scientific change detection are not assessed by this retrieval script.",
        ],
    }
    if chosen is None:
        report["status"] = "no_observations"
    else:
        rows = [row for row in chosen["observations"] if row.get("mjd_start") is not None]
        bands = sorted(set(row.get("bandpass_name") for row in rows if row.get("bandpass_name")))
        band = "SPHEREx-D1" if "SPHEREx-D1" in bands else (bands[0] if bands else None)
        rows = sorted([row for row in rows if row.get("bandpass_name") == band], key=lambda row: row["mjd_start"])
        selected = [rows[0]] if rows else chosen["observations"][:1]
        if rows and rows[-1]["mjd_start"] - rows[0]["mjd_start"] >= 1.0:
            selected.append(rows[-1])
        for row in selected:
            destination = output / f"{row['observation_id']}.fits"
            download = download_cutout(row["source_url"], RA_DEG, DEC_DEG, 0.03, destination)
            with fits.open(destination, memmap=False) as hdus:
                inspection = [{"name": hdu.name, "shape": list(hdu.data.shape) if hdu.data is not None else None} for hdu in hdus]
                image = hdus["IMAGE"]
                headers = {key: image.header.get(key, hdus[0].header.get(key)) for key in ("DATE-OBS", "MJD-OBS", "DETECTOR", "BUNIT", "CTYPE1", "CTYPE2")}
            report["downloaded_observations"].append({"observation": row, "download": download, "local_fits_path": str(destination), "hdu_summary": inspection, "image_header_summary": headers})
            (output / "retrieval.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
            print(f"Downloaded {destination.name}: {download['byte_count']} bytes; IMAGE {image.shape}", flush=True)
        report["status"] = "retrieved" if report["downloaded_observations"] else "no_downloads"
        report["selection_basis"] = "First/last MJD of one detector within one collection; not a validated same-wavelength temporal pair."
    (output / "retrieval.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(f"Evidence: {output / 'retrieval.json'}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except IRSAError as exc:
        raise SystemExit(f"{exc.code}: {exc}") from exc
