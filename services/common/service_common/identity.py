from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError

TOKEN_ISSUER = "shopeasy-auth"
TOKEN_AUDIENCE = "shopeasy-api"
bearer_scheme = HTTPBearer(auto_error=False)


class TokenConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    username: str
    access_token: str = field(default="", repr=False, compare=False)
    role: str = "customer"


def _signing_secret() -> str:
    secret = os.getenv("AUTH_JWT_SECRET", "")
    if len(secret.encode("utf-8")) < 32:
        raise TokenConfigurationError("AUTH_JWT_SECRET must contain at least 32 bytes.")
    return secret


def validate_signing_configuration() -> None:
    """Fail before persisting a registration if token signing is misconfigured."""
    _signing_secret()


def issue_access_token(
    user_id: UUID,
    username: str,
    expires_in_seconds: int,
    role: str = "customer",
) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in_seconds),
        "iss": TOKEN_ISSUER,
        "aud": TOKEN_AUDIENCE,
    }
    return jwt.encode(claims, _signing_secret(), algorithm="HS256")


def decode_access_token(token: str) -> Principal:
    claims = jwt.decode(
        token,
        _signing_secret(),
        algorithms=["HS256"],
        issuer=TOKEN_ISSUER,
        audience=TOKEN_AUDIENCE,
        options={"require": ["sub", "username", "iat", "exp", "iss", "aud"]},
    )
    try:
        user_id = UUID(claims["sub"])
        username = claims["username"]
        role = claims.get("role", "customer")
        if not isinstance(username, str) or not username:
            raise ValueError("Invalid username claim.")
        if role not in {"customer", "operator"}:
            raise ValueError("Invalid role claim.")
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidTokenError("Access token claims are invalid.") from exc
    return Principal(user_id=user_id, username=username, role=role)


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid access token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        decoded = decode_access_token(credentials.credentials)
        return Principal(decoded.user_id, decoded.username, credentials.credentials, decoded.role)
    except TokenConfigurationError as exc:
        raise HTTPException(status_code=503, detail="Authentication is not configured.") from exc
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The access token is invalid or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def require_operator(principal: Principal = Depends(get_current_principal)) -> Principal:
    if principal.role != "operator":
        raise HTTPException(status_code=403, detail="Operator access is required.")
    return principal
