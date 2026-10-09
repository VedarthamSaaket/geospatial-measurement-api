import pytest
from fastapi import Request
from shapely.geometry import box

from app import services
from tests.conftest import upload

PLOT = box(78.47, 17.38, 78.48, 17.39)


def test_upload_kml_and_read_file_info(client, kml_bytes):
    created = upload(client, "survey.kml", kml_bytes)
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "COMPLETED"
    assert body["feature_count"] == 3
    assert body["crs"] == "EPSG:4326"
    info = client.get(f"/api/files/{body['id']}/")
    assert info.status_code == 200
    assert info.json()["filename"] == "survey.kml"
    assert info.json()["created_at"] == body["created_at"]
    assert body["created_at"].endswith("Z")


def test_kml_measurements(client, kml_bytes):
    file_id = upload(client, "survey.kml", kml_bytes).json()["id"]
    body = client.get(f"/api/files/{file_id}/measurements/").json()
    by_type = {m["geometry_type"]: m for m in body["measurements"]}
    assert body["total"] == 3
    assert by_type["Polygon"]["measurement_type"] == "area"
    assert 1_170_000 < by_type["Polygon"]["value"] < 1_180_000
    assert by_type["LineString"]["measurement_type"] == "length"
    assert 1_530 < by_type["LineString"]["value"] < 1_540
    assert by_type["Point"]["value"] is None


def test_measurements_in_other_units(client, kml_bytes):
    file_id = upload(client, "survey.kml", kml_bytes).json()["id"]
    url = f"/api/files/{file_id}/measurements/"
    metric = {m["geometry_type"]: m for m in client.get(url).json()["measurements"]}
    params = {"area_unit": "hectare", "length_unit": "kilometre"}
    other = {m["geometry_type"]: m for m in client.get(url, params=params).json()["measurements"]}
    assert other["Polygon"]["unit"] == "hectare"
    assert other["Polygon"]["value"] == pytest.approx(metric["Polygon"]["value"] / 10_000)
    assert other["LineString"]["unit"] == "kilometre"
    assert other["LineString"]["value"] == pytest.approx(metric["LineString"]["value"] / 1000)
    assert other["Point"]["unit"] is None
    assert client.get(url, params={"area_unit": "furlong"}).status_code == 422


def test_summary_totals(client, make_shapefile_zip):
    content = make_shapefile_zip([PLOT, box(78.50, 17.38, 78.51, 17.39)])
    file_id = upload(client, "plots.zip", content).json()["id"]
    values = [m["value"] for m in client.get(f"/api/files/{file_id}/measurements/").json()["measurements"]]
    summary = client.get(f"/api/files/{file_id}/summary/").json()
    assert summary["geometry_types"] == {"Polygon": 2}
    assert summary["measured_count"] == 2
    assert summary["total_area"] == pytest.approx(sum(values))
    assert summary["total_length"] == 0
    hectares = client.get(f"/api/files/{file_id}/summary/", params={"area_unit": "hectare"}).json()
    assert hectares["total_area"] == pytest.approx(sum(values) / 10_000)


def test_summary_counts_unmeasured_features(client, kml_bytes):
    file_id = upload(client, "survey.kml", kml_bytes).json()["id"]
    summary = client.get(f"/api/files/{file_id}/summary/").json()
    assert summary["geometry_types"] == {"Polygon": 1, "LineString": 1, "Point": 1}
    assert summary["feature_count"] == 3
    assert summary["measured_count"] == 2
    assert summary["total_length"] > 0


def test_kmz_gives_same_features_as_kml(client, kml_bytes, kmz_bytes):
    from_kml = upload(client, "survey.kml", kml_bytes).json()
    from_kmz = upload(client, "survey.kmz", kmz_bytes).json()
    assert from_kmz["file_type"] == "kmz"
    assert from_kmz["feature_count"] == from_kml["feature_count"]
    kml_values = client.get(f"/api/files/{from_kml['id']}/measurements/").json()["measurements"]
    kmz_values = client.get(f"/api/files/{from_kmz['id']}/measurements/").json()["measurements"]
    assert [m["value"] for m in kmz_values] == [m["value"] for m in kml_values]


def test_kmz_without_kml_is_failed(client, make_shapefile_zip):
    response = upload(client, "wrong.kmz", make_shapefile_zip([PLOT]))
    assert response.status_code == 422
    assert "no kml" in response.json()["error"]


