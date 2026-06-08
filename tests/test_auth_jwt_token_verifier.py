from datetime import datetime, timedelta, timezone

import jwt
import pytest

from core.auth.jwt_token_verifier import JwtTokenVerifier
from core.auth.token_verifier import TokenAuthorizationError, TokenVerificationError
from core.config import Settings


SECRET = "test-secret"
APPLICATION_ID = "00000000-0000-0000-0000-000000000002"


def _token(
    *,
    secret: str = SECRET,
    algorithm: str = "HS256",
    application_id: str = APPLICATION_ID,
    expires_delta: timedelta = timedelta(minutes=5),
    omit_claim: str | None = None,
) -> str:
    payload = {
        "sub": "user-id",
        "email": "user@example.com",
        "profile_id": "profile-id",
        "application_id": application_id,
        "exp": datetime.now(timezone.utc) + expires_delta,
    }
    if omit_claim is not None:
        payload.pop(omit_claim)
    return jwt.encode(payload, secret, algorithm=algorithm)


def test_verify_returns_authenticated_user_for_valid_token() -> None:
    verifier = JwtTokenVerifier(
        secret=SECRET,
        algorithm="HS256",
        expected_application_id=APPLICATION_ID,
    )

    user = verifier.verify(_token())

    assert user.id == "user-id"
    assert user.email == "user@example.com"
    assert user.profile_id == "profile-id"
    assert user.application_id == APPLICATION_ID


def test_verify_rejects_invalid_signature() -> None:
    verifier = JwtTokenVerifier(
        secret="other-secret",
        algorithm="HS256",
        expected_application_id=APPLICATION_ID,
    )

    with pytest.raises(TokenVerificationError):
        verifier.verify(_token())


def test_verify_rejects_expired_token() -> None:
    verifier = JwtTokenVerifier(
        secret=SECRET,
        algorithm="HS256",
        expected_application_id=APPLICATION_ID,
    )

    with pytest.raises(TokenVerificationError):
        verifier.verify(_token(expires_delta=timedelta(minutes=-1)))


def test_verify_rejects_unsupported_algorithm() -> None:
    verifier = JwtTokenVerifier(
        secret=SECRET,
        algorithm="HS256",
        expected_application_id=APPLICATION_ID,
    )

    with pytest.raises(TokenVerificationError):
        verifier.verify(_token(algorithm="HS512"))


def test_verify_rejects_missing_required_claim() -> None:
    verifier = JwtTokenVerifier(
        secret=SECRET,
        algorithm="HS256",
        expected_application_id=APPLICATION_ID,
    )

    with pytest.raises(TokenVerificationError):
        verifier.verify(_token(omit_claim="profile_id"))


def test_verify_rejects_wrong_application_id_as_authorization_failure() -> None:
    verifier = JwtTokenVerifier(
        secret=SECRET,
        algorithm="HS256",
        expected_application_id=APPLICATION_ID,
    )

    with pytest.raises(TokenAuthorizationError):
        verifier.verify(_token(application_id="00000000-0000-0000-0000-000000000003"))


def test_auth_config_defaults(monkeypatch) -> None:
    monkeypatch.delenv("AUTH_TOKEN_VERIFIER", raising=False)
    monkeypatch.delenv("AUTH_JWT_ALGORITHM", raising=False)
    monkeypatch.delenv("AUTH_EXPECTED_APPLICATION_ID", raising=False)

    settings = Settings()

    assert settings.AUTH_TOKEN_VERIFIER == "jwt"
    assert settings.AUTH_JWT_ALGORITHM == "HS256"
    assert settings.AUTH_EXPECTED_APPLICATION_ID == APPLICATION_ID
