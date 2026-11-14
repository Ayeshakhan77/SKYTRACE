"""Archive parsing, resource bounds and URL safety without network access."""
from __future__ import annotations

import io
from pathlib import Path
from urllib.parse import urlencode

import httpx
import pytest
from astropy.io import fits

from skytrace import irsa

SOURCE = "https://irsa.ipac.caltech.edu/ibe/data/spherex/qr2/level2/2025W19_1B/l2b-v20-2025-242/1/example.fits"


def votable(source: str = SOURCE, status: str = "OK", rows: bool = True,
            obs_collection: str | None = None) -> bytes:
    extra_value = f"<TD>{obs_collection}</TD>" if obs_collection is not None else ""
    extra_field = '<FIELD ID="col_4" name="obs_collection" datatype="char" arraysize="*"/>' if obs_collection is not None else ""
    row = f"<TR><TD>{source}</TD><TD>60801.5</TD><TD>NaN</TD><TD>SPHEREx-D1</TD>{extra_value}</TR>" if rows else ""
    return f'''<?xml version="1.0"?><VOTABLE version="1.3" xmlns="http://www.ivoa.net/xml/VOTable/v1.3">
    <RESOURCE type="results"><INFO name="QUERY_STATUS" value="{status}">test status</INFO><TABLE>
    <FIELD ID="col_0" name="access_url" datatype="char" arraysize="*"/>
    <FIELD ID="col_1" name="t_min" datatype="double"/>
    <FIELD ID="col_2" name="em_min" datatype="double"/>
    <FIELD ID="col_3" name="energy_bandpassname" datatype="char" arraysize="*"/>
    {extra_field}
    <DATA><TABLEDATA>{row}</TABLEDATA></DATA></TABLE></RESOURCE></VOTABLE>'''.encode()


