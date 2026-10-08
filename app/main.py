from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models
from app.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Geospatial File Measurement API", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}
