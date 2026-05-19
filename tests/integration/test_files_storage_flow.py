import pytest

from app.core.models.patient import Patient


pytestmark = pytest.mark.integration


def _register_user(client):
    response = client.post(
        "/auth/register",
        json={
            "email": "storage@example.com",
            "full_name": "Storage User",
            "password": "password123",
            "organization": "Clinic",
            "role": "doctor",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_upload_download_delete_roundtrip_with_real_minio_and_postgres(client, db_session) -> None:
    user = _register_user(client)

    patient = Patient(
        external_patient_id="ROUNDTRIP-001",
        age_years=29,
        sex="female",
    )
    db_session.add(patient)
    db_session.commit()
    db_session.refresh(patient)

    upload_response = client.post(
        "/files/upload",
        data={
            "uploaded_by_user_id": user["id"],
            "patient_id": patient.id,
            "analysis_type": "day",
        },
        files={"file": ("signals.csv", b"time,C3,C4\n0,1,2\n1,3,4\n", "text/csv")},
    )
    assert upload_response.status_code == 200
    upload_payload = upload_response.json()
    file_id = upload_payload["file"]["id"]

    list_response = client.get(
        "/files/",
        params={"uploaded_by_user_id": user["id"], "patient_id": patient.id},
    )
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert list_response.json()["files"][0]["original_filename"] == "signals.csv"

    download_response = client.get(f"/files/{file_id}/download")
    assert download_response.status_code == 200
    assert download_response.content == b"time,C3,C4\n0,1,2\n1,3,4\n"
    assert download_response.headers["content-disposition"] == 'attachment; filename="signals.csv"'

    delete_response = client.delete(f"/files/{file_id}")
    assert delete_response.status_code == 200

    metadata_response = client.get(f"/files/{file_id}")
    assert metadata_response.status_code == 404