def test_geojson_upload_is_measured(client, geojson_bytes):
    body = upload(client, "plot.geojson", geojson_bytes).json()
    assert body["status"] == "COMPLETED"
    assert body["crs"] == "EPSG:4326"
    measurement = client.get(f"/api/files/{body['id']}/measurements/").json()["measurements"][0]
    assert 1_170_000 < measurement["value"] < 1_180_000


def test_geojson_without_properties(client):
    content = b'{"type": "Polygon", "coordinates": [[[78.47, 17.38], [78.48, 17.38], [78.48, 17.39], [78.47, 17.38]]]}'
    body = upload(client, "bare.geojson", content).json()
    assert body["status"] == "COMPLETED"
    feature = client.get(f"/api/files/{body['id']}/features/").json()["features"][0]
    assert feature["properties"] == {}


def test_shapefile_zip_features_and_pagination(client, make_shapefile_zip):
    content = make_shapefile_zip([PLOT, box(78.50, 17.38, 78.51, 17.39)])
    file_id = upload(client, "plots.zip", content).json()["id"]
    page = client.get(f"/api/files/{file_id}/features/", params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 2
    assert len(page["features"]) == 1
    feature = page["features"][0]
    assert feature["index"] == 1
    assert feature["geometry"]["type"] == "Polygon"
    assert feature["crs"] == "EPSG:4326"
    assert feature["properties"] == {"name": "f1"}


def test_projected_shapefile_is_measured_in_metres(client, make_shapefile_zip):
    content = make_shapefile_zip([box(500000, 1900000, 501000, 1901000)], crs="EPSG:32644")
    body = upload(client, "utm.zip", content).json()
    assert body["crs"] == "EPSG:32644"
    area = client.get(f"/api/files/{body['id']}/measurements/").json()["measurements"][0]["value"]
    assert 995_000 < area < 1_005_000


def test_shapefile_without_prj_assumes_lonlat(client, make_shapefile_zip):
    body = upload(client, "noprj.zip", make_shapefile_zip([PLOT], skip=(".prj",))).json()
    assert body["crs"] == "EPSG:4326"
    assert body["crs_assumed"] is True


def test_shapefile_without_prj_and_not_lonlat_skips_measurement(client, make_shapefile_zip):
    content = make_shapefile_zip([box(500000, 1900000, 501000, 1901000)], crs="EPSG:32644", skip=(".prj",))
    body = upload(client, "unknown.zip", content).json()
    assert body["crs"] is None
    measurement = client.get(f"/api/files/{body['id']}/measurements/").json()["measurements"][0]
    assert measurement["value"] is None
    assert "no crs" in measurement["note"]


def test_zip_missing_parts_is_failed(client, make_shapefile_zip):
    response = upload(client, "broken.zip", make_shapefile_zip([PLOT], skip=(".dbf",)))
    assert response.status_code == 422
    assert response.json()["status"] == "FAILED"
    assert ".dbf" in response.json()["error"]
    assert client.get(f"/api/files/{response.json()['id']}/").json()["status"] == "FAILED"


def test_kml_without_placemarks_is_completed_with_no_features(client):
    content = b'<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document></Document></kml>'
    response = upload(client, "nothing.kml", content)
    assert response.status_code == 201
    assert response.json()["feature_count"] == 0


def test_read_errors_do_not_show_server_paths(client, tmp_path):
    for name, content in (("fake.kml", b"<html></html>"), ("fake.geojson", b"{}"), ("fake.kmz", b"nope")):
        error = upload(client, name, content).json()["error"]
        assert str(tmp_path) not in error
        assert "/" not in error


def test_corrupt_files_do_not_crash(client):
    assert upload(client, "fake.zip", b"not a zip").status_code == 422
    assert upload(client, "fake.kml", b"not xml").status_code == 422
    assert upload(client, "fake.kmz", b"not a zip").status_code == 422
    assert upload(client, "fake.geojson", b"not json").status_code == 422


def test_features_are_stored_in_batches_and_keep_their_order(client, kml_bytes, monkeypatch):
    monkeypatch.setattr(services, "BATCH_SIZE", 2)
    file_id = upload(client, "survey.kml", kml_bytes).json()["id"]
    features = client.get(f"/api/files/{file_id}/features/").json()["features"]
    assert [f["index"] for f in features] == [0, 1, 2]
    assert [f["geometry_type"] for f in features] == ["Polygon", "LineString", "Point"]
    assert features[0]["properties"]["Name"] == "plot a"
    assert client.get(f"/api/files/{file_id}/summary/").json()["measured_count"] == 2


def test_failure_after_reading_is_saved_as_failed(client, kml_bytes, monkeypatch, caplog):
    def broken(geometry):
        raise ValueError("/srv/secret/path")

    monkeypatch.setattr(services.shapely, "to_geojson", broken)
    response = upload(client, "survey.kml", kml_bytes)
    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["error"] == "file could not be processed"
    assert body["feature_count"] == 0
    assert body["crs"] is None
    assert client.get(f"/api/files/{body['id']}/").json()["status"] == "FAILED"
    assert client.get(f"/api/files/{body['id']}/features/").json()["features"] == []
    assert f"file {body['id']} failed while processing" in caplog.text
    assert "/srv/secret/path" in caplog.text


def test_rejected_uploads(client, monkeypatch):
    assert upload(client, "notes.txt", b"hello").status_code == 415
    assert upload(client, "empty.kml", b"").status_code == 400
    monkeypatch.setattr(services, "MAX_UPLOAD_BYTES", 10)
    assert upload(client, "big.kml", b"x" * 11).status_code == 413


def test_oversized_body_is_rejected_before_it_is_read(client, monkeypatch):
    def never_called(*args):
        raise AssertionError("the body was read")

    monkeypatch.setattr(services, "MAX_UPLOAD_BYTES", 10)
    monkeypatch.setattr(Request, "form", never_called)
    content = b"x" * (services.FORM_OVERHEAD + 11)
    response = client.post("/api/files/", files={"file": ("big.kml", content)}, headers={"Origin": "https://maps.example.com"})
    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == "*"
    assert "larger than" in response.json()["detail"]
    assert client.get("/api/files/").json()["total"] == 0


def test_two_files_in_one_upload_are_rejected(client, kml_bytes, geojson_bytes):
    files = [("file", ("survey.kml", kml_bytes)), ("file", ("plot.geojson", geojson_bytes))]
    response = client.post("/api/files/", files=files)
    assert response.status_code == 400
    assert response.json()["detail"] == "send one file per upload"
    assert client.get("/api/files/").json()["total"] == 0


def test_unknown_file_id_is_404(client):
    assert client.get("/api/files/missing/").status_code == 404
    assert client.get("/api/files/missing/measurements/").status_code == 404


def test_list_files_newest_first(client, kml_bytes, geojson_bytes):
    first = upload(client, "survey.kml", kml_bytes).json()["id"]
    second = upload(client, "plot.geojson", geojson_bytes).json()["id"]
    body = client.get("/api/files/").json()
    assert body["total"] == 2
    assert [f["id"] for f in body["files"]] == [second, first]
    assert len(client.get("/api/files/", params={"limit": 1}).json()["files"]) == 1


def test_delete_file(client, kml_bytes):
    file_id = upload(client, "survey.kml", kml_bytes).json()["id"]
    assert client.delete(f"/api/files/{file_id}/").status_code == 204
    assert client.get(f"/api/files/{file_id}/").status_code == 404
    assert client.get(f"/api/files/{file_id}/measurements/").status_code == 404
    assert client.get("/api/files/").json()["total"] == 0
    assert client.delete(f"/api/files/{file_id}/").status_code == 404


def test_paths_work_without_the_trailing_slash(client, kml_bytes):
    created = client.post("/api/files", files={"file": ("survey.kml", kml_bytes)}, follow_redirects=False)
    assert created.status_code == 201
    file_id = created.json()["id"]
    for path in (f"/api/files/{file_id}", f"/api/files/{file_id}/measurements", f"/api/files/{file_id}/features", "/api/files"):
        assert client.get(path, follow_redirects=False).status_code == 200
    assert client.get(f"/api/files/{file_id}/measurements?limit=1", follow_redirects=False).json()["limit"] == 1


def test_root_redirects_to_docs(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/docs"


def test_cors_headers_for_a_page_on_another_origin(client):
    origin = {"Origin": "https://maps.example.com"}
    assert client.get("/api/files/", headers=origin).headers["access-control-allow-origin"] == "*"
    preflight = client.options("/api/files/", headers={**origin, "Access-Control-Request-Method": "POST"})
    assert preflight.status_code == 200
    assert "POST" in preflight.headers["access-control-allow-methods"]
