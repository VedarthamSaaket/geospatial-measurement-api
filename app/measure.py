import logging
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import shapely
from pyproj import CRS, Transformer
from shapely.geometry.base import BaseGeometry

from app.edges import GEOD, geodesic_edges, metres_per_unit, straight_edges

WGS84 = "EPSG:4326"
AREA_TYPES = {"Polygon", "MultiPolygon"}
LENGTH_TYPES = {"LineString", "MultiLineString"}
POINT_TYPES = {"Point", "MultiPoint"}
SECTION_RADIUS = 50_000
SHORT_EDGE_DEGREES = 0.05
AREA_UNITS = {"square_metre": 1.0, "hectare": 10_000.0, "square_kilometre": 1_000_000.0, "acre": 4046.8564224}
LENGTH_UNITS = {"metre": 1.0, "kilometre": 1000.0, "mile": 1609.344, "foot": 0.3048}
logger = logging.getLogger(__name__)


@dataclass
class Measurement:
    measurement_type: str | None = None
    value: float | None = None
    unit: str | None = None
    measurement_crs: str | None = None
    note: str | None = None


def measure(geometry: BaseGeometry | None, source_crs: str | None) -> Measurement:
    if geometry is None or geometry.is_empty:
        return Measurement(note="feature has no geometry")
    kind = geometry.geom_type
    if kind in POINT_TYPES:
        return Measurement(note="no measurement for point geometry")
    if kind not in AREA_TYPES | LENGTH_TYPES:
        return Measurement(note=f"geometry type {kind} is not supported for measurement")
    if source_crs is None:
        return Measurement(note="file has no crs so measurement was skipped")

    try:
        return calculate(shapely.force_2d(geometry), kind in AREA_TYPES, source_crs)
    except Exception:
        logger.exception("a %s could not be measured", kind)
        return Measurement(note="feature could not be measured")


def calculate(geometry: BaseGeometry, is_area: bool, source_crs: str) -> Measurement:
    unit = metres_per_unit(source_crs)
    if unit:
        geometry = straight_edges(geometry, unit)
    lonlat = reproject(geometry, source_crs, WGS84)
    lons, lats = shapely.get_coordinates(lonlat).T
    if not (np.isfinite(lons).all() and (np.abs(lats) <= 90).all()):
        return Measurement(note="coordinates are outside the valid range of the file crs")
    if unit is None and max(np.ptp(lons), np.ptp(lats)) > SHORT_EDGE_DEGREES:
        lonlat = geodesic_edges(lonlat)
        lons, lats = shapely.get_coordinates(lonlat).T
    target = local_projection(lons, lats, is_area)
    if not is_area:
        lines = [line_length(shapely.get_coordinates(line)) for line in getattr(lonlat, "geoms", [lonlat])]
        sections = sum(count for _, count in lines)
        note = "line was measured in sections, each in its own projection" if sections > 1 else None
        return Measurement("length", sum(length for length, _ in lines), "metre", target, note)
    projected = reproject(lonlat, WGS84, target)
    note = None
    if not projected.is_valid:
        projected = keep_polygons(shapely.make_valid(projected))
        note = "geometry was invalid and was repaired before measuring"
    return Measurement("area", projected.area, "square_metre", target, note)


def line_length(coords: np.ndarray) -> tuple[float, int]:
    centre = coords[:1] if len(coords) == 2 else coords
    target = local_projection(centre[:, 0], centre[:, 1], False)
    xs, ys = transformer(WGS84, target).transform(coords[:, 0], coords[:, 1])
    if len(coords) > 2 and np.hypot(xs, ys).max() > SECTION_RADIUS:
        middle = len(coords) // 2
        first, second = line_length(coords[: middle + 1]), line_length(coords[middle:])
        return first[0] + second[0], first[1] + second[1]
    return float(np.hypot(np.diff(xs), np.diff(ys)).sum()), 1


def convert(measurement_type: str | None, value: float | None, area_unit: str, length_unit: str):
    if value is None:
        return None, None
    if measurement_type == "area":
        return value / AREA_UNITS[area_unit], area_unit
    return value / LENGTH_UNITS[length_unit], length_unit


def local_projection(lons: np.ndarray, lats: np.ndarray, is_area: bool) -> str:
    if lons.max() - lons.min() > 180:
        lons = lons % 360
    lon = round((lons.min() + lons.max()) / 2, 6)
    lon = lon - 360 if lon > 180 else lon
    lat = round((lats.min() + lats.max()) / 2, 6)
    projection = "laea" if is_area else "aeqd"
    return f"+proj={projection} +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m"


def reproject(geometry: BaseGeometry, source: str, target: str) -> BaseGeometry:
    if source == target:
        return geometry
    return shapely.transform(geometry, transformer(source, target).transform, interleaved=False)


@lru_cache(maxsize=256)
def transformer(source: str, target: str) -> Transformer:
    return Transformer.from_crs(CRS.from_user_input(source), CRS.from_user_input(target), always_xy=True)


def keep_polygons(geometry: BaseGeometry) -> BaseGeometry:
    parts = [g for g in getattr(geometry, "geoms", [geometry]) if g.geom_type in AREA_TYPES]
    return shapely.union_all(parts)


def reference_measure(geometry: BaseGeometry, source_crs: str) -> float:
    lonlat = reproject(shapely.force_2d(geometry), source_crs, WGS84)
    if lonlat.geom_type in AREA_TYPES:
        return geodesic_area(lonlat)
    return geodesic_length(lonlat)


def geodesic_area(geometry: BaseGeometry) -> float:
    total = 0.0
    for polygon in shapely.get_parts(geometry):
        total += ring_area(polygon.exterior)
        for hole in polygon.interiors:
            total -= ring_area(hole)
    return total


def ring_area(ring) -> float:
    lons, lats = np.asarray(ring.coords).T[:2]
    return abs(GEOD.polygon_area_perimeter(lons, lats)[0])


def geodesic_length(geometry: BaseGeometry) -> float:
    lengths = [GEOD.line_length(*np.asarray(line.coords).T[:2]) for line in shapely.get_parts(geometry)]
    return float(sum(lengths))
