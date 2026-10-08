import io
import zipfile

import geopandas as gpd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import services
from app.database import Base, get_session
from app.main import app

KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Folder><name>plots</name>
<Placemark><name>plot a</name><Polygon><outerBoundaryIs><LinearRing><coordinates>
78.47,17.38,0 78.48,17.38,0 78.48,17.39,0 78.47,17.39,0 78.47,17.38,0
</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
</Folder>
<Folder><name>roads</name>
<Placemark><name>road</name><LineString><coordinates>78.47,17.38,0 78.48,17.39,0</coordinates></LineString></Placemark>
<Placemark><name>gate</name><Point><coordinates>78.47,17.38,0</coordinates></Point></Placemark>
</Folder>
</Document></kml>"""


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        with TestSession() as session:
            yield session

    monkeypatch.setattr(services, "UPLOAD_DIR", tmp_path)
    app.dependency_overrides[get_session] = override_session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def kml_bytes():
    return KML.encode()


@pytest.fixture
def make_shapefile_zip(tmp_path):
    def build(geometries, crs="EPSG:4326", skip=()):
        folder = tmp_path / f"shp{len(list(tmp_path.iterdir()))}"
        folder.mkdir()
        frame = gpd.GeoDataFrame({"name": [f"f{i}" for i in range(len(geometries))]}, geometry=geometries, crs=crs)
        frame.to_file(folder / "layer.shp")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for part in folder.iterdir():
                if part.suffix not in skip:
                    archive.write(part, f"layer/{part.name}")
        return buffer.getvalue()

    return build


def upload(client, name, content):
    return client.post("/api/files/", files={"file": (name, content)})
