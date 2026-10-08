import pytest
from pyproj import Geod, Transformer
from shapely import transform
from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Point, Polygon, box

from app.measure import measure

GEOD = Geod(ellps="WGS84")
PLOT = box(78.47, 17.38, 78.48, 17.39)
ROAD = LineString([(78.47, 17.38), (78.48, 17.39)])


def test_polygon_area_matches_geodesic_area():
    result = measure(PLOT, "EPSG:4326")
    expected = abs(GEOD.geometry_area_perimeter(PLOT)[0])
    assert result.measurement_type == "area"
    assert result.unit == "square_metre"
    assert result.value == pytest.approx(expected, rel=1e-6)


def test_line_length_matches_geodesic_length():
    result = measure(ROAD, "EPSG:4326")
    assert result.measurement_type == "length"
    assert result.unit == "metre"
    assert result.value == pytest.approx(GEOD.geometry_length(ROAD), rel=1e-6)


def test_area_is_not_calculated_in_degrees():
    assert measure(PLOT, "EPSG:4326").value > 1_000_000
    assert PLOT.area == pytest.approx(0.0001)


def test_projected_input_gives_same_area_as_lonlat_input():
    to_mercator = Transformer.from_crs(4326, 3857, always_xy=True).transform
    mercator_plot = transform(PLOT, to_mercator, interleaved=False)
    from_mercator = measure(mercator_plot, "EPSG:3857").value
    assert from_mercator == pytest.approx(measure(PLOT, "EPSG:4326").value, rel=1e-6)
    assert mercator_plot.area > from_mercator * 1.05


def test_polygon_hole_is_subtracted():
    hole = [(78.472, 17.382), (78.474, 17.382), (78.474, 17.384), (78.472, 17.384)]
    with_hole = Polygon(PLOT.exterior.coords, [hole])
    assert measure(with_hole, "EPSG:4326").value < measure(PLOT, "EPSG:4326").value


def test_multipolygon_area_is_sum_of_parts():
    other = box(78.50, 17.38, 78.51, 17.39)
    total = measure(MultiPolygon([PLOT, other]), "EPSG:4326").value
    parts = measure(PLOT, "EPSG:4326").value + measure(other, "EPSG:4326").value
    assert total == pytest.approx(parts, rel=1e-4)


def test_point_has_no_measurement():
    result = measure(Point(78.47, 17.38), "EPSG:4326")
    assert result.value is None
    assert "point" in result.note


def test_unsupported_geometry_is_reported_not_raised():
    result = measure(GeometryCollection([Point(1, 1), ROAD]), "EPSG:4326")
    assert result.value is None
    assert "not supported" in result.note


def test_missing_geometry_and_missing_crs():
    assert measure(None, "EPSG:4326").note == "feature has no geometry"
    assert measure(PLOT, None).value is None


def test_invalid_polygon_is_repaired():
    bowtie = Polygon([(78.47, 17.38), (78.48, 17.39), (78.48, 17.38), (78.47, 17.39)])
    result = measure(bowtie, "EPSG:4326")
    assert result.value > 0
    assert "repaired" in result.note
