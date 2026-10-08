from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_session
from app.measure import convert
from app.models import Feature, UploadedFile
from app.schemas import (
    AreaUnit, FeaturePage, FileOut, FilePage, LengthUnit, MeasurementOut, MeasurementPage, SummaryOut,
)
from app.services import RejectedUpload, handle_upload, summarise

router = APIRouter(prefix="/api/files", tags=["files"])


def get_file(file_id: str, session: Session = Depends(get_session)) -> UploadedFile:
    record = session.get(UploadedFile, file_id)
    if record is None:
        raise HTTPException(404, "file not found")
    return record


def feature_page(session: Session, file_id: str, limit: int, offset: int) -> list[Feature]:
    query = select(Feature).where(Feature.file_id == file_id).order_by(Feature.index)
    return list(session.scalars(query.limit(limit).offset(offset)))


@router.post("/", response_model=FileOut, status_code=201)
def upload_file(file: UploadFile, session: Session = Depends(get_session)):
    try:
        record = handle_upload(session, file.filename or "", file.file)
    except RejectedUpload as exc:
        raise HTTPException(exc.status_code, exc.message)
    if record.status == "FAILED":
        body = FileOut.model_validate(record).model_dump(mode="json")
        return JSONResponse(body, status_code=422)
    return record


@router.get("/", response_model=FilePage)
def list_files(
    session: Session = Depends(get_session),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    total = session.scalar(select(func.count()).select_from(UploadedFile))
    query = select(UploadedFile).order_by(UploadedFile.created_at.desc(), UploadedFile.id)
    files = list(session.scalars(query.limit(limit).offset(offset)))
    return FilePage(total=total, limit=limit, offset=offset, files=files)


@router.get("/{file_id}/", response_model=FileOut)
def file_info(record: UploadedFile = Depends(get_file)):
    return record


@router.delete("/{file_id}/", status_code=204)
def delete_file(record: UploadedFile = Depends(get_file), session: Session = Depends(get_session)):
    session.delete(record)
    session.commit()


@router.get("/{file_id}/features/", response_model=FeaturePage)
def file_features(
    record: UploadedFile = Depends(get_file),
    session: Session = Depends(get_session),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    features = feature_page(session, record.id, limit, offset)
    return FeaturePage(
        file_id=record.id, crs=record.crs, total=record.feature_count,
        limit=limit, offset=offset, features=features,
    )


@router.get("/{file_id}/measurements/", response_model=MeasurementPage)
def file_measurements(
    record: UploadedFile = Depends(get_file),
    session: Session = Depends(get_session),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    area_unit: AreaUnit = AreaUnit.square_metre,
    length_unit: LengthUnit = LengthUnit.metre,
):
    measurements = []
    for feature in feature_page(session, record.id, limit, offset):
        item = MeasurementOut.model_validate(feature)
        item.value, item.unit = convert(item.measurement_type, item.value, area_unit.value, length_unit.value)
        measurements.append(item)
    return MeasurementPage(
        file_id=record.id, total=record.feature_count,
        limit=limit, offset=offset, measurements=measurements,
    )


@router.get("/{file_id}/summary/", response_model=SummaryOut)
def file_summary(
    record: UploadedFile = Depends(get_file),
    session: Session = Depends(get_session),
    area_unit: AreaUnit = AreaUnit.square_metre,
    length_unit: LengthUnit = LengthUnit.metre,
):
    summary = summarise(session, record.id)
    total_area, _ = convert("area", summary["area"], area_unit.value, length_unit.value)
    total_length, _ = convert("length", summary["length"], area_unit.value, length_unit.value)
    return SummaryOut(
        file_id=record.id, feature_count=record.feature_count, measured_count=summary["measured_count"],
        geometry_types=summary["geometry_types"], total_area=total_area, area_unit=area_unit.value,
        total_length=total_length, length_unit=length_unit.value,
    )
