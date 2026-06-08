from typing import Any

import jwt
from jwt import PyJWTError

from core.auth.schemas import AuthenticatedUser
from core.auth.token_verifier import (
    TokenAuthorizationError,
    TokenVerificationError,
    TokenVerifierConfigurationError,
)
from core.config import settings


class JwtTokenVerifier:
    """Verify Auth Backend JWTs and map claims to the app user schema."""

    REQUIRED_CLAIMS = ("sub", "email", "profile_id", "application_id", "exp")

    def __init__(
        self,
        secret: str | None = None,
        algorithm: str | None = None,
        expected_application_id: str | None = None,
    ) -> None:
        self.secret = settings.AUTH_JWT_SECRET if secret is None else secret
        self.algorithm = algorithm or settings.AUTH_JWT_ALGORITHM
        self.expected_application_id = (
            settings.AUTH_EXPECTED_APPLICATION_ID
            if expected_application_id is None
            else expected_application_id
        )

    def verify(self, token: str) -> AuthenticatedUser:
        if not self.secret:
            raise TokenVerifierConfigurationError("AUTH_JWT_SECRET is required.")

        try:
            payload = jwt.decode(
                token,
                self.secret,
                algorithms=[self.algorithm],
                options={"require": list(self.REQUIRED_CLAIMS)},
            )
        except PyJWTError as exc:
            raise TokenVerificationError("Invalid bearer token.") from exc

        return self._build_authenticated_user(payload)

    def _build_authenticated_user(self, payload: dict[str, Any]) -> AuthenticatedUser:
        application_id = self._required_string_claim(payload, "application_id")
        if application_id != self.expected_application_id:
            raise TokenAuthorizationError("Token application_id is not allowed.")

        return AuthenticatedUser(
            id=self._required_string_claim(payload, "sub"),
            email=self._required_string_claim(payload, "email"),
            profile_id=self._required_string_claim(payload, "profile_id"),
            application_id=application_id,
        )

    @staticmethod
    def _required_string_claim(payload: dict[str, Any], claim: str) -> str:
        value = payload.get(claim)
        if not isinstance(value, str) or not value:
            raise TokenVerificationError(f"Missing or invalid token claim: {claim}.")
        return value
