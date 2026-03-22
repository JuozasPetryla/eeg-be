import app.db.base

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import users, files
from app.core.file_storage import ensure_bucket_exists

app = FastAPI()

@app.on_event("startup")
def startup():
    ensure_bucket_exists()

app.include_router(users.router)
app.include_router(files.router)

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
