import zipfile
from pathlib import Path, PurePosixPath

import geopandas as gpd
import pandas as pd
import pyogrio

REQUIRED_SIDECARS = (".shx", ".dbf")


class UnreadableFile(Exception):
    pass


def read_geofile(path: Path) -> gpd.GeoDataFrame:
    try:
        if path.suffix.lower() == ".kml":
            return read_kml(path)
        return read_shapefile_zip(path)
    except UnreadableFile:
        raise
    except Exception as exc:
        raise UnreadableFile(f"could not read file: {exc}") from exc


def read_kml(path: Path) -> gpd.GeoDataFrame:
    layers = [name for name, _ in pyogrio.list_layers(path)]
    if not layers:
        raise UnreadableFile("kml has no layers")
    frames = [gpd.read_file(path, layer=name, engine="pyogrio") for name in layers]
    frames = [frame for frame in frames if len(frame)]
    if not frames:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    merged = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)
    empty_columns = [c for c in merged.columns if c != "geometry" and merged[c].isna().all()]
    return merged.drop(columns=empty_columns)


def read_shapefile_zip(path: Path) -> gpd.GeoDataFrame:
    if not zipfile.is_zipfile(path):
        raise UnreadableFile("file is not a valid zip archive")
    member = find_shapefile(path)
    return gpd.read_file(f"/vsizip/{path.resolve()}/{member}", engine="pyogrio")


def find_shapefile(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if not n.startswith("__MACOSX/")]
    shapefiles = [n for n in names if n.lower().endswith(".shp")]
    if len(shapefiles) != 1:
        raise UnreadableFile(f"zip must contain exactly one .shp file, found {len(shapefiles)}")
    member = shapefiles[0]
    present = {n.lower() for n in names}
    stem = str(PurePosixPath(member).with_suffix("")).lower()
    missing = [ext for ext in REQUIRED_SIDECARS if stem + ext not in present]
    if missing:
        raise UnreadableFile(f"zip is missing shapefile parts: {', '.join(missing)}")
    return member


def detect_crs(frame: gpd.GeoDataFrame) -> tuple[str | None, bool]:
    if frame.crs is not None:
        epsg = frame.crs.to_epsg()
        return (f"EPSG:{epsg}" if epsg else frame.crs.name), False
    if len(frame) and looks_like_lonlat(frame):
        return "EPSG:4326", True
    return None, False


def looks_like_lonlat(frame: gpd.GeoDataFrame) -> bool:
    minx, miny, maxx, maxy = frame.total_bounds
    return minx >= -180 and maxx <= 180 and miny >= -90 and maxy <= 90
