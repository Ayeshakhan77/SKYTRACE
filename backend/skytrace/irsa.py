"""Bounded public SPHEREx SIA queries and spatial FITS cutout downloads."""
from __future__ import annotations

import hashlib
import io
import math
import numbers
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit
from xml.etree import ElementTree

import httpx
import numpy as np
from astropy.io.votable import parse

SIA_URL = "https://irsa.ipac.caltech.edu/SIA"
COLLECTIONS = frozenset({"spherex_dr1", "spherex_dr1_deep", "spherex_qr2", "spherex_qr2_deep", "spherex_qr3", "spherex_qr3_deep"})
MAX_METADATA_BYTES = 10 * 1024 * 1024
MAX_CUTOUT_BYTES = 32 * 1024 * 1024
TIMEOUT = httpx.Timeout(60.0, connect=15.0, pool=10.0)


class IRSAError(Exception):
    """An archive or validation failure safe for an API error response."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _number(value: Any, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise IRSAError("invalid_request", f"{name} must be a finite number.")
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise IRSAError("invalid_request", f"{name} must be a finite number.") from exc
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise IRSAError("invalid_request", f"{name} must be in [{minimum}, {maximum}].")
    return result


def _position(ra_deg: float, dec_deg: float) -> tuple[float, float]:
    ra = _number(ra_deg, "ra_deg", 0, 360)
    dec = _number(dec_deg, "dec_deg", -90, 90)
    return (0.0 if ra == 360 else ra), dec


def validate_source_url(source_url: str) -> str:
    """Accept only unambiguous on-premises SPHEREx spectral-image FITS URLs."""
    if not isinstance(source_url, str):
        raise IRSAError("unsafe_source_url", "Invalid archive source URL.")
    try:
        parsed = urlsplit(source_url)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise IRSAError("unsafe_source_url", "Invalid archive source URL.") from exc
    if (
        parsed.scheme != "https" or parsed.hostname != "irsa.ipac.caltech.edu"
        or port is not None or parsed.username is not None or parsed.password is not None
        or parsed.query or parsed.fragment
        or not parsed.path.startswith("/ibe/data/spherex/")
        or not parsed.path.endswith(".fits")
        or any(part in {".", ".."} for part in parsed.path.split("/"))
        or "%" in parsed.path or "\\" in source_url
        or any(ord(char) < 33 or ord(char) == 127 for char in source_url)
    ):
        raise IRSAError("unsafe_source_url", "Source must be a public IRSA SPHEREx FITS URL.")
    pieces = parsed.path.split("/")
    if len(pieces) < 8 or pieces[4] not in {"dr1", "qr2", "qr3"} or pieces[5] != "level2":
        raise IRSAError("unsafe_source_url", "Source must be an IRSA DR1/QR2/QR3 level2 product.")
    return source_url


def validate_capture_request(request: dict[str, Any], ra_deg: float, dec_deg: float,
                             radius_deg: float, collection: str) -> None:
    """Require reused metadata to have the exact intended SIA query provenance."""
    try:
        if request.get("status_code") != 200 or not isinstance(request.get("url"), str):
            raise ValueError("Capture did not record a successful request URL")
        url = urlsplit(request["url"])
        if (url.scheme != "https" or url.hostname != "irsa.ipac.caltech.edu"
                or url.path != "/SIA" or url.port is not None or url.username is not None
                or url.password is not None or url.fragment):
            raise ValueError("Capture is not an IRSA SIA request")
        params = parse_qs(url.query, keep_blank_values=True, strict_parsing=True)
        if set(params) != {"COLLECTION", "POS", "RESPONSEFORMAT"} or any(len(values) != 1 for values in params.values()):
            raise ValueError("Capture has ambiguous or unexpected query parameters")
        if params["COLLECTION"][0] != collection or params["RESPONSEFORMAT"][0] != "VOTABLE":
            raise ValueError("Capture collection or response format differs from the test")
        expected = (*_position(ra_deg, dec_deg), _number(radius_deg, "radius_deg", 0.000001, 0.05))

        def check_position(value: str) -> None:
            pieces = value.split()
            if len(pieces) != 4 or pieces[0].lower() != "circle":
                raise ValueError("Capture POS is not a circle")
            actual = tuple(float(piece) for piece in pieces[1:])
            if any(not math.isfinite(value) or not math.isclose(value, wanted, rel_tol=0, abs_tol=1e-9)
                   for value, wanted in zip(actual, expected, strict=True)):
                raise ValueError("Capture coordinates or radius differ from the test")

        check_position(params["POS"][0])
        if "params" in request:
            recorded = request["params"]
            if not isinstance(recorded, dict) or set(recorded) != set(params):
                raise ValueError("Capture parameter envelope differs from its URL")
            if recorded.get("COLLECTION") != collection or recorded.get("RESPONSEFORMAT") != "VOTABLE":
                raise ValueError("Capture parameter envelope differs from its URL")
            check_position(recorded["POS"])
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, IRSAError) as exc:
        raise IRSAError("invalid_capture", "Saved metadata query does not match this target, radius and collection.") from exc


def _json_value(value: Any) -> Any:
    if np.ma.is_masked(value):
        return None
    if isinstance(value, np.ndarray):
        return [_json_value(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _nullable_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def parse_metadata(content: bytes, collection: str, limit: int) -> tuple[list[dict[str, Any]], int, bool]:
    """Read result tables by FIELD names, not archive-internal FIELD IDs."""
    if collection not in COLLECTIONS:
        raise IRSAError("invalid_request", "Unsupported SPHEREx collection.")
    if len(content) > MAX_METADATA_BYTES:
        raise IRSAError("metadata_too_large", "IRSA metadata exceeded the size limit.")
    upper = content.upper()
    if b"\x00" in content or b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise IRSAError("invalid_metadata", "DTD/entity declarations are not supported.")
    try:
        root = ElementTree.fromstring(content)
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1].upper() == "STREAM" and any(
                key.rsplit("}", 1)[-1].lower() == "href" for key in element.attrib
            ):
                raise IRSAError("invalid_metadata", "External VOTable data streams are not supported.")
        statuses = [el for el in root.iter() if el.tag.rsplit("}", 1)[-1] == "INFO" and el.get("name") == "QUERY_STATUS"]
        for status in statuses:
            if status.get("value", "").upper() == "ERROR":
                raise IRSAError("archive_query_error", (status.text or "IRSA rejected the query.").strip()[:300])
        overflow = any(status.get("value", "").upper() == "OVERFLOW" for status in statuses)
        parsed = parse(io.BytesIO(content), verify="warn")
        tables = [table.to_table(use_names_over_ids=True) for table in parsed.iter_tables()]
        table = next((table for table in tables if "access_url" in table.colnames), None)
        if table is None:
            raise IRSAError("invalid_metadata", "IRSA response has no image-result table.")
        observations = []
        for row in table[:limit]:
            raw = {name: _json_value(row[name]) for name in table.colnames}
            source_url = raw.get("access_url")
            if not isinstance(source_url, str):
                raise IRSAError("invalid_metadata", "IRSA image row has no source URL.")
            validate_source_url(source_url)
            expected_release = collection.split("_")[1]
            if urlsplit(source_url).path.split("/")[4] != expected_release:
                raise IRSAError("collection_mismatch", "IRSA source product release differs from the requested collection.")
            if raw.get("obs_collection") not in (None, "", collection):
                raise IRSAError("collection_mismatch", "IRSA row collection differs from the requested collection.")
            observations.append({
                "observation_id": hashlib.sha256(source_url.encode()).hexdigest()[:24],
                "source_url": source_url,
                "source_product_id": raw.get("obs_publisher_did") or raw.get("obs_id"),
                "collection": collection,
                "mjd_start": _nullable_float(raw.get("t_min")),
                "mjd_end": _nullable_float(raw.get("t_max")),
                "wavelength_min_m": _nullable_float(raw.get("em_min")),
                "wavelength_max_m": _nullable_float(raw.get("em_max")),
                "bandpass_name": raw.get("energy_bandpassname"),
                "metadata": raw,
            })
        return observations, len(table), overflow
    except IRSAError:
        raise
    except Exception as exc:
        raise IRSAError("invalid_metadata", "Could not read the IRSA VOTable response.") from exc


def _read_bounded(response: httpx.Response, maximum: int, code: str) -> bytes:
    if response.status_code != 200:
        raise IRSAError("archive_http_error", f"IRSA returned HTTP {response.status_code}.")
    content = bytearray()
    for chunk in response.iter_bytes():
        content.extend(chunk)
        if len(content) > maximum:
            raise IRSAError(code, "IRSA response exceeded the configured byte limit.")
    return bytes(content)


def search_images(ra_deg: float, dec_deg: float, radius_deg: float = 0.01,
                  collection: str = "spherex_qr3", limit: int = 100,
                  *, raw_path: Path | None = None) -> dict[str, Any]:
    ra, dec = _position(ra_deg, dec_deg)
    radius = _number(radius_deg, "radius_deg", 0.000001, 0.05)
    if collection not in COLLECTIONS:
        raise IRSAError("invalid_request", "Unsupported SPHEREx collection.")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise IRSAError("invalid_request", "limit must be an integer in [1, 500].")
    params = {"COLLECTION": collection, "POS": f"circle {ra:.10f} {dec:.10f} {radius:.10f}", "RESPONSEFORMAT": "VOTABLE"}
    query_url = SIA_URL + "?" + urlencode(params)
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=False) as client:
            with client.stream("GET", SIA_URL, params=params) as response:
                content = _read_bounded(response, MAX_METADATA_BYTES, "metadata_too_large")
    except httpx.TimeoutException as exc:
        raise IRSAError("archive_timeout", "IRSA did not respond within the timeout.") from exc
    except httpx.HTTPError as exc:
        raise IRSAError("archive_unavailable", "Could not reach the IRSA archive.") from exc
    if raw_path is not None:
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(content)
    observations, total, overflow = parse_metadata(content, collection, limit)
    return {"query_url": query_url, "queried_at_utc": _utc_now(), "total_rows": total,
            "truncated": overflow or total > limit, "upstream_truncated": overflow,
            "observations": observations}


def download_cutout(source_url: str, ra_deg: float, dec_deg: float,
                    size_deg: float, destination: Path) -> dict[str, Any]:
    source_url = validate_source_url(source_url)
    ra, dec = _position(ra_deg, dec_deg)
    size = _number(size_deg, "size_deg", 0.001, 0.1)
    url = source_url + "?" + urlencode({"center": f"{ra:.10f},{dec:.10f}", "size": f"{size:.6f}"})
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.part")
    digest = hashlib.sha256()
    byte_count = 0
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=False) as client:
            with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise IRSAError("archive_http_error", f"IRSA returned HTTP {response.status_code}.")
                with temporary.open("xb") as handle:
                    for chunk in response.iter_bytes():
                        byte_count += len(chunk)
                        if byte_count > MAX_CUTOUT_BYTES:
                            raise IRSAError("cutout_too_large", "IRSA cutout exceeded the 32 MiB limit.")
                        handle.write(chunk)
                        digest.update(chunk)
        with temporary.open("rb") as handle:
            if handle.read(9) != b"SIMPLE  =":
                raise IRSAError("invalid_fits", "IRSA did not return a FITS file.")
        os.replace(temporary, destination)
    except httpx.TimeoutException as exc:
        raise IRSAError("archive_timeout", "IRSA cutout request timed out.") from exc
    except httpx.HTTPError as exc:
        raise IRSAError("archive_unavailable", "Could not retrieve the IRSA cutout.") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return {"url": url, "byte_count": byte_count, "sha256": digest.hexdigest(), "retrieved_at_utc": _utc_now()}
