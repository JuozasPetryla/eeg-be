import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.models.user import User
from app.core.models.user_session import UserSession

PASSWORD_HASH_SCHEME = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = int(os.getenv("PASSWORD_HASH_ITERATIONS", "100000"))
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
DEV_AUTH_EMAIL_HEADER = "x-dev-user-email"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived_key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    return (
        f"{PASSWORD_HASH_SCHEME}${PASSWORD_HASH_ITERATIONS}$"
        f"{base64.b64encode(salt).decode('utf-8')}$"
        f"{base64.b64encode(derived_key).decode('utf-8')}"
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, iteration_text, salt_b64, hash_b64 = stored_hash.split("$", 3)
    except ValueError:
        return False

    if scheme != PASSWORD_HASH_SCHEME:
        return False

    try:
        iterations = int(iteration_text)
        salt = base64.b64decode(salt_b64)
        expected_hash = base64.b64decode(hash_b64)
    except (ValueError, TypeError):
        return False

    candidate_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(candidate_hash, expected_hash)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(
    user_id: int,
    session_id: int | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    expire_at = utcnow() + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": str(user_id),
        "exp": expire_at,
    }
    if session_id is not None:
        payload["sid"] = str(session_id)
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])


def _dev_auth_bypass_enabled() -> bool:
    return os.getenv("DEV_AUTH_BYPASS", "").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_dev_bypass_user(request: Request, db: Session) -> User | None:
    if not _dev_auth_bypass_enabled():
        return None

    email = (
        request.headers.get(DEV_AUTH_EMAIL_HEADER)
        or os.getenv("DEV_AUTH_DEFAULT_EMAIL", "doctor@example.com")
    ).strip().lower()
    if not email:
        return None

    user = db.query(User).filter(User.email == email).first()
    if user is not None:
        return user

    user = User(
        email=email,
        full_name=os.getenv("DEV_AUTH_DEFAULT_NAME", "Dev User"),
        role="doctor",
        password_hash=hash_password("dev-auth-bypass-password"),
        password_changed_at=utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _resolve_dev_bypass_session(request: Request, db: Session, user: User) -> UserSession:
    session = (
        db.query(UserSession)
        .filter(
            UserSession.user_id == user.id,
            UserSession.user_agent == "dev-auth-bypass",
            UserSession.revoked_at.is_(None),
        )
        .order_by(UserSession.id.desc())
        .first()
    )
    if session is None:
        session = UserSession(
            user_id=user.id,
            user_agent="dev-auth-bypass",
            ip_address=request.client.host if request.client else None,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    db.execute(
        update(UserSession)
        .where(UserSession.id == session.id)
        .values(last_seen_at=utcnow())
    )
    db.commit()
    db.refresh(session)
    return session


def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        bypass_user = _resolve_dev_bypass_user(request, db)
        if bypass_user is not None:
            return bypass_user
        raise credentials_error

    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
        session_id = payload.get("sid")
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise credentials_error

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_error

    if session_id is not None:
        session = db.execute(
            select(UserSession).where(
                UserSession.id == int(session_id),
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
            )
        ).scalar_one_or_none()
        if session is None:
            raise credentials_error

        db.execute(
            update(UserSession)
            .where(UserSession.id == session.id)
            .values(last_seen_at=utcnow())
        )
        db.commit()

    return user


def get_current_session(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> UserSession:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        bypass_user = _resolve_dev_bypass_user(request, db)
        if bypass_user is not None:
            return _resolve_dev_bypass_session(request, db, bypass_user)
        raise credentials_error

    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
        session_id = int(payload["sid"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise credentials_error

    session = db.execute(
        select(UserSession).where(
            UserSession.id == session_id,
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
        )
    ).scalar_one_or_none()
    if session is None:
        raise credentials_error

    db.execute(
        update(UserSession)
        .where(UserSession.id == session.id)
        .values(last_seen_at=utcnow())
    )
    db.commit()
    db.refresh(session)
    return session
