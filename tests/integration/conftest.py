from collections.abc import Generator
import os

import pytest
from fastapi.testclient import TestClient

from app.core.database import Base, SessionLocal, engine
from app.core.file_storage import S3_BUCKET, ensure_bucket_exists, minio_client
from app.main import app


def _assert_isolated_test_environment() -> None:
    database_url = os.getenv("DATABASE_URL", "")
    if "test" not in database_url.lower():
        raise RuntimeError(
            "Integration tests require a dedicated test DATABASE_URL. "
            "Refusing to run against a non-test database."
        )

    if "test" not in S3_BUCKET.lower():
        raise RuntimeError(
            "Integration tests require a dedicated test S3_BUCKET. "
            "Refusing to run against a non-test bucket."
        )


def _clear_bucket() -> None:
    ensure_bucket_exists()
    for obj in minio_client.list_objects(S3_BUCKET, recursive=True):
        minio_client.remove_object(S3_BUCKET, obj.object_name)


@pytest.fixture(autouse=True)
def reset_integration_state() -> Generator[None]:
    _assert_isolated_test_environment()
    _clear_bucket()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    try:
        yield
    finally:
        _clear_bucket()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client() -> Generator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
