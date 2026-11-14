"""Local API: archive search -> selected cutout -> inspected preview.

Run with ``uvicorn skytrace.api:app --host 127.0.0.1 --port 8765``.
Source URLs are never accepted from callers. A cutout must refer to a product
returned by a saved archive search. Scientific comparison remains unassessed.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .fits_preview import inspect_and_render
from .irsa import IRSAError, download_cutout, search_images

Collection = Literal["spherex_dr1", "spherex_qr2", "spherex_qr3"]
DOCS_URL = "https://www.spaceappschallenge.org/2026/challenges/planet-x-and-spherex/"
WISE_POSITION = {"ra_deg": 133.7951291667, "dec_deg": -7.2451472222}
MAX_STORAGE_BYTES = 256 * 1024 * 1024
MAX_SEARCHES = 64
MAX_CUTOUTS = 32


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Position(StrictModel):
    ra_deg: float = Field(ge=0, lt=360, description="ICRS fixed sky direction, degrees")
    dec_deg: float = Field(ge=-90, le=90, description="ICRS fixed sky direction, degrees")


class SearchRequest(Position):
    radius_deg: float = Field(default=0.01, ge=0.0001, le=0.05)
    collection: Collection = "spherex_qr3"
    limit: int = Field(default=100, ge=1, le=500)


class ArchiveObservation(BaseModel):
    """The wavelength bounds describe product coverage, not a source's band."""

    model_config = ConfigDict(extra="allow", allow_inf_nan=False)
    observation_id: str = Field(pattern=r"^[a-f0-9]{16,64}$")
    source_product_id: str | None
    source_url: str
    collection: Collection
    mjd_start: float | None = None
    mjd_end: float | None = None
    wavelength_min_m: float | None = None
    wavelength_max_m: float | None = None


class SearchRecord(StrictModel):
    schema_version: Literal["0.1"] = "0.1"
    search_id: str
    query: SearchRequest
    query_url: str
    queried_at_utc: str
    truncated: bool
    observations: list[ArchiveObservation]
    total_rows: int | None = None
    interpretation: str = (
        "Footprints overlap a fixed sky direction. Object identity, usable pixels, "
        "same-wavelength coverage and temporal comparability need inspection."
    )


class PrepareRequest(StrictModel):
    observation_ids: list[str] = Field(min_length=1, max_length=2)
    size_deg: float = Field(default=0.03, ge=0.005, le=0.1)


class Assets(StrictModel):
    original_fits_url: str
    preview_png_url: str
    sha256: str
    byte_count: int


class ImageInfo(StrictModel):
    width: int
    height: int
    unit: str | None
    image_extension: Literal["IMAGE"]


class ObservationTime(StrictModel):
    date_obs: str | None
    date_end: str | None
    source_field: str | None
    end_source_field: str | None
    time_system: str | None
    time_system_source_field: str | None
    status: Literal["header_value", "not_assessed"]


class SpatialInfo(StrictModel):
    has_celestial_wcs: bool
    query_pixel_x: float | None
    query_pixel_y: float | None
    query_position_within_cutout: bool | None
    alignment_status: Literal["not_assessed"]


class WavelengthInfo(StrictModel):
    target_center_um: float | None
    target_bandwidth_um: float | None
    status: Literal["not_assessed", "spectral_wcs_evaluated"]
    reason: str
    position_basis: Literal["fixed_query_position"]


class FlagCount(StrictModel):
    name: str
    bit: int
    count: int
    description: str


class VarianceInfo(StrictModel):
    present: bool
    unit: str | None
    nonfinite_fraction: float | None
    negative_fraction: float | None


class QualityInfo(StrictModel):
    status: Literal["not_assessed"]
    nonfinite_fraction: float
    flags_present: bool
    nonzero_flag_fraction: float | None
    flag_counts: list[FlagCount]
    variance: VarianceInfo


class ExtensionInfo(StrictModel):
    index: int
    name: str
    kind: str
    shape: list[int] | None


class DisplayInfo(StrictModel):
    mode: Literal["per_image_asinh"]
    percentile_low: int
    percentile_high: int
    value_low: float
    value_high: float
    origin: Literal["lower"]
    nonfinite_pixels_displayed_as: int
    brightness_comparison_validated: Literal[False]


