from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.core.analysis_views import summarize_batch_jobs
from app.core.database import get_db
from app.core.models.analysis_batch import AnalysisBatch
from app.core.models.analysis_job import AnalysisJob
from app.core.models.analysis_result import AnalysisResult
from app.core.models.eeg_file import EEGFile
from app.core.models.user import User
from app.core.models.user_session import UserSession
from app.core.security import (
    get_current_session,
    get_current_user,
    hash_password,
    utcnow,
    verify_password,
)

router = APIRouter(prefix="/account", tags=["account"])

ALLOWED_ROLES = {"doctor", "researcher"}


class ProfileStatsResponse(BaseModel):
    analysis_count: int
    patient_count: int
    file_count: int
    last_activity_at: datetime | None = None


class AccountProfileResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    organization: str | None = None
    role: str
    default_age_group: str | None = None
    password_changed_at: datetime | None = None
    created_at: datetime
    stats: ProfileStatsResponse


class UpdateProfileRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    organization: str | None = Field(default=None, max_length=255)
    role: str = Field(min_length=1, max_length=50)
    default_age_group: str | None = Field(default=None, max_length=20)


class SessionResponse(BaseModel):
    id: int
    user_agent: str | None = None
    ip_address: str | None = None
    created_at: datetime
    last_seen_at: datetime
    revoked_at: datetime | None = None
    is_current: bool


class SecurityOverviewResponse(BaseModel):
    password_changed_at: datetime | None = None
    sessions: list[SessionResponse]


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=255)
    new_password: str = Field(min_length=8, max_length=255)
    confirm_password: str = Field(min_length=8, max_length=255)


class AccountHistoryItemResponse(BaseModel):
    id: int
    kind: str
    file_id: int | None = None
    batch_id: int | None = None
    child_job_count: int = 1
    file_name: str
    analysis_type: str
    status: str
    bands: list[str]
    duration_seconds: float | None = None
    queued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result_created_at: datetime | None = None
    result_url: str


class AccountHistoryResponse(BaseModel):
    total: int
    items: list[AccountHistoryItemResponse]


def _normalize_role(role: str) -> str:
    normalized = role.strip().lower()
    if normalized not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"role must be one of {sorted(ALLOWED_ROLES)}",
        )
    return normalized


def _profile_stats_for_user(db: Session, user_id: int) -> ProfileStatsResponse:
    analysis_count = db.execute(
        select(func.count(AnalysisJob.id))
        .select_from(AnalysisJob)
        .join(EEGFile, EEGFile.id == AnalysisJob.eeg_file_id)
        .where(EEGFile.uploaded_by_user_id == user_id)
    ).scalar_one()

    patient_count = db.execute(
        select(func.count(distinct(EEGFile.patient_id)))
        .select_from(EEGFile)
        .where(
            EEGFile.uploaded_by_user_id == user_id,
            EEGFile.patient_id.is_not(None),
        )
    ).scalar_one()

    file_count = db.execute(
        select(func.count(EEGFile.id)).where(EEGFile.uploaded_by_user_id == user_id)
    ).scalar_one()

    last_activity_at = db.execute(
        select(func.max(AnalysisJob.finished_at))
        .select_from(AnalysisJob)
        .join(EEGFile, EEGFile.id == AnalysisJob.eeg_file_id)
        .where(EEGFile.uploaded_by_user_id == user_id)
    ).scalar_one()

    return ProfileStatsResponse(
        analysis_count=analysis_count,
        patient_count=patient_count,
        file_count=file_count,
        last_activity_at=last_activity_at,
    )


def _build_profile_response(db: Session, user: User) -> AccountProfileResponse:
    return AccountProfileResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        organization=user.organization,
        role=user.role,
        default_age_group=user.default_age_group,
        password_changed_at=user.password_changed_at,
        created_at=user.created_at,
        stats=_profile_stats_for_user(db, user.id),
    )


def _extract_bands(result_json: dict[str, Any] | None) -> list[str]:
    if not isinstance(result_json, dict):
        return []

    preferred_keys = ("bands", "band_names", "frequency_bands")
    for key in preferred_keys:
        value = result_json.get(key)
        if isinstance(value, list):
            return [str(item) for item in value]

    discovered_bands: set[str] = set()
    expected_names = {"delta", "theta", "alpha", "beta", "gamma"}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if isinstance(key, str) and key.lower() in expected_names:
                    discovered_bands.add(key.capitalize())
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(result_json)
    return sorted(discovered_bands)


def _extract_duration_seconds(result_json: dict[str, Any] | None) -> float | None:
    if not isinstance(result_json, dict):
        return None

    candidate_keys = (
        "duration_seconds",
        "duration_sec",
        "duration",
        "recording_duration_seconds",
        "recording_length_seconds",
    )
    for key in candidate_keys:
        value = result_json.get(key)
        if isinstance(value, (int, float)):
            return float(value)

    return None


@router.get("/profile", response_model=AccountProfileResponse)
def get_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _build_profile_response(db, current_user)


