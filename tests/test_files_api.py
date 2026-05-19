from io import BytesIO

from app.core.models.analysis_batch import AnalysisBatch
from app.core.models.analysis_job import AnalysisJob
from app.core.models.eeg_file import EEGFile
from app.core.models.user import User


def test_upload_accepts_csv_and_creates_job(client, db_session, fake_minio, seed_user, seed_patient) -> None:
    response = client.post(
        "/files/upload",
        data={
            "uploaded_by_user_id": seed_user.id,
            "patient_id": seed_patient.id,
            "analysis_type": "day",
        },
        files={"file": ("signals.csv", b"time,C3,C4\n0,1,2\n1,3,4\n", "text/csv")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["file"]["original_filename"] == "signals.csv"
    assert payload["file"]["file_type"] == "csv"
    assert payload["analysis_job"]["analysis_type"] == "day"
    assert fake_minio.put_calls[0]["content_type"] == "text/csv"

    stored_file = db_session.query(EEGFile).one()
    stored_job = db_session.query(AnalysisJob).one()
    assert stored_file.object_storage_key.endswith(".csv")
    assert stored_job.eeg_file_id == stored_file.id
    assert stored_job.status == "queued"


def test_upload_accepts_edf(client, db_session, fake_minio, seed_user) -> None:
    response = client.post(
        "/files/upload",
        data={"uploaded_by_user_id": seed_user.id, "analysis_type": "night"},
        files={"file": ("study.edf", b"EDF-DATA", "application/edf")},
    )

    assert response.status_code == 200
    assert response.json()["file"]["file_type"] == "edf"
    assert next(iter(fake_minio.objects)).endswith(".edf")


def test_upload_rejects_unsupported_extension(client, seed_user) -> None:
    response = client.post(
        "/files/upload",
        data={"uploaded_by_user_id": seed_user.id, "analysis_type": "day"},
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 500
    assert "Unsupported file type: txt" in response.json()["detail"]


def test_upload_rejects_invalid_analysis_type(client, seed_user) -> None:
    response = client.post(
        "/files/upload",
        data={"uploaded_by_user_id": seed_user.id, "analysis_type": "weekly"},
        files={"file": ("study.csv", b"a,b\n1,2\n", "text/csv")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "analysis_type must be 'day' or 'night'"


def test_upload_batch_requires_at_least_two_files(client, seed_user) -> None:
    response = client.post(
        "/files/upload-batch",
        data={"uploaded_by_user_id": seed_user.id, "analysis_type": "day"},
        files=[("files", ("study.csv", b"a,b\n1,2\n", "text/csv"))],
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Batch upload requires at least 2 files"


def test_upload_batch_creates_batch_files_and_jobs(client, db_session, seed_user, seed_patient) -> None:
    response = client.post(
        "/files/upload-batch",
        data={
            "uploaded_by_user_id": seed_user.id,
            "patient_id": seed_patient.id,
            "analysis_type": "day",
        },
        files=[
            ("files", ("first.csv", b"time,C3\n0,1\n1,2\n", "text/csv")),
            ("files", ("second.edf", b"EDF-DATA", "application/edf")),
        ],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["batch"]["child_job_count"] == 2
    assert len(payload["files"]) == 2
    assert len(payload["analysis_jobs"]) == 2
    assert db_session.query(AnalysisBatch).count() == 1
    assert db_session.query(EEGFile).count() == 2
    assert db_session.query(AnalysisJob).count() == 2


def test_list_files_filters_by_patient_and_uploader(client, db_session, seed_user, seed_patient) -> None:
    other_user = User(
        email="other@example.com",
        full_name="Other User",
        password_hash="hashed-password",
    )
    db_session.add(other_user)
    db_session.commit()
    db_session.refresh(other_user)

    own_file = EEGFile(
        uploaded_by_user_id=seed_user.id,
        patient_id=seed_patient.id,
        original_filename="own.csv",
        file_type="csv",
        file_size_bytes=10,
        object_storage_key="uploads/own.csv",
    )
    other_file = EEGFile(
        uploaded_by_user_id=other_user.id,
        patient_id=None,
        original_filename="other.edf",
        file_type="edf",
        file_size_bytes=12,
        object_storage_key="uploads/other.edf",
    )
    db_session.add_all([own_file, other_file])
    db_session.commit()

    response = client.get(
        "/files/",
        params={"patient_id": seed_patient.id, "uploaded_by_user_id": seed_user.id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert [item["original_filename"] for item in payload["files"]] == ["own.csv"]


def test_get_file_metadata_returns_404_for_missing_file(client) -> None:
    response = client.get("/files/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "File not found"


def test_download_returns_original_filename_and_bytes(client, db_session, fake_minio, seed_user) -> None:
    eeg_file = EEGFile(
        uploaded_by_user_id=seed_user.id,
        patient_id=None,
        original_filename="signals.csv",
        file_type="csv",
        file_size_bytes=4,
        object_storage_key="uploads/signals.csv",
    )
    db_session.add(eeg_file)
    db_session.commit()
    db_session.refresh(eeg_file)
    fake_minio.objects[eeg_file.object_storage_key] = b"data"

    response = client.get(f"/files/{eeg_file.id}/download")

    assert response.status_code == 200
    assert response.content == b"data"
    assert response.headers["content-disposition"] == 'attachment; filename="signals.csv"'


def test_delete_removes_file_record_and_storage_object(client, db_session, fake_minio, seed_user) -> None:
    eeg_file = EEGFile(
        uploaded_by_user_id=seed_user.id,
        patient_id=None,
        original_filename="signals.edf",
        file_type="edf",
        file_size_bytes=7,
        object_storage_key="uploads/signals.edf",
    )
    db_session.add(eeg_file)
    db_session.commit()
    db_session.refresh(eeg_file)
    fake_minio.objects[eeg_file.object_storage_key] = b"payload"

    response = client.delete(f"/files/{eeg_file.id}")

    assert response.status_code == 200
    assert db_session.query(EEGFile).count() == 0
    assert fake_minio.objects == {}


def test_upload_rolls_back_database_changes_on_storage_failure(
    client,
    db_session,
    fake_minio,
    monkeypatch,
    seed_user,
) -> None:
    def fail_put_object(**_kwargs) -> None:
        raise RuntimeError("storage is down")

    monkeypatch.setattr(fake_minio, "put_object", fail_put_object)

    response = client.post(
        "/files/upload",
        data={"uploaded_by_user_id": seed_user.id, "analysis_type": "day"},
        files={"file": ("signals.csv", b"time,C3\n0,1\n", "text/csv")},
    )

    assert response.status_code == 500
    assert "storage is down" in response.json()["detail"]
    assert db_session.query(EEGFile).count() == 0
    assert db_session.query(AnalysisJob).count() == 0
