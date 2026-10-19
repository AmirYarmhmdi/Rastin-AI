"""Authentication primitives for Rastin-AI API requests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import jwt
from fastapi import status
from jwt import PyJWKClient

from rastin_ai.core.config import Settings
from rastin_ai.core.exceptions import AppException


class AuthenticationError(AppException):
    """Raised when a request cannot be authenticated."""

    def __init__(self, message: str = "Authentication required.") -> None:
        super().__init__(
            message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="AUTHENTICATION_REQUIRED",
        )


@dataclass(frozen=True)
class ExternalIdentity:
    """Identity resolved from a trusted local or OIDC token source."""

    issuer: str
    subject: str
    email: str | None = None
    display_name: str | None = None


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """Application principal after external identity has been mapped to a user."""

    user_id: UUID
    issuer: str
    subject: str
    email: str | None = None
    display_name: str | None = None


def validate_bearer_token(
    *,
    token: str | None,
    settings: Settings,
) -> ExternalIdentity:
    """Validate configured auth mode and return a normalized external identity."""
    if settings.AUTH_MODE == "disabled":
        return ExternalIdentity(
            issuer=settings.AUTH_DISABLED_LOCAL_USER_ISSUER,
            subject=settings.AUTH_DISABLED_LOCAL_USER_SUBJECT,
            email=settings.AUTH_DISABLED_LOCAL_USER_EMAIL,
            display_name=settings.AUTH_DISABLED_LOCAL_USER_DISPLAY_NAME,
        )

    if not token:
        raise AuthenticationError()

    if _token_uses_none_algorithm(token):
        raise AuthenticationError("Invalid authentication token.")

    if settings.AUTH_MODE == "dev_jwt":
        payload = _decode_dev_jwt(token, settings)
    elif settings.AUTH_MODE == "oidc":
        payload = _decode_oidc_jwt(token, settings)
    else:
        raise AuthenticationError("Authentication is not configured correctly.")

    return _identity_from_claims(payload)


def _decode_dev_jwt(token: str, settings: Settings) -> dict[str, Any]:
    try:
        return dict(
            jwt.decode(
                token,
                _required(settings.AUTH_DEV_JWT_SECRET),
                algorithms=[settings.AUTH_DEV_JWT_ALGORITHM],
                audience=_required(settings.AUTH_DEV_JWT_AUDIENCE),
                issuer=_required(settings.AUTH_DEV_JWT_ISSUER),
                options={"require": ["exp", "sub"]},
            )
        )
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid authentication token.") from exc


def _decode_oidc_jwt(token: str, settings: Settings) -> dict[str, Any]:
    algorithms = _csv_values(settings.AUTH_OIDC_ALGORITHMS)
    if not algorithms or "none" in {algorithm.lower() for algorithm in algorithms}:
        raise AuthenticationError("OIDC algorithms are not configured correctly.")

    try:
        signing_key = _oidc_signing_key(token, settings)
        return dict(
            jwt.decode(
                token,
                signing_key,
                algorithms=algorithms,
                audience=_required(settings.AUTH_OIDC_AUDIENCE),
                issuer=_required(settings.AUTH_OIDC_ISSUER),
                options={"require": ["exp", "sub"]},
            )
        )
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid authentication token.") from exc


def _oidc_signing_key(token: str, settings: Settings) -> Any:
    if settings.AUTH_OIDC_JWKS_JSON:
        return _signing_key_from_jwks_json(token, settings.AUTH_OIDC_JWKS_JSON)
    jwks_url = _required(settings.AUTH_OIDC_JWKS_URL)
    return PyJWKClient(jwks_url).get_signing_key_from_jwt(token).key


def _signing_key_from_jwks_json(token: str, jwks_json: str) -> Any:
    try:
        key_set = json.loads(jwks_json)
        key_id = jwt.get_unverified_header(token).get("kid")
        for key in key_set.get("keys", []):
            if key.get("kid") == key_id or key_id is None:
                return jwt.PyJWK(key).key
    except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
        raise AuthenticationError("Invalid OIDC JWKS configuration.") from exc

    raise AuthenticationError("Invalid authentication token.")


def _identity_from_claims(payload: dict[str, Any]) -> ExternalIdentity:
    issuer = _claim_text(payload, "iss")
    subject = _claim_text(payload, "sub")
    if issuer is None or subject is None:
        raise AuthenticationError("Invalid authentication token.")

    return ExternalIdentity(
        issuer=issuer,
        subject=subject,
        email=_claim_text(payload, "email"),
        display_name=_claim_text(payload, "name")
        or _claim_text(payload, "preferred_username"),
    )


def _token_uses_none_algorithm(token: str) -> bool:
    try:
        algorithm = jwt.get_unverified_header(token).get("alg")
    except jwt.PyJWTError:
        return True
    return not algorithm or str(algorithm).lower() == "none"


def _claim_text(payload: dict[str, Any], name: str) -> str | None:
    value = payload.get(name)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _required(value: str | None) -> str:
    if value is None or not value.strip():
        raise AuthenticationError("Authentication is not configured correctly.")
    return value.strip()


def _csv_values(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]
