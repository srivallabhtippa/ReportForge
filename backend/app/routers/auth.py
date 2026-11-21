from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
import uuid

from sqlalchemy import select

from app import audit

from app.models import Organization, Permission, Role, User
from app.permissions import ADMIN_ROLE_NAME

from app.schemas import LoginRequest, RegisterRequest, RegisterResponse, TokenResponse
from app.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    # Emails are compared case-insensitively by always storing them in lowercase.
    email = payload.email.lower()

    # Ids are generated here (not by the database) so the audit row below can name them
    # before anything is saved, and everything still goes out in one commit.
    organization = Organization(id=uuid.uuid4(), name=payload.organization_name.strip())
    user = User(
        id=uuid.uuid4(),
        organization=organization,
        email=email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
    )
    # Every organization starts with a system "Admin" role holding every permission
    # in the catalogue, and its first user holds that role (ADR 0005, decision 5).
    admin_role = Role(
        organization=organization,
        name=ADMIN_ROLE_NAME,
        description="Full access to everything in the organization",
        is_system=True,
        permissions=list(db.scalars(select(Permission))),
    )
    user.roles.append(admin_role)
    audit.record(
        db,
        organization_id=organization.id,
        actor_id=user.id,
        action="organization.registered",
        target_type="organization",
        target_id=organization.id,
        details={"organization_name": organization.name, "admin_email": email},
    )
    # Adding the user also adds the organization (through the relationship).
    db.add(user)

    try:
        # One commit = one transaction: either both rows exist or neither does.
        db.commit()
    except IntegrityError:
        db.rollback()
        # The unique constraint on users.email is the real guard. Checking first and
        # inserting later would be racy if two requests arrived at the same moment.
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="An account with this email already exists"
        )

    return RegisterResponse(organization=organization, user=user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))

    # Always run one password check, even for an unknown email, so response time
    # does not reveal whether the account exists.
    password_ok = verify_password(
        payload.password, user.password_hash if user else DUMMY_PASSWORD_HASH
    )

    # One identical message for unknown email, wrong password and disabled account,
    # so an attacker cannot tell which emails are registered.
    if user is None or not password_ok or not user.is_active:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Only successful logins are recorded. Recording failures only for existing emails
    # would make those responses slower and reveal which emails are registered; failed
    # attempts are handled by rate limiting in v4.
    audit.record(
        db,
        organization_id=user.organization_id,
        actor_id=user.id,
        action="auth.login",
        target_type="user",
        target_id=user.id,
    )
    db.commit()

    token, expires_in = create_access_token(user.id, user.organization_id)
    return TokenResponse(access_token=token, expires_in=expires_in)
