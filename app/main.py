import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.config import CORS_ORIGINS, LOG_LEVEL
from app.database import init_db
from app.routes import router
from app.services import RejectedUpload, check_declared_size


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    init_db()
    yield


app = FastAPI(title="Geospatial File Measurement API", lifespan=lifespan)
app.include_router(router)


@app.middleware("http")
async def accept_missing_trailing_slash(request: Request, call_next):
    path = request.scope["path"]
    if path.startswith("/api/") and not path.endswith("/"):
        request.scope["path"] = path + "/"
    return await call_next(request)


@app.middleware("http")
async def reject_oversized_body(request: Request, call_next):
    try:
        check_declared_size(request.headers.get("content-length"))
    except RejectedUpload as exc:
        return JSONResponse({"detail": exc.message}, status_code=exc.status_code)
    return await call_next(request)


app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@app.get("/health")
def health():
    return {"status": "ok"}
