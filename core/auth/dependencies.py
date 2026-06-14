from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.auth.jwt_token_verifier import JwtTokenVerifier
from core.auth.schemas import AuthenticatedUser
from core.auth.token_verifier import (
    TokenAuthorizationError,
    TokenVerificationError,
    TokenVerifier,
    TokenVerifierConfigurationError,
)
from core.config import settings


bearer_scheme = HTTPBearer(
    auto_error=False,
    bearerFormat="JWT",
    scheme_name="BearerAuth",
    description=(
        "Paste a JWT bearer token. Swagger UI sends it as "
        "`Authorization: Bearer <token>`."
    ),
)


def get_token_verifier() -> TokenVerifier:
    if settings.AUTH_TOKEN_VERIFIER != "jwt":
        raise TokenVerifierConfigurationError(
            f"Unsupported AUTH_TOKEN_VERIFIER: {settings.AUTH_TOKEN_VERIFIER}."
        )
    return JwtTokenVerifier()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization token required.",
        )

    try:
        return get_token_verifier().verify(credentials.credentials)
    except TokenAuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token is not authorized for this application.",
        ) from exc
    except TokenVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization token.",
        ) from exc
    except TokenVerifierConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token verifier is not configured.",
        ) from exc
