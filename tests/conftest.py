from collections.abc import Generator
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.core.models.analysis_batch import AnalysisBatch
from app.core.models.analysis_job import AnalysisJob
from app.core.models.eeg_file import EEGFile
from app.core.models.patient import Patient
from app.core.models.user import User
from app.core.models.user_session import UserSession


class FakeMinioClient:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.put_calls: list[dict[str, object]] = []

    def put_object(
        self,
        *,
        bucket_name: str,
        object_name: str,
        data,
        length: int,
        content_type: str,
    ) -> None:
        payload = data.read()
        self.objects[object_name] = payload
        self.put_calls.append(
            {
                "bucket_name": bucket_name,
                "object_name": object_name,
                "length": length,
                "content_type": content_type,
            }
        )

    def get_object(self, bucket_name: str, object_name: str) -> BytesIO:
        return BytesIO(self.objects[object_name])

    def remove_object(self, bucket_name: str, object_name: str) -> None:
        self.objects.pop(object_name)


@pytest.fixture()
def db_session() -> Generator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    TestingSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )

    tables = [
        User.__table__,
        Patient.__table__,
        AnalysisBatch.__table__,
        EEGFile.__table__,
        AnalysisJob.__table__,
        UserSession.__table__,
    ]
    for table in tables:
        table.create(bind=engine)
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()
        for table in reversed(tables):
            table.drop(bind=engine)
        engine.dispose()


@pytest.fixture()
def fake_minio() -> FakeMinioClient:
    return FakeMinioClient()


@pytest.fixture()
def client(db_session: Session, fake_minio: FakeMinioClient, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient]:
    from app.api import files as files_api
    from app.main import app

    def override_get_db() -> Generator[Session]:
        yield db_session

    monkeypatch.setenv("DEV_AUTH_BYPASS", "true")
    monkeypatch.setenv("DEV_AUTH_DEFAULT_EMAIL", "doctor@example.com")
    monkeypatch.setattr("app.main.ensure_bucket_exists", lambda: None)
    monkeypatch.setattr(files_api, "ensure_bucket_exists", lambda: None)
    monkeypatch.setattr(files_api, "minio_client", fake_minio)

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture()
def seed_user(db_session: Session) -> User:
    user = User(
        email="doctor@example.com",
        full_name="Dr. Test",
        password_hash="hashed-password",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def seed_patient(db_session: Session) -> Patient:
    patient = Patient(
        external_patient_id="PAT-001",
        age_years=30,
        sex="female",
    )
    db_session.add(patient)
    db_session.commit()
    db_session.refresh(patient)
    return patient
