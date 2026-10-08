from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

from app.database import init_db
from app.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
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


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@app.get("/health")
def health():
    return {"status": "ok"}
