import json
from pathlib import Path
from typing import BinaryIO

import pandas as pd
import shapely
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES, UPLOAD_DIR
from app.measure import WGS84, measure
from app.models import Feature, UploadedFile, new_id
from app.readers import UnreadableFile, detect_crs, read_geofile

CHUNK_SIZE = 1024 * 1024


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
        process(record, path)
    finally:
        path.unlink(missing_ok=True)
    session.add(record)
    session.commit()
    return record


def save_stream(stream: BinaryIO, path: Path):
    written = 0
    with path.open("wb") as target:
        while chunk := stream.read(CHUNK_SIZE):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                raise RejectedUpload(413, f"file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
            target.write(chunk)
    if written == 0:
        raise RejectedUpload(400, "uploaded file is empty")


def process(record: UploadedFile, path: Path):
    try:
        frame = read_geofile(path)
    except UnreadableFile as exc:
        record.status = "FAILED"
        record.error = str(exc)[:500]
        return
    record.crs, record.crs_assumed = detect_crs(frame)
    source_crs = frame.crs.to_wkt() if frame.crs else (WGS84 if record.crs_assumed else None)
    attributes = pd.DataFrame(frame.drop(columns=frame.geometry.name))
    properties = json.loads(attributes.to_json(orient="records", date_format="iso")) or [{}] * len(frame)
    for index, geometry in enumerate(frame.geometry):
        result = measure(geometry, source_crs)
        record.features.append(
            Feature(
                index=index,
                geometry_type=geometry.geom_type if geometry is not None else None,
                geometry=json.loads(shapely.to_geojson(geometry)) if geometry is not None else None,
                properties=properties[index],
                **vars(result),
            )
        )
    record.feature_count = len(record.features)
    record.status = "COMPLETED"


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
