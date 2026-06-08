from fastapi import APIRouter, Depends

from core.auth.dependencies import get_current_user
from core.auth.schemas import AuthenticatedUser
from core.auth.service import AuthService


router = APIRouter(tags=["Auth"])
service = AuthService()


@router.get("/me")
async def me(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    return service.get_me(user)
