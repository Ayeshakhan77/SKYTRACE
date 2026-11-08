"""Synthetic fixtures test semantics; live science data is tested separately."""

import json

from astropy.io import fits
import numpy as np
from PIL import Image
import pytest

from skytrace.fits_preview import FITSPreviewError, inspect_and_render


def write_mef(path, image, *, flags=None, variance=None, with_wcs=False, with_spectral=False):
    primary = fits.PrimaryHDU(np.full((10, 10), 999, dtype=np.float32))
    science = fits.ImageHDU(np.asarray(image, dtype=np.float32), name="IMAGE")
    science.header["BUNIT"] = "MJy/sr"
    science.header["DATE-OBS"] = "2025-05-01T00:00:00"
    if with_wcs:
        science.header.update(CTYPE1="RA---TAN", CTYPE2="DEC--TAN", CRPIX1=2, CRPIX2=2, CRVAL1=133.7951291667, CRVAL2=-7.2451472222, CDELT1=-0.001, CDELT2=0.001)
    if with_spectral:
        science.header.update(CTYPE1W="LINEAR", CTYPE2W="LINEAR", CUNIT1W="um", CUNIT2W="um", CRPIX1W=2, CRPIX2W=2, CRVAL1W=1.4, CRVAL2W=0.03, CDELT1W=0.01, CDELT2W=0.001)
    hdus = [primary, science]
    if flags is not None:
        flag_hdu = fits.ImageHDU(np.asarray(flags, dtype=np.uint32), name="FLAGS")
        flag_hdu.header["HIERARCH MP_SOURCE"] = (21, "Pixel mapped to a known source")
        flag_hdu.header["HIERARCH MP_HOT"] = (10, "Hot pixel")
        hdus.append(flag_hdu)
    if variance is not None:
        variance_hdu = fits.ImageHDU(np.asarray(variance, dtype=np.float32), name="VARIANCE")
        variance_hdu.header["BUNIT"] = "MJy2/sr2"
        hdus.append(variance_hdu)
    fits.HDUList(hdus).writeto(path)


def test_science_extension_is_selected_and_png_has_lower_origin(tmp_path):
    source, preview = tmp_path / "source.fits", tmp_path / "preview.png"
    write_mef(source, [[0, 1, 2], [3, 4, 5]])
    original = source.read_bytes()
    result = inspect_and_render(source, preview, 133.7951291667, -7.2451472222)
    pixels = np.asarray(Image.open(preview))
    assert pixels.shape == (2, 3)
    assert pixels[0, 0] > pixels[-1, 0]
    assert result["image"]["image_extension"] == "IMAGE"
    assert result["image"]["unit"] == "MJy/sr"
    assert result["display"]["brightness_comparison_validated"] is False
    assert source.read_bytes() == original
    json.dumps(result, allow_nan=False)


def test_missing_metadata_stays_unassessed(tmp_path):
    source, preview = tmp_path / "source.fits", tmp_path / "preview.png"
    fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(np.ones((2, 2)), name="IMAGE")]).writeto(source)
    result = inspect_and_render(source, preview, 1, 2)
    assert result["observation_time"]["date_obs"] is None
    assert result["spatial"]["has_celestial_wcs"] is False
    assert result["spatial"]["query_position_within_cutout"] is None
    assert result["wavelength"]["target_center_um"] is None
    assert result["quality"]["flags_present"] is False
    assert result["quality"]["nonzero_flag_fraction"] is None
    assert result["quality"]["status"] == "not_assessed"


def test_nonzero_flags_are_reported_without_becoming_an_unusable_fraction(tmp_path):
    source, preview = tmp_path / "source.fits", tmp_path / "preview.png"
    write_mef(source, [[1, np.nan], [3, 4]], flags=[[1 << 21, (1 << 21) | (1 << 10)], [0, 0]], variance=[[1, 1], [-1, np.nan]])
    result = inspect_and_render(source, preview, 1, 2)
    quality = result["quality"]
    assert quality["nonfinite_fraction"] == 0.25
    assert quality["nonzero_flag_fraction"] == 0.5
    assert {item["name"]: item["count"] for item in quality["flag_counts"]} == {"MP_HOT": 1, "MP_SOURCE": 2}
    assert "unusable_fraction" not in quality
    assert quality["status"] == "not_assessed"
    assert quality["variance"]["negative_fraction"] == 0.25
    assert quality["variance"]["nonfinite_fraction"] == 0.25
    assert np.asarray(Image.open(preview))[1, 1] == 0
    json.dumps(result, allow_nan=False)


