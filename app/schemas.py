from datetime import datetime

from pydantic import BaseModel, ConfigDict


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


class FeatureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    index: int
    geometry_type: str | None
    geometry: dict | None
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
