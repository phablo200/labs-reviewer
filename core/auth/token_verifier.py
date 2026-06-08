from typing import Protocol

from core.auth.schemas import AuthenticatedUser


class TokenVerificationError(Exception):
    """Raised when a bearer token cannot be authenticated."""


class TokenAuthorizationError(Exception):
    """Raised when an authenticated token is not authorized for this service."""


class TokenVerifierConfigurationError(Exception):
    """Raised when token verification cannot run because configuration is invalid."""


class TokenVerifier(Protocol):
    def verify(self, token: str) -> AuthenticatedUser:
        """Validate a bearer token and return the authenticated user."""
