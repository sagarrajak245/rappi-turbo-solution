from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import UserRole


class LoginIn(BaseModel):
    email: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=200)


class UserOut(BaseModel):
    """The signed-in user as the API shows it: never the password hash."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: str
    role: UserRole
    branch: str
