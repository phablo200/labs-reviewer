from uuid import UUID

from fastapi import HTTPException, status

from core.auth.schemas import AuthenticatedUser


def parse_user_id(user: AuthenticatedUser) -> UUID:
    try:
        return UUID(user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authenticated user id is invalid.",
        ) from exc


class AuthService:
    def get_me(self, user: AuthenticatedUser) -> AuthenticatedUser:
        return user
