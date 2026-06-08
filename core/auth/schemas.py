from pydantic import BaseModel


class AuthenticatedUser(BaseModel):
    id: str
    email: str
    profile_id: str
    application_id: str