def install_transport(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    real_client = httpx.Client
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(irsa.httpx, "Client", lambda **kwargs: real_client(transport=transport, **kwargs))


def test_field_names_and_json_finite_values() -> None:
    rows, total, overflow = irsa.parse_metadata(votable(), "spherex_qr2", 10)
    assert total == 1 and not overflow
    assert rows[0]["source_url"] == SOURCE
    assert rows[0]["mjd_start"] == 60801.5
    assert rows[0]["wavelength_min_m"] is None
    assert rows[0]["metadata"]["em_min"] is None
    assert len(rows[0]["observation_id"]) == 24


def test_zero_rows_is_a_valid_result() -> None:
    assert irsa.parse_metadata(votable(rows=False), "spherex_qr3", 10) == ([], 0, False)


@pytest.mark.parametrize("body", [votable(source=SOURCE.replace("/qr2/", "/qr3/")),
                                   votable(obs_collection="spherex_qr3"),
                                   votable(obs_collection="spherex_qr2_deep")])
def test_result_collection_and_product_release_must_match_query(body: bytes) -> None:
    with pytest.raises(irsa.IRSAError) as error:
        irsa.parse_metadata(body, "spherex_qr2", 10)
    assert error.value.code == "collection_mismatch"


def capture_request(**overrides) -> dict:
    params = {"COLLECTION": "spherex_qr2", "POS": "circle 133.7951291667 -7.2451472222 0.01", "RESPONSEFORMAT": "VOTABLE"}
    return {"status_code": 200, "url": irsa.SIA_URL + "?" + urlencode(params), **overrides}


def test_reused_capture_matches_target_with_circle_whitespace() -> None:
    request = capture_request()
    request["url"] = request["url"].replace("POS=circle+", "POS=circle+++%09")
    irsa.validate_capture_request(request, 133.7951291667, -7.2451472222, 0.01, "spherex_qr2")


@pytest.mark.parametrize("replace_old,replace_new", [
    ("133.7951291667", "100"), ("-7.2451472222", "0"), ("0.01", "0.02"),
    ("spherex_qr2", "spherex_qr3"), ("https://", "http://"),
    ("irsa.ipac.caltech.edu", "localhost"), ("/SIA?", "/other?"),
    (".edu/", ".edu:443/"), ("VOTABLE", "HTML"), ("circle", "polygon"),
])
def test_mismatched_reused_capture_rejected(replace_old: str, replace_new: str) -> None:
    request = capture_request()
    request["url"] = request["url"].replace(replace_old, replace_new)
    with pytest.raises(irsa.IRSAError) as error:
        irsa.validate_capture_request(request, 133.7951291667, -7.2451472222, 0.01, "spherex_qr2")
    assert error.value.code == "invalid_capture"


def test_reused_capture_envelope_and_duplicate_query_rejected() -> None:
    request = capture_request()
    request["params"] = {"COLLECTION": "spherex_qr3", "POS": "circle 0 0 0.01", "RESPONSEFORMAT": "VOTABLE"}
    with pytest.raises(irsa.IRSAError):
        irsa.validate_capture_request(request, 133.7951291667, -7.2451472222, 0.01, "spherex_qr2")
    request = capture_request()
    request["url"] += "&COLLECTION=spherex_qr2"
    with pytest.raises(irsa.IRSAError):
        irsa.validate_capture_request(request, 133.7951291667, -7.2451472222, 0.01, "spherex_qr2")


def test_query_error_and_overflow() -> None:
    with pytest.raises(irsa.IRSAError) as error:
        irsa.parse_metadata(votable(status="ERROR"), "spherex_qr2", 10)
    assert error.value.code == "archive_query_error"
    assert irsa.parse_metadata(votable(status="OVERFLOW"), "spherex_qr2", 10)[2]


@pytest.mark.parametrize("body", [b"<html>unavailable</html>", b"not XML", b'<!DOCTYPE VOTABLE [<!ENTITY test "x">]><VOTABLE/>' ])
def test_invalid_metadata_is_structured(body: bytes) -> None:
    with pytest.raises(irsa.IRSAError) as error:
        irsa.parse_metadata(body, "spherex_qr2", 10)
    assert error.value.code == "invalid_metadata"


@pytest.mark.parametrize("attribute", ['href="file:///etc/passwd"', 'xmlns:x="http://www.w3.org/1999/xlink" x:href="http://127.0.0.1/private"'])
def test_external_stream_rejected_before_astropy(monkeypatch: pytest.MonkeyPatch, attribute: str) -> None:
    parse_calls = []
    def unexpected_parse(*args, **kwargs):
        parse_calls.append(True)
        raise AssertionError("Astropy must not parse an external data stream")
    monkeypatch.setattr(irsa, "parse", unexpected_parse)
    content = f'<VOTABLE><RESOURCE><TABLE><DATA><BINARY><STREAM {attribute}/></BINARY></DATA></TABLE></RESOURCE></VOTABLE>'.encode()
    with pytest.raises(irsa.IRSAError) as error:
        irsa.parse_metadata(content, "spherex_qr2", 10)
    assert error.value.code == "invalid_metadata"
    assert parse_calls == []


@pytest.mark.parametrize("url", [
    "http://irsa.ipac.caltech.edu/ibe/data/spherex/qr2/level2/a/b.fits",
    "https://localhost/ibe/data/spherex/qr2/level2/a/b.fits",
    "https://irsa.ipac.caltech.edu.evil.test/ibe/data/spherex/qr2/level2/a/b.fits",
    SOURCE.replace("https://", "https://user:pass@"),
    SOURCE.replace(".edu/", ".edu:443/"), SOURCE + "?center=0,0", SOURCE + "#fragment",
    SOURCE.replace("/level2/", "/level2/../"),
    SOURCE.replace("/level2/", "/level2/%2e%2e/"),
    SOURCE.replace("/spherex/qr2/", "/other/qr2/"), SOURCE.replace(".fits", ".txt"),
])
def test_disallow_untrusted_download_sources(url: str) -> None:
    with pytest.raises(irsa.IRSAError) as error:
        irsa.validate_source_url(url)
    assert error.value.code == "unsafe_source_url"


@pytest.mark.parametrize("kwargs", [
    {"ra_deg": float("nan")}, {"dec_deg": 91}, {"radius_deg": 1},
    {"collection": "other"}, {"limit": 501}, {"limit": True},
])
def test_search_rejects_invalid_inputs_before_network(kwargs: dict) -> None:
    params = {"ra_deg": 133.7, "dec_deg": -7.2, **kwargs}
    with pytest.raises(irsa.IRSAError) as error:
        irsa.search_images(**params)
    assert error.value.code == "invalid_request"


def test_search_and_metadata_byte_limit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    install_transport(monkeypatch, lambda request: httpx.Response(200, content=votable()))
    result = irsa.search_images(133.7, -7.2, collection="spherex_qr2", raw_path=tmp_path / "raw.xml")
    assert result["total_rows"] == 1 and not result["truncated"]
    assert (tmp_path / "raw.xml").read_bytes() == votable()
    monkeypatch.setattr(irsa, "MAX_METADATA_BYTES", 8)
    with pytest.raises(irsa.IRSAError) as error:
        irsa.search_images(133.7, -7.2)
    assert error.value.code == "metadata_too_large"


def test_network_timeout_is_structured(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(request):
        raise httpx.ReadTimeout("service timed out", request=request)
    install_transport(monkeypatch, timeout)
    with pytest.raises(irsa.IRSAError) as error:
        irsa.search_images(133.7, -7.2)
    assert error.value.code == "archive_timeout"


def test_download_fits_and_cleanup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    content = io.BytesIO()
    fits.PrimaryHDU().writeto(content)
    install_transport(monkeypatch, lambda request: httpx.Response(200, content=content.getvalue()))
    destination = tmp_path / "cutout.fits"
    result = irsa.download_cutout(SOURCE, 133.7, -7.2, 0.03, destination)
    assert destination.read_bytes() == content.getvalue()
    assert result["byte_count"] == 2880 and len(result["sha256"]) == 64
    assert not list(tmp_path.glob("*.part"))


@pytest.mark.parametrize("status,content,expected", [
    (302, b"", "archive_http_error"), (500, b"error", "archive_http_error"),
    (200, b"<html>not FITS</html>", "invalid_fits"),
])
def test_failed_download_does_not_replace_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                               status: int, content: bytes, expected: str) -> None:
    install_transport(monkeypatch, lambda request: httpx.Response(status, content=content, headers={"location": "https://evil.test"}))
    destination = tmp_path / "cutout.fits"
    destination.write_bytes(b"existing")
    with pytest.raises(irsa.IRSAError) as error:
        irsa.download_cutout(SOURCE, 133.7, -7.2, 0.03, destination)
    assert error.value.code == expected and destination.read_bytes() == b"existing"
    assert not list(tmp_path.glob("*.part"))


def test_cutout_byte_limit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    install_transport(monkeypatch, lambda request: httpx.Response(200, content=b"SIMPLE  =" + b"x" * 50))
    monkeypatch.setattr(irsa, "MAX_CUTOUT_BYTES", 20)
    with pytest.raises(irsa.IRSAError) as error:
        irsa.download_cutout(SOURCE, 133.7, -7.2, 0.03, tmp_path / "cutout.fits")
    assert error.value.code == "cutout_too_large"
    assert not list(tmp_path.iterdir())


# IRSA made QR2 unsearchable via SIA2 (superseded by DR1 + QR3, Nov 2026).
DR1_SOURCE = ("https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/2025W19_1B/"
              "l2b-v27-2026-197/3/level2_2025W19_1B_0116_1D3_spx_l2b-v27-2026-197.fits")


def test_allow_dr1_source_and_collection() -> None:
    assert irsa.validate_source_url(DR1_SOURCE) == DR1_SOURCE
    assert "spherex_dr1" in irsa.COLLECTIONS
    with pytest.raises(irsa.IRSAError) as error:
        irsa.validate_source_url(DR1_SOURCE.replace("/dr1/", "/dr9/"))
    assert error.value.code == "unsafe_source_url"
