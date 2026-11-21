import uuid
from datetime import datetime

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


class RoleRef(BaseModel):
    """A role as shown inside a user. Full role details come with the role endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    is_active: bool
    roles: list[RoleRef]
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
    # What this user may do, so the UI can hide buttons and menu entries. This is a
    # convenience only: the backend checks every request again, whatever the UI shows.
    permissions: list[str]


class RegisterResponse(BaseModel):
    organization: OrganizationOut
    user: UserOut


class PermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    description: str


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    is_system: bool
    permissions: list[PermissionOut]


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=255)
    # Permission keys from the catalogue, e.g. ["users.view"]. Validated in the endpoint.
    permission_keys: list[str] = Field(default_factory=list, max_length=100)


class RoleUpdate(BaseModel):
    """PATCH body: send only what you want to change. A missing field stays as it is."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    # If present, REPLACES the role's whole permission set.
    permission_keys: list[str] | None = Field(default=None, max_length=100)


class UserCreate(BaseModel):
    """An admin creates a user directly and sets the first password (no email invites yet)."""

    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=12, max_length=128)
    role_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)


class UserUpdate(BaseModel):
    """PATCH body: only the fields sent are changed."""

    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    is_active: bool | None = None
    # If present, REPLACES the user's whole set of roles.
    role_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)


class AuditLogOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    action: str
    actor_user_id: uuid.UUID | None
    actor_email: str | None  # looked up for convenience; None if the actor no longer exists
    target_type: str | None
    target_id: uuid.UUID | None
    details: dict
