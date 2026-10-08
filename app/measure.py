from dataclasses import dataclass
from functools import lru_cache

import shapely
from pyproj import CRS, Transformer
from shapely.geometry.base import BaseGeometry

WGS84 = "EPSG:4326"
AREA_TYPES = {"Polygon", "MultiPolygon"}
LENGTH_TYPES = {"LineString", "MultiLineString"}
POINT_TYPES = {"Point", "MultiPoint"}
AREA_UNITS = {"square_metre": 1.0, "hectare": 10_000.0, "square_kilometre": 1_000_000.0, "acre": 4046.8564224}
LENGTH_UNITS = {"metre": 1.0, "kilometre": 1000.0, "mile": 1609.344, "foot": 0.3048}


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

    note = None
    geometry = shapely.force_2d(geometry)
    if not geometry.is_valid:
        geometry = keep_same_kind(shapely.make_valid(geometry), kind)
        note = "geometry was invalid and was repaired before measuring"
    lonlat = reproject(geometry, source_crs, WGS84)
    is_area = kind in AREA_TYPES
    target = local_projection(lonlat, is_area)
    projected = reproject(lonlat, WGS84, target)
    if is_area:
        return Measurement("area", projected.area, "square_metre", target, note)
    return Measurement("length", projected.length, "metre", target, note)


def convert(measurement_type: str | None, value: float | None, area_unit: str, length_unit: str):
    if value is None:
        return None, None
    if measurement_type == "area":
        return value / AREA_UNITS[area_unit], area_unit
    return value / LENGTH_UNITS[length_unit], length_unit


def local_projection(lonlat: BaseGeometry, is_area: bool) -> str:
    lons, lats = shapely.get_coordinates(lonlat).T
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


def keep_same_kind(geometry: BaseGeometry, kind: str) -> BaseGeometry:
    wanted = AREA_TYPES if kind in AREA_TYPES else LENGTH_TYPES
    parts = [g for g in getattr(geometry, "geoms", [geometry]) if g.geom_type in wanted]
    return shapely.union_all(parts)