@router.put("/profile", response_model=AccountProfileResponse)
def update_profile(
    payload: UpdateProfileRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing_user = (
        db.query(User)
        .filter(User.email == payload.email, User.id != current_user.id)
        .first()
    )
    if existing_user is not None:
        raise HTTPException(status_code=400, detail="Email is already registered")

    current_user.full_name = payload.full_name.strip()
    current_user.email = payload.email
    current_user.organization = payload.organization.strip() if payload.organization else None
    current_user.role = _normalize_role(payload.role)
    current_user.default_age_group = (
        payload.default_age_group.strip() if payload.default_age_group else None
    )

    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return _build_profile_response(db, current_user)


@router.get("/security", response_model=SecurityOverviewResponse)
def get_security_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_session: UserSession = Depends(get_current_session),
):
    sessions = (
        db.query(UserSession)
        .filter(
            UserSession.user_id == current_user.id,
            UserSession.revoked_at.is_(None),
        )
        .order_by(UserSession.last_seen_at.desc(), UserSession.id.desc())
        .all()
    )

    return SecurityOverviewResponse(
        password_changed_at=current_user.password_changed_at,
        sessions=[
            SessionResponse(
                id=session.id,
                user_agent=session.user_agent,
                ip_address=session.ip_address,
                created_at=session.created_at,
                last_seen_at=session.last_seen_at,
                revoked_at=session.revoked_at,
                is_current=session.id == current_session.id,
            )
            for session in sessions
        ],
    )


@router.post("/security/password")
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_session: UserSession = Depends(get_current_session),
):
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="New passwords do not match")

    if payload.current_password == payload.new_password:
        raise HTTPException(
            status_code=400,
            detail="New password must be different from the current password",
        )

    current_user.password_hash = hash_password(payload.new_password)
    current_user.password_changed_at = utcnow()
    db.add(current_user)
    (
        db.query(UserSession)
        .filter(
            UserSession.user_id == current_user.id,
            UserSession.id != current_session.id,
            UserSession.revoked_at.is_(None),
        )
        .update({UserSession.revoked_at: utcnow()}, synchronize_session=False)
    )
    db.commit()
    return {"message": "Password changed successfully"}


@router.delete("/security/sessions/{session_id}")
def revoke_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = (
        db.query(UserSession)
        .filter(
            UserSession.id == session_id,
            UserSession.user_id == current_user.id,
            UserSession.revoked_at.is_(None),
        )
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    session.revoked_at = utcnow()
    db.add(session)
    db.commit()
    return {"message": "Session revoked successfully", "session_id": session_id}


@router.get("/history", response_model=AccountHistoryResponse)
def get_history(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    standalone_rows = (
        db.query(AnalysisJob, EEGFile, AnalysisResult)
        .join(EEGFile, EEGFile.id == AnalysisJob.eeg_file_id)
        .outerjoin(AnalysisResult, AnalysisResult.analysis_job_id == AnalysisJob.id)
        .filter(
            EEGFile.uploaded_by_user_id == current_user.id,
            AnalysisJob.batch_id.is_(None),
        )
        .order_by(
            AnalysisJob.finished_at.desc().nullslast(),
            AnalysisJob.queued_at.desc(),
            AnalysisJob.id.desc(),
        )
        .all()
    )

    batches = (
        db.query(AnalysisBatch)
        .filter(AnalysisBatch.uploaded_by_user_id == current_user.id)
        .order_by(AnalysisBatch.created_at.desc(), AnalysisBatch.id.desc())
        .all()
    )

    items: list[AccountHistoryItemResponse] = [
        AccountHistoryItemResponse(
            id=job.id,
            kind="job",
            file_id=eeg_file.id,
            batch_id=job.batch_id,
            child_job_count=1,
            file_name=eeg_file.original_filename,
            analysis_type=job.analysis_type,
            status=job.status,
            bands=_extract_bands(result.result_json if result else None),
            duration_seconds=_extract_duration_seconds(result.result_json if result else None),
            queued_at=job.queued_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            result_created_at=result.created_at if result else None,
            result_url=f"/analysis-jobs/{job.id}/result",
        )
        for job, eeg_file, result in standalone_rows
    ]

    for batch in batches:
        rows = (
            db.query(AnalysisJob, EEGFile, AnalysisResult)
            .join(EEGFile, EEGFile.id == AnalysisJob.eeg_file_id)
            .outerjoin(AnalysisResult, AnalysisResult.analysis_job_id == AnalysisJob.id)
            .filter(AnalysisJob.batch_id == batch.id)
            .order_by(AnalysisJob.queued_at.asc(), AnalysisJob.id.asc())
            .all()
        )
        if not rows:
            continue

        jobs = [job for job, _, _ in rows]
        summary = summarize_batch_jobs(jobs)
        all_bands = sorted(
            {
                band
                for _, _, result in rows
                for band in _extract_bands(result.result_json if result else None)
            }
        )
        items.append(
            AccountHistoryItemResponse(
                id=batch.id,
                kind="batch",
                batch_id=batch.id,
                child_job_count=summary["total_jobs"],
                file_name=f"{summary['total_jobs']} failu paketas",
                analysis_type=batch.analysis_type,
                status=summary["status"],
                bands=all_bands,
                duration_seconds=None,
                queued_at=batch.created_at,
                started_at=summary["started_at"],
                finished_at=summary["finished_at"],
                result_created_at=None,
                result_url=f"/analysis-batches/{batch.id}",
            )
        )

    items.sort(
        key=lambda item: item.finished_at or item.queued_at,
        reverse=True,
    )

    return AccountHistoryResponse(
        total=len(items),
        items=items[:limit],
    )
