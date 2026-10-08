from functools import lru_cache

import numpy as np
import shapely
from pyproj import CRS, Geod
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

MAX_EDGE = 10_000
MAX_POINTS = 10_000
GEOD = Geod(ellps="WGS84")


@lru_cache(maxsize=64)
def metres_per_unit(crs: str) -> float | None:
    parsed = CRS.from_user_input(crs)
    return None if parsed.is_geographic else parsed.axis_info[0].unit_conversion_factor


def straight_edges(geometry: BaseGeometry, metres_per_unit: float) -> BaseGeometry:
    step = max(MAX_EDGE / metres_per_unit, geometry.length / MAX_POINTS)
    return shapely.segmentize(geometry, step)


def geodesic_edges(lonlat: BaseGeometry) -> BaseGeometry:
    data = mapping(lonlat)
    return shape({"type": data["type"], "coordinates": walk(data["coordinates"])})


def walk(coords):
    if isinstance(coords[0][0], (int, float)):
        return geodesic_path(np.array(coords))
    return [walk(part) for part in coords]


def geodesic_path(coords: np.ndarray) -> list:
    lons, lats = coords[:, 0], coords[:, 1]
    lengths = GEOD.inv(lons[:-1], lats[:-1], lons[1:], lats[1:])[2]
    step = max(MAX_EDGE, lengths.sum() / MAX_POINTS)
    path = []
    for i, length in enumerate(lengths):
        path.append((lons[i], lats[i]))
        if length > step:
            path.extend(GEOD.npts(lons[i], lats[i], lons[i + 1], lats[i + 1], int(length // step)))
    path.append((lons[-1], lats[-1]))
    return path
