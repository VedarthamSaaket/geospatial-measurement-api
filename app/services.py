import json
import logging
from pathlib import Path
from typing import BinaryIO

import geopandas as gpd
import pandas as pd
import shapely
from shapely.geometry import shape
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.config import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES, UPLOAD_DIR
from app.measure import WGS84, measure, reference_measure
from app.models import Feature, UploadedFile, new_id
from app.readers import UnreadableFile, detect_crs, read_geofile

CHUNK_SIZE = 1024 * 1024
FORM_OVERHEAD = 64 * 1024
BATCH_SIZE = 1000
logger = logging.getLogger(__name__)


class RejectedUpload(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message


def handle_upload(session: Session, filename: str, stream: BinaryIO) -> UploadedFile:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise RejectedUpload(415, "accepted files are .kml, .kmz, .geojson or a .zip containing a shapefile")
    record = UploadedFile(id=new_id(), filename=Path(filename).name[:255], file_type=extension.lstrip("."))
    path = UPLOAD_DIR / f"{record.id}{extension}"
    try:
        save_stream(stream, path)
        rows = process(record, path)
    finally:
        path.unlink(missing_ok=True)
    session.add(record)
    session.flush()
    for start in range(0, len(rows), BATCH_SIZE):
        session.execute(insert(Feature), rows[start : start + BATCH_SIZE])
    session.commit()
    return record


def too_large() -> RejectedUpload:
    return RejectedUpload(413, f"file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")


def check_declared_size(content_length: str | None):
    if content_length and content_length.isdigit() and int(content_length) > MAX_UPLOAD_BYTES + FORM_OVERHEAD:
        raise too_large()


def save_stream(stream: BinaryIO, path: Path):
    written = 0
    with path.open("wb") as target:
        while chunk := stream.read(CHUNK_SIZE):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                raise too_large()
            target.write(chunk)
    if written == 0:
        raise RejectedUpload(400, "uploaded file is empty")


def process(record: UploadedFile, path: Path) -> list[dict]:
    try:
        return extract(record, read_geofile(path))
    except UnreadableFile as exc:
        logger.warning("file %s could not be read: %s", record.id, exc)
        mark_failed(record, str(exc))
    except Exception:
        logger.exception("file %s failed while processing", record.id)
        mark_failed(record, "file could not be processed")
    return []


def mark_failed(record: UploadedFile, reason: str):
    record.feature_count = 0
    record.crs, record.crs_assumed = None, False
    record.status = "FAILED"
    record.error = reason[:500]


def extract(record: UploadedFile, frame: gpd.GeoDataFrame) -> list[dict]:
    record.crs, record.crs_assumed = detect_crs(frame)
    source_crs = frame.crs.to_wkt() if frame.crs else (WGS84 if record.crs_assumed else None)
    attributes = pd.DataFrame(frame.drop(columns=frame.geometry.name))
    properties = json.loads(attributes.to_json(orient="records", date_format="iso")) or [{}] * len(frame)
    rows = []
    for index, geometry in enumerate(frame.geometry):
        rows.append(
            {
                "file_id": record.id,
                "index": index,
                "geometry_type": geometry.geom_type if geometry is not None else None,
                "geometry": json.loads(shapely.to_geojson(geometry)) if geometry is not None else None,
                "properties": properties[index],
                **vars(measure(geometry, source_crs)),
            }
        )
    record.feature_count = len(rows)
    record.status = "COMPLETED"
    logger.info("file %s processed with %d features", record.id, record.feature_count)
    return rows


def summarise(session: Session, file_id: str) -> dict:
    query = (
        select(Feature.geometry_type, Feature.measurement_type, func.count(), func.sum(Feature.value))
        .where(Feature.file_id == file_id)
        .group_by(Feature.geometry_type, Feature.measurement_type)
    )
    summary = {"geometry_types": {}, "measured_count": 0, "area": 0.0, "length": 0.0}
    for geometry_type, measurement_type, count, total in session.execute(query):
        name = geometry_type or "no geometry"
        summary["geometry_types"][name] = summary["geometry_types"].get(name, 0) + count
        if measurement_type:
            summary["measured_count"] += count
            summary[measurement_type] += total
    return summary


def accuracy(session: Session, file_id: str, source_crs: str | None) -> dict:
    totals = {"area": [0.0, 0.0], "length": [0.0, 0.0]}
    query = select(Feature.geometry, Feature.measurement_type, Feature.value).where(
        Feature.file_id == file_id, Feature.measurement_type.is_not(None)
    )
    for geometry, measurement_type, value in session.execute(query):
        totals[measurement_type][0] += reference_measure(shape(geometry), source_crs)
        totals[measurement_type][1] += value
    return totals
