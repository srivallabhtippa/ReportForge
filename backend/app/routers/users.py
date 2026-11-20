import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import audit
from app.authz import forbid_granting_what_you_lack, forbid_managing_above_you, keys_of
from app.database import get_db
from app.dependencies import get_current_permissions, require_permission
from app.models import Role, User, user_roles
from app.permissions import ADMIN_ROLE_NAME
from app.schemas import UserCreate, UserOut, UserUpdate
from app.security import hash_password

router = APIRouter(prefix="/api/users", tags=["users"])


def _get_user_or_404(db: Session, organization_id: uuid.UUID, user_id: uuid.UUID) -> User:
    # Same rule as roles: filter by organization in the query, answer 404 for foreign ids.
    found = db.scalar(
        select(User).where(User.id == user_id, User.organization_id == organization_id)
    )
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    return found


def _load_roles(db: Session, organization_id: uuid.UUID, role_ids: list[uuid.UUID]) -> list[Role]:
    wanted = set(role_ids)
    found = list(
        db.scalars(select(Role).where(Role.id.in_(wanted), Role.organization_id == organization_id))
    )
    # A role id from another organization and one that does not exist look identical.
    if len(found) != len(wanted):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown role id")
    return found


def _lock_admin_role(db: Session, organization_id: uuid.UUID) -> Role | None:
    # SELECT ... FOR UPDATE: a second request that wants this row waits until we commit.
    # Without the lock, two admins could demote each other at the same instant, both see
    # "the other one is still an admin", and leave the organization with no admin.
    return db.execute(
        select(Role)
        .where(
            Role.organization_id == organization_id,
            Role.is_system.is_(True),
            Role.name == ADMIN_ROLE_NAME,
        )
        .with_for_update()
    ).scalar_one_or_none()  # None only if the role was never created: nothing to protect


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("users.view")),
):
    return db.scalars(
        select(User)
        .where(User.organization_id == user.organization_id)
        .options(selectinload(User.roles))  # one extra query, not one per user
        .order_by(User.email)
    ).all()


@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("users.view")),
):
    return _get_user_or_404(db, user.organization_id, user_id)


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("users.manage")),
    caller_permissions: frozenset[str] = Depends(get_current_permissions),
):
    roles = _load_roles(db, user.organization_id, payload.role_ids)
    forbid_granting_what_you_lack(keys_of(roles), caller_permissions)

    new_user = User(
        id=uuid.uuid4(),  # generated here so the audit row can name it before saving
        organization_id=user.organization_id,  # always the caller's: never taken from the request
        email=payload.email.lower(),
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        roles=roles,
    )
    db.add(new_user)
    audit.record(
        db,
        organization_id=user.organization_id,
        actor_id=user.id,
        action="user.created",
        target_type="user",
        target_id=new_user.id,
        # Never the password or its hash.
        details={"email": new_user.email, "roles": sorted(r.name for r in roles)},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="An account with this email already exists"
        )
    return new_user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    caller: User = Depends(require_permission("users.manage")),
    caller_permissions: frozenset[str] = Depends(get_current_permissions),
):
    target = _get_user_or_404(db, caller.organization_id, user_id)

    # Take the Admin-role lock BEFORE reading the facts the guards depend on, and only
    # when the change could remove an active admin (a name edit cannot). If another
    # request holds the lock we wait here; afterwards expire() makes SQLAlchemy reload
    # the target, so we never decide from state that was read before the wait.
    admin_role = None
    if payload.is_active is not None or payload.role_ids is not None:
        admin_role = _lock_admin_role(db, caller.organization_id)
        db.expire(target)

    # Nobody may manage a user who holds permissions they lack. Otherwise someone with
    # only users.manage could disable or re-role an admin.
    forbid_managing_above_you(keys_of(target.roles), caller_permissions, "user")

    new_active = target.is_active if payload.is_active is None else payload.is_active
    new_roles = target.roles
    if payload.role_ids is not None:
        new_roles = _load_roles(db, caller.organization_id, payload.role_ids)
        current_ids = {r.id for r in target.roles}
        forbid_granting_what_you_lack(
            keys_of([r for r in new_roles if r.id not in current_ids]), caller_permissions
        )

    # Last-admin guard (ADR 0005, decision 9): after this change the organization must
    # still have at least one active admin.
    admin_id = admin_role.id if admin_role else None
    is_active_admin_now = target.is_active and any(r.id == admin_id for r in target.roles)
    will_be_active_admin = new_active and any(r.id == admin_id for r in new_roles)
    if is_active_admin_now and not will_be_active_admin:
        other_admins = db.scalar(
            select(func.count())
            .select_from(User)
            .join(user_roles, user_roles.c.user_id == User.id)
            .where(
                user_roles.c.role_id == admin_id,
                User.is_active.is_(True),
                User.id != target.id,
            )
        )
        if other_admins == 0:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="The organization must keep at least one active admin",
            )

    def log(action: str, details: dict) -> None:
        audit.record(
            db,
            organization_id=caller.organization_id,
            actor_id=caller.id,
            action=action,
            target_type="user",
            target_id=target.id,
            details={"email": target.email, **details},
        )

    # One event per kind of change, so the log can be filtered ("show me every disable").
    if payload.full_name is not None and payload.full_name.strip() != target.full_name:
        log("user.updated", {"full_name": {"from": target.full_name, "to": payload.full_name.strip()}})
        target.full_name = payload.full_name.strip()
    if new_active != target.is_active:
        log("user.enabled" if new_active else "user.disabled", {})
        target.is_active = new_active
    old_names = {r.name for r in target.roles}
    new_names = {r.name for r in new_roles}
    if old_names != new_names:
        log(
            "user.roles_changed",
            {"added": sorted(new_names - old_names), "removed": sorted(old_names - new_names)},
        )
        target.roles = new_roles
    db.commit()
    return target
