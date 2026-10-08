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


def test_shapefile_zip_features_and_pagination(client, make_shapefile_zip):
    content = make_shapefile_zip([PLOT, box(78.50, 17.38, 78.51, 17.39)])
    file_id = upload(client, "plots.zip", content).json()["id"]
    page = client.get(f"/api/files/{file_id}/features/", params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 2
    assert len(page["features"]) == 1
    feature = page["features"][0]
    assert feature["index"] == 1
    assert feature["geometry"]["type"] == "Polygon"
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


def test_corrupt_files_do_not_crash(client):
    assert upload(client, "fake.zip", b"not a zip").status_code == 422
    assert upload(client, "fake.kml", b"not xml").status_code == 422
    assert upload(client, "fake.kmz", b"not a zip").status_code == 422
    assert upload(client, "fake.geojson", b"not json").status_code == 422


def test_rejected_uploads(client, monkeypatch):
    assert upload(client, "notes.txt", b"hello").status_code == 415
    assert upload(client, "empty.kml", b"").status_code == 400
    monkeypatch.setattr(services, "MAX_UPLOAD_BYTES", 10)
    assert upload(client, "big.kml", b"x" * 11).status_code == 413


def test_unknown_file_id_is_404(client):
    assert client.get("/api/files/missing/").status_code == 404
    assert client.get("/api/files/missing/measurements/").status_code == 404
