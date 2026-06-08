from core.auth.schemas import AuthenticatedUser


class AuthService:
    def get_me(self, user: AuthenticatedUser) -> AuthenticatedUser:
        return user
