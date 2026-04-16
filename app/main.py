import app.db.base
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth, users, files, analysis_results
from app.core.file_storage import ensure_bucket_exists

logger = logging.getLogger(__name__)
app = FastAPI()

@app.on_event("startup")
def startup():
    try:
        ensure_bucket_exists()
    except RuntimeError as exc:
        logger.warning("Skipping eager MinIO initialization during startup: %s", exc)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(files.router)
app.include_router(analysis_results.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}
