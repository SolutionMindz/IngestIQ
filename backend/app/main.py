import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.models.base import init_db
from app.api import documents, structure, comparison, validation, audit, a2i

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings().get_upload_path()
    init_db()
    yield
    pass


app = FastAPI(title="Knowledge Ingestion API", lifespan=lifespan)

# CORS first so all responses (including errors) get CORS headers
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://new.packt.localhost:8003",
        "http://new.packt.localhost:8004",
        "http://127.0.0.1:8003",
        "http://127.0.0.1:8004",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://localhost:8003",
        "http://localhost:8004",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "type": type(exc).__name__},
    )

app.include_router(documents.router, prefix="/api", tags=["documents"])
app.include_router(structure.router, prefix="/api", tags=["structure"])
app.include_router(comparison.router, prefix="/api", tags=["comparison"])
app.include_router(validation.router, prefix="/api", tags=["validation"])
app.include_router(audit.router, prefix="/api", tags=["audit"])
app.include_router(a2i.router, prefix="/api", tags=["a2i"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/health")
def api_health():
    return {"status": "ok"}