class Inspection(StrictModel):
    image: ImageInfo
    observation_time: ObservationTime
    spatial: SpatialInfo
    wavelength: WavelengthInfo
    quality: QualityInfo
    extensions: list[ExtensionInfo]
    display: DisplayInfo
    warnings: list[str]


class PreparedObservation(StrictModel):
    schema_version: Literal["0.1"] = "0.1"
    cutout_id: str
    search_id: str
    query_position: Position
    size_deg: float
    source: ArchiveObservation
    retrieval: dict[str, Any]
    inspection: Inspection = Field(
        description="Measured FITS image, time, WCS, wavelength and raw-flag summaries. See data-format.md."
    )
    assets: Assets
    comparison_status: Literal["not_assessed"] = "not_assessed"
    limitations: list[str] = Field(default_factory=lambda: [
        "A preview is a display rendering, not a new measurement or object identification.",
        "No cross-image registration, PSF matching, photometric comparison or motion detection was performed.",
        "Broad archive wavelength bounds do not prove the same band at the target position.",
    ])


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_app(data_dir: Path | None = None) -> FastAPI:
    storage = (data_dir or Path(os.environ.get(
        "SKYTRACE_DATA_DIR", Path(__file__).resolve().parents[1] / "data"
    ))).resolve()
    storage.mkdir(parents=True, exist_ok=True)
    searches = storage / "searches"
    cutouts = storage / "cutouts"
    searches.mkdir(exist_ok=True)
    cutouts.mkdir(exist_ok=True)
    # One archive operation at a time also keeps cache writes and budgets coherent.
    operation = threading.Lock()
    api = FastAPI(
        title="SKYTRACE local prototype", version="0.1.0",
        description="Public IRSA retrieval and honest previews; no discovery/classification service.",
    )
    api.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])
    api.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
    )

    @api.exception_handler(IRSAError)
    def upstream_error(_request: Any, exc: IRSAError) -> JSONResponse:
        return JSONResponse(status_code=502, content={
            "error": {"code": exc.code, "message": str(exc),
                      "retryable": exc.code in {"archive_timeout", "archive_unavailable"}}
        })

    def safe_path(parent: Path, identifier: str, suffix: str = "") -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", identifier):
            raise HTTPException(404, detail={"code": "not_found"})
        result = parent / (identifier + suffix)
        # Do not follow locally planted symlinks outside the configured cache.
        if not result.resolve().is_relative_to(storage):
            raise HTTPException(404, detail={"code": "not_found"})
        return result

    def checked_file(path: Path) -> Path:
        if path.is_symlink() or not path.resolve().is_relative_to(storage):
            raise HTTPException(404, detail={"code": "not_found"})
        return path

    def read_json(path: Path) -> dict[str, Any]:
        checked_file(path)
        if not path.is_file():
            raise HTTPException(404, detail={"code": "not_found"})
        return json.loads(path.read_text())

    def save_json(path: Path, value: BaseModel) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(value.model_dump_json(indent=2) + "\n")
        os.replace(temporary, path)

    def lock_and_check(reserve_bytes: int = 0) -> None:
        if not operation.acquire(blocking=False):
            raise HTTPException(429, detail={"code": "archive_busy", "message": "One retrieval is already running."})
        try:
            used = sum(p.stat().st_size for p in storage.rglob("*") if p.is_file())
            if used + reserve_bytes > MAX_STORAGE_BYTES:
                raise HTTPException(507, detail={"code": "cache_budget", "message": "Local cache budget reached."})
        except Exception:
            operation.release()
            raise

    @api.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "scope": "local_prototype", "schema_version": "0.1"}

    @api.get("/v1/targets")
    def targets() -> dict[str, Any]:
        return {"targets": [{
            "id": "wise0855", "name": "WISE 0855", **WISE_POSITION,
            "coordinate_source": DOCS_URL,
            "coordinate_note": "Converted from challenge coordinates; epoch/proper motion not propagated. Fixed-position search only.",
        }]}

    @api.post("/v1/searches", response_model=SearchRecord)
    def search(request: SearchRequest) -> SearchRecord:
        lock_and_check(10 * 1024 * 1024)
        try:
            if len(list(searches.glob("*.json"))) >= MAX_SEARCHES:
                raise HTTPException(507, detail={"code": "search_budget"})
            result = search_images(**request.model_dump())
            record = SearchRecord(
                search_id=uuid4().hex, query=request,
                query_url=result["query_url"], queried_at_utc=result["queried_at_utc"],
                truncated=result["truncated"], observations=result["observations"],
                total_rows=result.get("total_rows"),
            )
            save_json(searches / f"{record.search_id}.json", record)
            return record
        finally:
            operation.release()

    @api.get("/v1/searches/{search_id}", response_model=SearchRecord)
    def get_search(search_id: str) -> SearchRecord:
        return SearchRecord.model_validate(read_json(safe_path(searches, search_id, ".json")))

    @api.post("/v1/searches/{search_id}/cutouts", response_model=list[PreparedObservation])
    def prepare(search_id: str, request: PrepareRequest) -> list[PreparedObservation]:
        saved = get_search(search_id)
        products = {p.observation_id: p for p in saved.observations}
        if len(set(request.observation_ids)) != len(request.observation_ids):
            raise HTTPException(422, detail={"code": "duplicate_observation"})
        if any(identifier not in products for identifier in request.observation_ids):
            raise HTTPException(404, detail={"code": "observation_not_in_search"})
        lock_and_check(len(request.observation_ids) * 39 * 1024 * 1024)
        created_directories: list[Path] = []
        try:
            if len(list(cutouts.glob("*/record.json"))) + len(request.observation_ids) > MAX_CUTOUTS:
                raise HTTPException(507, detail={"code": "cutout_budget"})
            records = []
            for identifier in request.observation_ids:
                source = products[identifier]
                cutout_id = uuid4().hex
                directory = cutouts / cutout_id
                directory.mkdir()
                created_directories.append(directory)
                try:
                    retrieval = download_cutout(
                        source.source_url, saved.query.ra_deg, saved.query.dec_deg,
                        request.size_deg, directory / "source.fits",
                    )
                    inspection = inspect_and_render(
                        directory / "source.fits", directory / "preview.png",
                        saved.query.ra_deg, saved.query.dec_deg,
                    )
                    record = PreparedObservation(
                        cutout_id=cutout_id, search_id=search_id,
                        query_position=Position(ra_deg=saved.query.ra_deg, dec_deg=saved.query.dec_deg),
                        size_deg=request.size_deg, source=source, retrieval=retrieval,
                        inspection=inspection, assets=Assets(
                            original_fits_url=f"/v1/cutouts/{cutout_id}/source.fits",
                            preview_png_url=f"/v1/cutouts/{cutout_id}/preview.png",
                            sha256=retrieval["sha256"], byte_count=retrieval["byte_count"],
                        ),
                    )
                    save_json(directory / "record.json", record)
                    records.append(record)
                except Exception:
                    # Remove only this operation's unpublished, generated scratch files.
                    for artifact in directory.iterdir():
                        artifact.unlink()
                    directory.rmdir()
                    raise
            return records
        except Exception as exc:
            # A failed multi-product request leaves no inaccessible partial result.
            for directory in created_directories:
                if directory.exists():
                    shutil.rmtree(directory)
            if isinstance(exc, ValueError):
                raise HTTPException(422, detail={"code": "unsupported_fits", "message": str(exc)}) from exc
            raise
        finally:
            operation.release()

    @api.get("/v1/cutouts/{cutout_id}", response_model=PreparedObservation)
    def get_cutout(cutout_id: str) -> PreparedObservation:
        return PreparedObservation.model_validate(read_json(safe_path(cutouts, cutout_id) / "record.json"))

    @api.get("/v1/cutouts/{cutout_id}/preview.png", response_class=FileResponse)
    def preview(cutout_id: str) -> FileResponse:
        get_cutout(cutout_id)
        return FileResponse(checked_file(safe_path(cutouts, cutout_id) / "preview.png"), media_type="image/png")

    @api.get("/v1/cutouts/{cutout_id}/source.fits", response_class=FileResponse)
    def source_file(cutout_id: str) -> FileResponse:
        get_cutout(cutout_id)
        return FileResponse(checked_file(safe_path(cutouts, cutout_id) / "source.fits"), media_type="application/fits")

    return api


app = create_app()
