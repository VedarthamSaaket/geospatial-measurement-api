from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import Feature, UploadedFile
from app.schemas import FeaturePage, FileOut, MeasurementPage
from app.services import RejectedUpload, handle_upload

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


@router.get("/{file_id}/", response_model=FileOut)
def file_info(record: UploadedFile = Depends(get_file)):
    return record


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
):
    features = feature_page(session, record.id, limit, offset)
    return MeasurementPage(
        file_id=record.id, total=record.feature_count,
        limit=limit, offset=offset, measurements=features,
    )
