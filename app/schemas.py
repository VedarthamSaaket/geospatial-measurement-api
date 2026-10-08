from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator

from app.measure import AREA_UNITS, LENGTH_UNITS

AreaUnit = Enum("AreaUnit", {name: name for name in AREA_UNITS}, type=str)
LengthUnit = Enum("LengthUnit", {name: name for name in LENGTH_UNITS}, type=str)


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    file_type: str
    feature_count: int
    crs: str | None
    crs_assumed: bool
    status: str
    error: str | None
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def as_utc(cls, value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class FilePage(BaseModel):
    total: int
    limit: int
    offset: int
    files: list[FileOut]


class FeatureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    index: int
    geometry_type: str | None
    geometry: dict | None
    crs: str | None
    properties: dict


class MeasurementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    index: int
    geometry_type: str | None
    measurement_type: str | None
    value: float | None
    unit: str | None
    measurement_crs: str | None
    note: str | None


class FeaturePage(BaseModel):
    file_id: str
    crs: str | None
    total: int
    limit: int
    offset: int
    features: list[FeatureOut]


class MeasurementPage(BaseModel):
    file_id: str
    total: int
    limit: int
    offset: int
    measurements: list[MeasurementOut]


class SummaryOut(BaseModel):
    file_id: str
    feature_count: int
    measured_count: int
    geometry_types: dict[str, int]
    total_area: float
    area_unit: str
    total_length: float
    length_unit: str
