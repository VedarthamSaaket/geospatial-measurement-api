import io
import math

import geopandas as gpd
import numpy as np
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import LineString, Point, box
from sqlalchemy.orm import sessionmaker

from app import database, services
from app.edges import geodesic_path, metres_per_unit, straight_edges
from app.main import app
from app.measure import convert, line_length, local_projection, measure
from app.readers import UnreadableFile, clean_message, detect_crs, find_shapefile
from tests.conftest import KML, upload

ONE_DEGREE_ON_EQUATOR = 6378137 * math.pi / 180


def test_convert_gives_predicted_values():
    assert convert("area", 25_000.0, "hectare", "metre") == (2.5, "hectare")
    assert convert("area", 4046.8564224, "acre", "metre") == (1.0, "acre")
    assert convert("length", 1609.344, "hectare", "mile") == (1.0, "mile")
    assert convert("length", 0.3048, "hectare", "foot") == (1.0, "foot")
    assert convert(None, None, "hectare", "mile") == (None, None)


def test_local_projection_is_centred_on_the_feature():
    area = local_projection(np.array([78.47, 78.48]), np.array([17.38, 17.39]), True)
    assert area == "+proj=laea +lat_0=17.385 +lon_0=78.475 +datum=WGS84 +units=m"
    length = local_projection(np.array([179.0, -179.0]), np.array([10.0, 12.0]), False)
    assert length == "+proj=aeqd +lat_0=11.0 +lon_0=180.0 +datum=WGS84 +units=m"
    wrapped = local_projection(np.array([-178.0, 179.0]), np.array([0.0, 0.0]), False)
    assert "+lon_0=-179.5 " in wrapped


def test_line_length_on_the_equator_matches_the_formula():
    length, sections = line_length(np.array([[0.0, 0.0], [1.0, 0.0]]))
    assert sections == 1
    assert length == pytest.approx(ONE_DEGREE_ON_EQUATOR, rel=1e-12)
    length, sections = line_length(np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]]))
    assert sections == 2
    assert length == pytest.approx(2 * ONE_DEGREE_ON_EQUATOR, rel=1e-12)


def test_utm_square_area_is_predicted_by_the_scale_factor():
    result = measure(box(500_000, 0, 500_100, 100), "EPSG:32631")
    assert result.value == pytest.approx(10_000 / 0.9996**2, rel=1e-8)
    assert result.unit == "square_metre"


def test_geodesic_path_adds_points_only_to_long_edges():
    long_edge = np.array([[0.0, 0.0], [25_000 / ONE_DEGREE_ON_EQUATOR, 0.0]])
    path = geodesic_path(long_edge)
    assert len(path) == 4
    assert [round(lon * ONE_DEGREE_ON_EQUATOR) for lon, _ in path] == [0, 8333, 16667, 25000]
    assert len(geodesic_path(np.array([[0.0, 0.0], [0.01, 0.0]]))) == 2


def test_straight_edges_step_follows_the_crs_unit():
    assert metres_per_unit("EPSG:4326") is None
    assert metres_per_unit("EPSG:32644") == 1
    assert metres_per_unit("EPSG:2263") == pytest.approx(0.3048006096)
    assert len(straight_edges(LineString([(0, 0), (35_000, 0)]), 1).coords) == 5
    assert len(straight_edges(LineString([(0, 0), (100_000, 0)]), 0.3048).coords) == 5
    assert len(straight_edges(LineString([(0, 0), (9_000, 0)]), 1).coords) == 2


def test_find_shapefile_rules():
    parts = ["data/roads.shp", "data/roads.shx", "data/roads.dbf", "notes.txt"]
    assert find_shapefile(parts) == "data/roads.shp"
    assert find_shapefile(["A.SHP", "a.shx", "a.DBF"]) == "A.SHP"
    with pytest.raises(UnreadableFile, match="found 0"):
        find_shapefile(["notes.txt"])
    with pytest.raises(UnreadableFile, match="found 2"):
        find_shapefile(["a.shp", "b.shp"])
    with pytest.raises(UnreadableFile, match=".shx, .dbf"):
        find_shapefile(["a.shp", "other.shx", "other.dbf"])


def test_detect_crs_cases():
    plot = [box(78.47, 17.38, 78.48, 17.39)]
    assert detect_crs(gpd.GeoDataFrame(geometry=plot, crs="EPSG:32644")) == ("EPSG:32644", False)
    assert detect_crs(gpd.GeoDataFrame(geometry=plot)) == ("EPSG:4326", True)
    assert detect_crs(gpd.GeoDataFrame(geometry=[Point(500_000, 1_900_000)])) == (None, False)
    assert detect_crs(gpd.GeoDataFrame(geometry=[])) == (None, False)


def test_clean_message_removes_folders(tmp_path):
    path = tmp_path / "abc123.zip"
    raw = f"'/vsizip/{path.resolve()}/layer.shp' not recognized; try another driver"
    assert clean_message(Exception(raw), path) == "'uploaded.zip/layer.shp' not recognized"


def test_save_stream_limits(tmp_path, monkeypatch):
    with pytest.raises(services.RejectedUpload) as empty:
        services.save_stream(io.BytesIO(b""), tmp_path / "empty")
    assert empty.value.status_code == 400
    monkeypatch.setattr(services, "MAX_UPLOAD_BYTES", 4)
    services.save_stream(io.BytesIO(b"1234"), tmp_path / "exact")
    assert (tmp_path / "exact").read_bytes() == b"1234"
    with pytest.raises(services.RejectedUpload) as big:
        services.save_stream(io.BytesIO(b"12345"), tmp_path / "big")
    assert big.value.status_code == 413


def test_real_startup_creates_the_data_folder_and_database(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    engine = database.build_engine(f"sqlite:///{data_dir / 'app.db'}")
    monkeypatch.setattr(database, "DATA_DIR", data_dir)
    monkeypatch.setattr(database, "UPLOAD_DIR", data_dir / "uploads")
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine, expire_on_commit=False))
    monkeypatch.setattr(services, "UPLOAD_DIR", data_dir / "uploads")
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert upload(client, "survey.kml", KML.encode()).status_code == 201
        assert client.get("/api/files/").json()["total"] == 1
    assert (data_dir / "app.db").exists()
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == database.BUSY_TIMEOUT_MS
    assert list((data_dir / "uploads").iterdir()) == []


def test_only_sqlite_gets_the_sqlite_settings(monkeypatch):
    calls = []
    monkeypatch.setattr(database, "create_engine", lambda url, **options: calls.append((url, options)))
    database.build_engine("postgresql://db/geo")
    assert calls == [("postgresql://db/geo", {})]
