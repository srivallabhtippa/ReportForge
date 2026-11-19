import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    """What the sign-up form sends. FastAPI validates it before our code runs."""

    organization_name: str = Field(min_length=2, max_length=200)
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    # Upper limit stops someone sending a megabyte-long password to waste hashing time.
    password: str = Field(min_length=12, max_length=128)


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # allow building from a DB object

    id: uuid.UUID
    name: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: str
    # Note what is missing: password_hash is never part of any response.


class LoginRequest(BaseModel):
    email: EmailStr
    # No length rules here: login only checks the password, it must not hint at them.
    password: str = Field(max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until the token stops working


class MeResponse(BaseModel):
    organization: OrganizationOut
    user: UserOut


class RegisterResponse(BaseModel):
    organization: OrganizationOut
    user: UserOut
