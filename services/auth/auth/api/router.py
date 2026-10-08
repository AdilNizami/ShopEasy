from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth.api.schemas import AccessTokenResponse, CredentialsRequest, CurrentUserResponse
from auth.infrastructure.database import SessionLocal
from auth.infrastructure.models import UserRecord
from auth.settings import settings
from service_common.identity import (
    Principal,
    TokenConfigurationError,
    get_current_principal,
    issue_access_token,
    validate_signing_configuration,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])
password_hasher = PasswordHash.recommended()
dummy_password_hash = password_hasher.hash(secrets.token_urlsafe(32))


def get_session():
    with SessionLocal() as session:
        yield session


def _issue_response(user: UserRecord) -> AccessTokenResponse:
    try:
        operator_ids = {
            value.strip() for value in settings.engineering_operator_ids.split(",") if value.strip()
        }
        role = "operator" if str(user.id) in operator_ids else "customer"
        token = issue_access_token(user.id, user.username, settings.access_token_ttl_seconds, role)
    except TokenConfigurationError as exc:
        raise HTTPException(status_code=503, detail="Authentication is not configured.") from exc
    return AccessTokenResponse(
        access_token=token,
        expires_in=settings.access_token_ttl_seconds,
        user_id=user.id,
    )


@router.post("/register", response_model=AccessTokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: CredentialsRequest,
    session: Session = Depends(get_session),
) -> AccessTokenResponse:
    try:
        validate_signing_configuration()
    except TokenConfigurationError as exc:
        raise HTTPException(status_code=503, detail="Authentication is not configured.") from exc
    username = payload.username.strip().lower()
    user = UserRecord(username=username, password_hash=password_hasher.hash(payload.password))
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Username is already registered.") from exc
    session.refresh(user)
    return _issue_response(user)


@router.post("/login", response_model=AccessTokenResponse)
def login(
    payload: CredentialsRequest,
    session: Session = Depends(get_session),
) -> AccessTokenResponse:
    try:
        validate_signing_configuration()
    except TokenConfigurationError as exc:
        raise HTTPException(status_code=503, detail="Authentication is not configured.") from exc
    username = payload.username.strip().lower()
    user = session.scalar(select(UserRecord).where(UserRecord.username == username))
    stored_hash = user.password_hash if user is not None else dummy_password_hash
    password_matches = password_hasher.verify(payload.password, stored_hash)
    if user is None or not password_matches:
        raise HTTPException(
            status_code=401,
            detail="Username or password is incorrect.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _issue_response(user)


@router.get("/me", response_model=CurrentUserResponse)
def current_user(principal: Principal = Depends(get_current_principal)) -> CurrentUserResponse:
    return CurrentUserResponse(
        user_id=principal.user_id, username=principal.username, role=principal.role
    )