def test_spectral_units_are_converted_at_query_position_without_extrapolation(tmp_path):
    source, preview = tmp_path / "source.fits", tmp_path / "preview.png"
    write_mef(source, np.arange(9).reshape(3, 3), with_wcs=True, with_spectral=True)
    result = inspect_and_render(source, preview, 133.7951291667, -7.2451472222)
    assert result["spatial"]["query_position_within_cutout"] is True
    assert result["wavelength"]["status"] == "spectral_wcs_evaluated"
    assert result["wavelength"]["target_center_um"] == pytest.approx(1.4)
    assert result["wavelength"]["target_bandwidth_um"] == pytest.approx(0.03)
    outside = inspect_and_render(source, preview, 133.9, -7.2451472222)
    assert outside["spatial"]["query_position_within_cutout"] is False
    assert outside["wavelength"]["target_center_um"] is None


@pytest.mark.parametrize("image", [np.full((2, 2), np.nan), np.full((2, 2), np.inf)])
def test_no_finite_data_does_not_create_preview(tmp_path, image):
    source, preview = tmp_path / "source.fits", tmp_path / "preview.png"
    write_mef(source, image)
    with pytest.raises(FITSPreviewError) as exc:
        inspect_and_render(source, preview, 1, 2)
    assert exc.value.code == "no_finite_pixels"
    assert not preview.exists()


def test_primary_image_cannot_substitute_for_named_science_extension(tmp_path):
    source = tmp_path / "source.fits"
    fits.PrimaryHDU(np.ones((2, 2))).writeto(source)
    with pytest.raises(FITSPreviewError) as exc:
        inspect_and_render(source, tmp_path / "preview.png", 1, 2)
    assert exc.value.code == "missing_image_extension"


def test_oversize_shape_rejected_before_preview(tmp_path):
    source = tmp_path / "source.fits"
    write_mef(source, np.ones((1, 4097)))
    with pytest.raises(FITSPreviewError) as exc:
        inspect_and_render(source, tmp_path / "preview.png", 1, 2)
    assert exc.value.code == "image_too_large"


def test_invalid_source_and_coordinates_are_structured_errors(tmp_path):
    source = tmp_path / "bad.fits"
    source.write_text("not a FITS file")
    with pytest.raises(FITSPreviewError) as exc:
        inspect_and_render(source, tmp_path / "preview.png", 1, 2)
    assert exc.value.code == "invalid_fits"
    with pytest.raises(FITSPreviewError) as exc:
        inspect_and_render(source, tmp_path / "preview.png", np.nan, 2)
    assert exc.value.code == "invalid_position"


def test_source_path_cannot_be_overwritten(tmp_path):
    source = tmp_path / "source.fits"
    write_mef(source, np.ones((2, 2)))
    with pytest.raises(FITSPreviewError) as exc:
        inspect_and_render(source, source, 1, 2)
    assert exc.value.code == "source_overwrite"


def test_extreme_finite_float64_values_keep_preview_and_json_finite(tmp_path):
    source, preview = tmp_path / "source.fits", tmp_path / "preview.png"
    values = np.array([[-1e308, 0], [1e308, 1e307]], dtype=np.float64)
    fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(values, name="IMAGE")]).writeto(source)
    with np.errstate(over="raise", invalid="raise"):
        result = inspect_and_render(source, preview, 1, 2)
    json.dumps(result, allow_nan=False)
    assert result["display"]["value_low"] < 0 < result["display"]["value_high"]
    assert np.asarray(Image.open(preview)).min() == 0
    assert np.asarray(Image.open(preview)).max() == 255


def test_extension_count_is_bounded(tmp_path):
    source = tmp_path / "source.fits"
    hdus = [fits.PrimaryHDU(), fits.ImageHDU(np.ones((2, 2)), name="IMAGE")]
    hdus.extend(fits.ImageHDU(np.zeros((1, 1))) for _ in range(31))
    fits.HDUList(hdus).writeto(source)
    with pytest.raises(FITSPreviewError) as exc:
        inspect_and_render(source, tmp_path / "preview.png", 1, 2)
    assert exc.value.code == "too_many_extensions"
