from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.models.user import User
from app.core.models.user_session import UserSession
from app.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    utcnow,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])
ALLOWED_ROLES = {"doctor", "researcher"}


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    organization: str | None = None
    role: str
    default_age_group: str | None = None
    password_changed_at: datetime | None = None
    created_at: datetime


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=255)
    organization: str | None = Field(default=None, max_length=255)
    role: str = Field(default="doctor", min_length=1, max_length=50)
    default_age_group: str | None = Field(default=None, max_length=20)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=255)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


def _normalize_role(role: str) -> str:
    normalized = role.strip().lower()
    if normalized not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"role must be one of {sorted(ALLOWED_ROLES)}",
        )
    return normalized


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(payload: RegisterRequest, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user is not None:
        raise HTTPException(status_code=400, detail="Email is already registered")

    user = User(
        email=payload.email,
        full_name=payload.full_name.strip(),
        organization=payload.organization.strip() if payload.organization else None,
        role=_normalize_role(payload.role),
        default_age_group=payload.default_age_group.strip() if payload.default_age_group else None,
        password_hash=hash_password(payload.password),
        password_changed_at=utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login_user(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    forwarded_for = request.headers.get("x-forwarded-for")
    ip_address = (
        forwarded_for.split(",")[0].strip()
        if forwarded_for
        else (request.client.host if request.client else None)
    )
    session = UserSession(
        user_id=user.id,
        user_agent=request.headers.get("user-agent"),
        ip_address=ip_address,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return TokenResponse(
        access_token=create_access_token(user.id, session.id),
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user
