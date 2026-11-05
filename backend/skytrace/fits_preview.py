"""Inspect an archive MEF and make a display-only preview of its IMAGE plane.

This module does not identify objects, register observations, calibrate images, or
classify a change. The original FITS file remains the source of scientific data.
"""

from __future__ import annotations

from numbers import Integral
from pathlib import Path
from typing import Any
from uuid import uuid4
import warnings

import astropy.units as u
from astropy.io import fits
from astropy.wcs import WCS
import numpy as np
from PIL import Image


MAX_FITS_BYTES = 32 * 1024 * 1024
MAX_AXIS = 4096
MAX_PIXELS = 4_500_000
MAX_HDUS = 32


class FITSPreviewError(ValueError):
    """A source file cannot safely supply the requested science preview."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if np.isfinite(number) else None


def _bounded_shape(hdu: Any, label: str) -> tuple[int, int]:
    shape = hdu.shape
    if not shape or len(shape) != 2:
        raise FITSPreviewError("invalid_image_shape", f"{label} must be a two-dimensional image.")
    height, width = (int(value) for value in shape)
    if min(width, height) < 1 or max(width, height) > MAX_AXIS or width * height > MAX_PIXELS:
        raise FITSPreviewError("image_too_large", f"{label} exceeds the supported image dimensions.")
    return height, width


def _time_metadata(image_header: fits.Header, primary_header: fits.Header) -> dict[str, Any]:
    def find(keys: tuple[str, ...]) -> tuple[str | None, str | None]:
        for label, header in (("IMAGE", image_header), ("PRIMARY", primary_header)):
            for key in keys:
                value = header.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip(), f"{label}.{key}"
        return None, None

    start, start_field = find(("DATE-OBS", "DATE-BEG"))
    end, end_field = find(("DATE-END",))
    timesys, timesys_field = find(("TIMESYS",))
    return {
        "date_obs": start,
        "date_end": end,
        "source_field": start_field,
        "end_source_field": end_field,
        "time_system": timesys,
        "time_system_source_field": timesys_field,
        "status": "header_value" if start is not None else "not_assessed",
    }


def _spatial_metadata(
    image_hdu: Any, hdul: fits.HDUList, ra_deg: float, dec_deg: float, width: int, height: int
) -> tuple[dict[str, Any], list[str]]:
    result: dict[str, Any] = {
        "has_celestial_wcs": False,
        "query_pixel_x": None,
        "query_pixel_y": None,
        "query_position_within_cutout": None,
        "alignment_status": "not_assessed",
    }
    messages: list[str] = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            celestial = WCS(image_hdu.header, fobj=hdul).celestial
            if celestial.has_celestial:
                result["has_celestial_wcs"] = True
                x, y = celestial.all_world2pix([[ra_deg, dec_deg]], 0)[0]
                x_value, y_value = _finite_float(x), _finite_float(y)
                result["query_pixel_x"] = x_value
                result["query_pixel_y"] = y_value
                if x_value is not None and y_value is not None:
                    result["query_position_within_cutout"] = bool(
                        0 <= x_value < width and 0 <= y_value < height
                    )
        except Exception as exc:  # Malformed WCS must not turn a display preview into an assertion.
            messages.append(f"Spatial WCS could not be evaluated: {str(exc)[:240]}")
        messages.extend(f"WCS warning: {str(item.message)[:240]}" for item in caught)
    if not result["has_celestial_wcs"]:
        messages.append("No usable celestial WCS was found; query-position coverage is not assessed.")
    elif result["query_position_within_cutout"] is False:
        messages.append("The fixed query position falls outside this cutout's pixel bounds.")
    return result, messages


def _spectral_metadata(
    image_hdu: Any, hdul: fits.HDUList, spatial: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    result: dict[str, Any] = {
        "target_center_um": None,
        "target_bandwidth_um": None,
        "status": "not_assessed",
        "reason": "No usable alternate spectral WCS W was evaluated.",
        "position_basis": "fixed_query_position",
    }
    messages: list[str] = []
    if spatial["query_position_within_cutout"] is not True:
        result["reason"] = "The query position is not established within this image; no spectral extrapolation was performed."
        return result, messages
    if "CTYPE1W" not in image_hdu.header or "CTYPE2W" not in image_hdu.header:
        result["reason"] = "The IMAGE header does not declare the expected alternate spectral WCS W."
        return result, messages
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            spectral = WCS(image_hdu.header, fobj=hdul, key="W")
            # IRSA's tutorial specifies that SIP distortion is not part of WCS W.
            spectral.sip = None
            values = spectral.pixel_to_world_values(spatial["query_pixel_x"], spatial["query_pixel_y"])
            units = spectral.world_axis_units
            if len(values) != 2 or len(units) != 2 or not all(units):
                raise ValueError("Expected two spectral world axes with declared units.")
            center = _finite_float((float(values[0]) * u.Unit(units[0])).to_value(u.um))
            bandwidth = _finite_float((float(values[1]) * u.Unit(units[1])).to_value(u.um))
            if center is None or bandwidth is None or center <= 0 or bandwidth <= 0:
                raise ValueError("Spectral WCS did not return a positive finite wavelength and bandwidth.")
            result.update(
                target_center_um=center,
                target_bandwidth_um=bandwidth,
                status="spectral_wcs_evaluated",
                reason="WCS W evaluated at the fixed query position, using declared axis units.",
            )
        except Exception as exc:
            result["reason"] = f"Spectral WCS could not be evaluated: {str(exc)[:240]}"
        messages.extend(f"Spectral WCS warning: {str(item.message)[:240]}" for item in caught)
    return result, messages


def _quality_metadata(
    hdul: fits.HDUList, shape: tuple[int, int], finite: np.ndarray
) -> tuple[dict[str, Any], list[str]]:
    quality: dict[str, Any] = {
        "status": "not_assessed",
        "nonfinite_fraction": float(1 - np.count_nonzero(finite) / finite.size),
        "flags_present": "FLAGS" in hdul,
        "nonzero_flag_fraction": None,
        "flag_counts": [],
        "variance": {"present": "VARIANCE" in hdul, "unit": None, "nonfinite_fraction": None, "negative_fraction": None},
    }
    messages = [
        "Flag counts describe the raw bitmask. A nonzero flag is not automatically an unusable pixel; SOURCE and other flags have different meanings.",
        "Image quality has not been approved for scientific comparison; flags and variance require interpretation.",
    ]
    if "FLAGS" in hdul:
        flag_hdu = hdul["FLAGS"]
        if _bounded_shape(flag_hdu, "FLAGS") != shape:
            messages.append("FLAGS dimensions differ from IMAGE; no pixel-level flag summary was calculated.")
        else:
            flags = np.asarray(flag_hdu.data)
            if flags.dtype.kind not in "iu":
                messages.append("FLAGS is not an integer bitmap; no flag counts were calculated.")
            else:
                quality["nonzero_flag_fraction"] = float(np.count_nonzero(flags) / flags.size)
                bitmap = flags.astype(np.uint64, copy=False)
                for key in flag_hdu.header:
                    normalized = key.upper().replace(" ", "_")
                    bit = flag_hdu.header[key]
                    if not normalized.startswith("MP_") or isinstance(bit, bool) or not isinstance(bit, Integral):
                        continue
                    bit = int(bit)
                    if not 0 <= bit < min(64, flags.dtype.itemsize * 8):
                        continue
                    quality["flag_counts"].append(
                        {
                            "name": normalized,
                            "bit": bit,
                            "count": int(np.count_nonzero(bitmap & np.uint64(1 << bit))),
                            "description": str(flag_hdu.header.comments[key]),
                        }
                    )
                quality["flag_counts"].sort(key=lambda item: (item["bit"], item["name"]))
                if not quality["flag_counts"]:
                    messages.append("FLAGS has no usable MP_* definitions in its header; bit meanings remain unknown.")
    else:
        messages.append("No FLAGS extension is present; pixel-level flags are unknown, not clear.")
    if "VARIANCE" in hdul:
        variance_hdu = hdul["VARIANCE"]
        quality["variance"]["unit"] = str(variance_hdu.header.get("BUNIT", "")) or None
        if _bounded_shape(variance_hdu, "VARIANCE") != shape:
            messages.append("VARIANCE dimensions differ from IMAGE; no variance summary was calculated.")
        else:
            variance = np.asarray(variance_hdu.data)
            if variance.dtype.kind in "iuf":
                quality["variance"]["nonfinite_fraction"] = float(1 - np.count_nonzero(np.isfinite(variance)) / variance.size)
                quality["variance"]["negative_fraction"] = float(np.count_nonzero(variance < 0) / variance.size)
            else:
                messages.append("VARIANCE is not a real-valued array; no variance summary was calculated.")
    return quality, messages


def inspect_and_render(
    fits_path: Path, preview_path: Path, ra_deg: float, dec_deg: float
) -> dict[str, Any]:
    """Create an orientation-preserving grayscale PNG and return cautious metadata.

    Raises FITSPreviewError (a ValueError) with a stable ``code`` on invalid input.
    The stretch is computed separately for this image, so it must not be used to
    measure brightness differences between images.
    """
    fits_path, preview_path = Path(fits_path), Path(preview_path)
    if fits_path.resolve() == preview_path.resolve():
        raise FITSPreviewError("source_overwrite", "The preview path must differ from the source FITS path.")
    ra, dec = _finite_float(ra_deg), _finite_float(dec_deg)
    if ra is None or dec is None or not 0 <= ra < 360 or not -90 <= dec <= 90:
        raise FITSPreviewError("invalid_position", "A finite RA in [0, 360) and declination in [-90, 90] are required.")
    try:
        size = fits_path.stat().st_size
    except OSError as exc:
        raise FITSPreviewError("unreadable_fits", "The FITS source could not be opened.") from exc
    if size > MAX_FITS_BYTES:
        raise FITSPreviewError("file_too_large", "The FITS source exceeds the 32 MiB limit.")
    try:
        with fits.open(fits_path, memmap=False, lazy_load_hdus=True) as hdul:
            extension_summary = []
            for index, hdu in enumerate(hdul):
                if index >= MAX_HDUS:
                    raise FITSPreviewError("too_many_extensions", "The FITS source exceeds the 32-extension limit.")
                extension_summary.append(
                    {"index": index, "name": hdu.name, "kind": type(hdu).__name__, "shape": [int(value) for value in hdu.shape] if getattr(hdu, "shape", None) else None}
                )
            if "IMAGE" not in hdul:
                raise FITSPreviewError("missing_image_extension", "A SPHEREx IMAGE extension is required; the primary plane is not a substitute.")
            image_hdu = hdul["IMAGE"]
            shape = _bounded_shape(image_hdu, "IMAGE")
            image = np.asarray(image_hdu.data)
            if image.dtype.kind not in "iuf":
                raise FITSPreviewError("invalid_image_type", "IMAGE must contain real numeric science pixels.")
            finite = np.isfinite(image)
            if not finite.any():
                raise FITSPreviewError("no_finite_pixels", "IMAGE has no finite pixels to display.")
            height, width = shape
            spatial, spatial_warnings = _spatial_metadata(image_hdu, hdul, ra, dec, width, height)
            wavelength, wavelength_warnings = _spectral_metadata(image_hdu, hdul, spatial)
            quality, quality_warnings = _quality_metadata(hdul, shape, finite)
            # Scale first: interpolation/subtraction can overflow even when every
            # source float64 value is finite (e.g. -1e308 and +1e308).
            finite_values = image[finite].astype(np.float64)
            magnitude = max(float(np.max(np.abs(finite_values))), np.finfo(np.float64).tiny)
            scaled_values = finite_values / magnitude
            lower_scaled, upper_scaled = np.percentile(scaled_values, [1, 99])
            lower, upper = float(lower_scaled * magnitude), float(upper_scaled * magnitude)
            normalized = np.zeros(shape, dtype=np.float64)
            if upper_scaled > lower_scaled:
                normalized[finite] = np.clip((scaled_values - lower_scaled) / (upper_scaled - lower_scaled), 0, 1)
            # A monotonic display stretch preserves order; it is not photometry.
            pixels = np.rint(np.arcsinh(10 * normalized) / np.arcsinh(10) * 255).astype(np.uint8)
            result = {
                "image": {"width": width, "height": height, "unit": str(image_hdu.header.get("BUNIT", "")) or None, "image_extension": "IMAGE"},
                "observation_time": _time_metadata(image_hdu.header, hdul[0].header),
                "spatial": spatial,
                "wavelength": wavelength,
                "quality": quality,
                "extensions": extension_summary,
                "display": {"mode": "per_image_asinh", "percentile_low": 1, "percentile_high": 99, "value_low": lower, "value_high": upper, "origin": "lower", "nonfinite_pixels_displayed_as": 0, "brightness_comparison_validated": False},
                "warnings": list(dict.fromkeys([
                    "This is a display-only preview; the source FITS remains the scientific data product.",
                    "The query is a fixed sky position; object identity and proper-motion tracking have not been confirmed.",
                    "WCS alignment, PSF matching, spectral compatibility and photometric comparison have not been assessed.",
                    "The display stretch is per image; preview brightness must not be used to measure changes.",
                    *spatial_warnings, *wavelength_warnings, *quality_warnings,
                ])),
            }
    except FITSPreviewError:
        raise
    except Exception as exc:
        raise FITSPreviewError("invalid_fits", f"FITS inspection failed: {str(exc)[:240]}") from exc
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = preview_path.with_name(f".{preview_path.name}.{uuid4().hex}.tmp")
    try:
        Image.fromarray(np.flipud(pixels)).save(temporary, format="PNG")
        temporary.replace(preview_path)
    finally:
        temporary.unlink(missing_ok=True)
    return result
