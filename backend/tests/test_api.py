"""Exercise the HTTP contract without depending on a live archive in unit tests."""

import hashlib
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from fastapi.testclient import TestClient

from skytrace import api

SOURCE = "https://irsa.ipac.caltech.edu/ibe/data/spherex/qr2/level2/example.fits"
OBSERVATION_ID = hashlib.sha256(SOURCE.encode()).hexdigest()[:32]
POSITION = {"ra_deg": 133.7951291667, "dec_deg": -7.2451472222}


@pytest.fixture
def client(tmp_path, monkeypatch):
    def fake_search(**_kwargs):
        return {
            "query_url": "https://irsa.ipac.caltech.edu/SIA?COLLECTION=spherex_qr2",
            "queried_at_utc": "2026-11-03T12:00:00+00:00",
            "truncated": False, "total_rows": 1,
            "observations": [{
                "observation_id": OBSERVATION_ID, "source_product_id": "example",
                "source_url": SOURCE, "collection": "spherex_qr2",
                "mjd_start": 60000.0, "mjd_end": 60000.01,
            }],
        }

    def fake_download(_url, _ra, _dec, _size, destination: Path):
        fits.HDUList([
            fits.PrimaryHDU(),
            fits.ImageHDU(np.arange(16, dtype=np.float32).reshape(4, 4), name="IMAGE"),
        ]).writeto(destination)
        body = destination.read_bytes()
        return {"url": SOURCE, "byte_count": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                "retrieved_at_utc": "2026-11-03T12:00:01+00:00"}

    monkeypatch.setattr(api, "search_images", fake_search)
    monkeypatch.setattr(api, "download_cutout", fake_download)
    return TestClient(api.create_app(tmp_path))


def test_search_prepare_and_serve_original_and_preview(client):
    search = client.post("/v1/searches", json={**POSITION, "collection": "spherex_qr2"})
    assert search.status_code == 200
    search_id = search.json()["search_id"]
    response = client.post(f"/v1/searches/{search_id}/cutouts", json={"observation_ids": [OBSERVATION_ID]})
    assert response.status_code == 200, response.text
    record = response.json()[0]
    assert record["comparison_status"] == "not_assessed"
    assert record["source"]["source_url"] == SOURCE
    assert client.get(record["assets"]["preview_png_url"]).content.startswith(b"\x89PNG")
    original = client.get(record["assets"]["original_fits_url"]).content
    assert hashlib.sha256(original).hexdigest() == record["assets"]["sha256"]
    assert client.get(f"/v1/cutouts/{record['cutout_id']}").json() == record


@pytest.mark.parametrize("values", [
    {"ra_deg": 360}, {"ra_deg": -1}, {"dec_deg": 91},
    {"radius_deg": 10}, {"collection": "arbitrary"}, {"source_url": "http://localhost/private"},
    {"limit": 501},
])
def test_invalid_search_does_not_reach_archive(client, monkeypatch, values):
    def forbidden(**_kwargs):
        pytest.fail("Invalid request reached archive")
    monkeypatch.setattr(api, "search_images", forbidden)
    assert client.post("/v1/searches", json={**POSITION, **values}).status_code == 422


def test_cutout_requires_observation_from_saved_search(client, monkeypatch):
    search_id = client.post("/v1/searches", json=POSITION).json()["search_id"]
    def forbidden(*_args):
        pytest.fail("Unselected URL reached download")
    monkeypatch.setattr(api, "download_cutout", forbidden)
    response = client.post(f"/v1/searches/{search_id}/cutouts", json={"observation_ids": ["unknown"]})
    assert response.status_code == 404
    response = client.post(f"/v1/searches/{search_id}/cutouts", json={"observation_ids": [OBSERVATION_ID] * 2})
    assert response.status_code == 422


def test_upstream_failure_is_not_empty_success(client, monkeypatch):
    def fail(**_kwargs):
        raise api.IRSAError("archive_timeout", "Archive timed out")
    monkeypatch.setattr(api, "search_images", fail)
    response = client.post("/v1/searches", json=POSITION)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "archive_timeout"
    assert response.json()["error"]["retryable"] is True


def test_malformed_archive_metadata_is_not_retryable(client, monkeypatch):
    def fail(**_kwargs):
        raise api.IRSAError("invalid_metadata", "Malformed archive response")
    monkeypatch.setattr(api, "search_images", fail)
    response = client.post("/v1/searches", json=POSITION)
    assert response.status_code == 502
    assert response.json()["error"]["retryable"] is False


def test_bad_host_and_unknown_cache_ids_are_rejected(client):
    assert client.get("/health", headers={"host": "attacker.example"}).status_code == 400
    assert client.get("/v1/cutouts/not-a-generated-id/source.fits").status_code == 404


def test_cross_origin_access_is_not_wildcard(client):
    allowed = client.options("/v1/searches", headers={"origin": "http://localhost:3000",
                                                       "access-control-request-method": "POST"})
    denied = client.options("/v1/searches", headers={"origin": "https://attacker.example",
                                                      "access-control-request-method": "POST"})
    assert allowed.status_code == 200
    assert denied.status_code == 400


def test_cached_leaf_symlinks_are_not_served(tmp_path, monkeypatch):
    app = api.create_app(tmp_path / "cache")
    client = TestClient(app)
    search_id = "a" * 32
    outside = tmp_path / "outside.json"
    outside.write_text('{"private": true}')
    (tmp_path / "cache" / "searches" / f"{search_id}.json").symlink_to(outside)
    assert client.get(f"/v1/searches/{search_id}").status_code == 404


def test_budget_scan_failure_releases_operation_lock(client, monkeypatch):
    original = Path.rglob
    calls = 0
    def fail_once(path, pattern):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("Temporary cache scan error")
        return original(path, pattern)
    monkeypatch.setattr(Path, "rglob", fail_once)
    with pytest.raises(OSError, match="Temporary cache"):
        client.post("/v1/searches", json=POSITION)
    assert client.post("/v1/searches", json=POSITION).status_code == 200


def test_failed_second_download_rolls_back_first_result(client, monkeypatch, tmp_path):
    original_search = api.search_images
    original_download = api.download_cutout
    second_id = "b" * 32
    def two_products(**kwargs):
        result = original_search(**kwargs)
        result["observations"].append({**result["observations"][0], "observation_id": second_id})
        return result
    calls = 0
    def fail_second(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise api.IRSAError("upstream_timeout", "Second cutout failed")
        return original_download(*args)
    monkeypatch.setattr(api, "search_images", two_products)
    monkeypatch.setattr(api, "download_cutout", fail_second)
    search_id = client.post("/v1/searches", json=POSITION).json()["search_id"]
    response = client.post(f"/v1/searches/{search_id}/cutouts", json={"observation_ids": [OBSERVATION_ID, second_id]})
    assert response.status_code == 502
    assert list((tmp_path / "cutouts").iterdir()) == []
