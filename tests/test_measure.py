import pytest
from pyproj import Geod, Transformer
from shapely import transform
from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPolygon, Point, Polygon, box

from app.measure import measure

GEOD = Geod(ellps="WGS84")
PLOT = box(78.47, 17.38, 78.48, 17.39)
ROAD = LineString([(78.47, 17.38), (78.48, 17.39)])


def circle(lon, lat, radius, points=72):
    ring = [GEOD.fwd(lon, lat, 360 * i / points, radius)[:2] for i in range(points)]
    return Polygon(ring)


def geodesic_area(polygon):
    lons, lats = zip(*polygon.exterior.coords)
    return abs(GEOD.polygon_area_perimeter(lons, lats)[0])


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


def test_feature_crossing_the_180_line_is_measured_like_any_other():
    crossing = Polygon([(179.95, 10), (-179.95, 10), (-179.95, 10.1), (179.95, 10.1)])
    same_shape_elsewhere = box(-0.05, 10, 0.05, 10.1)
    expected = measure(same_shape_elsewhere, "EPSG:4326").value
    assert measure(crossing, "EPSG:4326").value == pytest.approx(expected, rel=1e-6)
    line = LineString([(179.95, 10), (-179.95, 10.1)])
    expected = GEOD.geometry_length(LineString([(-0.05, 10), (0.05, 10.1)]))
    assert measure(line, "EPSG:4326").value == pytest.approx(expected, rel=1e-6)


def test_circle_across_the_180_line_is_not_broken_by_repair():
    for lon, lat in ((179.99, 17), (-179.99, -45), (180, 80)):
        shape = circle(lon, lat, 5000)
        result = measure(shape, "EPSG:4326")
        assert result.note is None
        assert result.value == pytest.approx(geodesic_area(shape), rel=1e-6)


def test_polygon_around_the_pole():
    cap = Polygon([(lon, 85) for lon in range(-180, 180)])
    assert measure(cap, "EPSG:4326").value == pytest.approx(geodesic_area(cap), rel=1e-4)


def test_bad_coordinates_are_reported_not_raised():
    not_a_number = Polygon([(0, 0), (1, float("nan")), (1, 1), (0, 0)])
    for shape, crs in ((box(10, 94, 11, 95), "EPSG:4326"), (not_a_number, "EPSG:4326"), (box(5e7, 5e7, 6e7, 6e7), "EPSG:32644")):
        result = measure(shape, crs)
        assert result.value is None
        assert "outside the valid range" in result.note
    assert measure(PLOT, "EPSG:999999").note == "feature could not be measured"


def test_degenerate_shapes_measure_as_zero():
    assert measure(LineString([(78.47, 17.38), (78.47, 17.38)]), "EPSG:4326").value == 0
    assert measure(Polygon([(78.47, 17.38), (78.48, 17.38), (78.47, 17.38)]), "EPSG:4326").value == 0


def test_long_line_matches_geodesic_length():
    coast = LineString([(70 + i * 0.05, 8 + i * 0.04 + (i % 3) * 0.1) for i in range(800)])
    result = measure(coast, "EPSG:4326")
    assert GEOD.geometry_length(coast) > 5_000_000
    assert result.value == pytest.approx(GEOD.geometry_length(coast), rel=1e-5)
    assert "sections" in result.note


def test_two_point_line_across_a_continent():
    flight = LineString([(0, 60), (60, 60)])
    assert measure(flight, "EPSG:4326").value == pytest.approx(GEOD.geometry_length(flight), rel=1e-9)


def test_multiline_with_parts_far_apart():
    parts = MultiLineString([[(0, 0), (0.01, 0)], [(60, 60), (60.01, 60)]])
    assert measure(parts, "EPSG:4326").value == pytest.approx(GEOD.geometry_length(parts), rel=1e-6)
