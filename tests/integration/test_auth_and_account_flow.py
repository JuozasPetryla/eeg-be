import pytest

from app.core.models.patient import Patient


pytestmark = pytest.mark.integration


def _register_user(client, email: str = "doctor@example.com", password: str = "password123"):
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "full_name": "Dr. Integration",
            "password": password,
            "organization": "Clinic",
            "role": "doctor",
        },
    )
    assert response.status_code == 201
    return response.json()


def _login_user(client, email: str = "doctor@example.com", password: str = "password123") -> str:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={
            "user-agent": "pytest-integration",
            "x-forwarded-for": "203.0.113.10",
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_auth_login_me_and_security_flow(client) -> None:
    registered_user = _register_user(client)
    token = _login_user(client)
    headers = {"Authorization": f"Bearer {token}"}

    me_response = client.get("/auth/me", headers=headers)
    assert me_response.status_code == 200
    assert me_response.json()["email"] == registered_user["email"]

    security_response = client.get("/account/security", headers=headers)
    assert security_response.status_code == 200
    security_payload = security_response.json()
    assert len(security_payload["sessions"]) == 1
    assert security_payload["sessions"][0]["is_current"] is True
    assert security_payload["sessions"][0]["user_agent"] == "pytest-integration"
    assert security_payload["sessions"][0]["ip_address"] == "203.0.113.10"


def test_profile_stats_reflect_uploaded_analysis_job(client, db_session) -> None:
    registered_user = _register_user(client)
    token = _login_user(client)
    headers = {"Authorization": f"Bearer {token}"}

    patient = Patient(
        external_patient_id="INT-001",
        age_years=42,
        sex="male",
    )
    db_session.add(patient)
    db_session.commit()
    db_session.refresh(patient)

    upload_response = client.post(
        "/files/upload",
        data={
            "uploaded_by_user_id": registered_user["id"],
            "patient_id": patient.id,
            "analysis_type": "day",
        },
        files={"file": ("profile.csv", b"time,C3\n0,1\n1,2\n", "text/csv")},
    )
    assert upload_response.status_code == 200

    profile_response = client.get("/account/profile", headers=headers)
    assert profile_response.status_code == 200
    profile_payload = profile_response.json()
    assert profile_payload["stats"]["analysis_count"] == 1
    assert profile_payload["stats"]["patient_count"] == 1
    assert profile_payload["stats"]["file_count"] == 1
