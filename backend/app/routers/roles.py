import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import audit
from app.authz import forbid_granting_what_you_lack, forbid_managing_above_you
from app.database import get_db
from app.dependencies import get_current_permissions, require_permission
from app.models import Permission, Role, User
from app.schemas import PermissionOut, RoleCreate, RoleOut, RoleUpdate

router = APIRouter(prefix="/api", tags=["roles"])


def _get_role_or_404(db: Session, organization_id: uuid.UUID, role_id: uuid.UUID) -> Role:
    # Filtering by organization_id in the same query is what enforces tenant isolation.
    # A role of another organization simply is not found: 404, not 403, so ids cannot be
    # used to learn which roles exist elsewhere (ADR 0005, decision 8).
    role = db.scalar(
        select(Role).where(Role.id == role_id, Role.organization_id == organization_id)
    )
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Role not found")
    return role


def _load_permissions(db: Session, keys: list[str]) -> list[Permission]:
    wanted = set(keys)  # a set drops duplicates sent by the client
    found = list(db.scalars(select(Permission).where(Permission.key.in_(wanted))))
    unknown = wanted - {p.key for p in found}
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown permissions: {', '.join(sorted(unknown))}",
        )
    return found


def _forbid_system_role(role: Role) -> None:
    if role.is_system:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="System roles cannot be changed")


def _commit_or_409(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # uq_roles_org_name is the real guard; checking first would be racy.
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="A role with this name already exists"
        )


@router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("roles.view")),
):
    """The catalogue, so the UI can show which permissions a role can be given."""
    return db.scalars(select(Permission).order_by(Permission.key)).all()


@router.get("/roles", response_model=list[RoleOut])
def list_roles(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("roles.view")),
):
    return db.scalars(
        select(Role)
        .where(Role.organization_id == user.organization_id)
        .options(selectinload(Role.permissions))  # one extra query, not one per role
        .order_by(Role.name)
    ).all()


@router.get("/roles/{role_id}", response_model=RoleOut)
def get_role(
    role_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("roles.view")),
):
    return _get_role_or_404(db, user.organization_id, role_id)


@router.post("/roles", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
def create_role(
    payload: RoleCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("roles.manage")),
    caller_permissions: frozenset[str] = Depends(get_current_permissions),
):
    permissions = _load_permissions(db, payload.permission_keys)
    forbid_granting_what_you_lack({p.key for p in permissions}, caller_permissions)

    role = Role(
        id=uuid.uuid4(),  # generated here so the audit row can name it before saving
        organization_id=user.organization_id,
        name=payload.name.strip(),
        description=payload.description.strip(),
        permissions=permissions,
    )
    db.add(role)
    audit.record(
        db,
        organization_id=user.organization_id,
        actor_id=user.id,
        action="role.created",
        target_type="role",
        target_id=role.id,
        details={"name": role.name, "permissions": sorted(p.key for p in permissions)},
    )
    _commit_or_409(db)
    return role


@router.patch("/roles/{role_id}", response_model=RoleOut)
def update_role(
    role_id: uuid.UUID,
    payload: RoleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("roles.manage")),
    caller_permissions: frozenset[str] = Depends(get_current_permissions),
):
    role = _get_role_or_404(db, user.organization_id, role_id)
    _forbid_system_role(role)
    forbid_managing_above_you({p.key for p in role.permissions}, caller_permissions, "role")

    changes: dict = {}
    if payload.name is not None and payload.name.strip() != role.name:
        changes["name"] = {"from": role.name, "to": payload.name.strip()}
        role.name = payload.name.strip()
    if payload.description is not None and payload.description.strip() != role.description:
        changes["description"] = {"from": role.description, "to": payload.description.strip()}
        role.description = payload.description.strip()
    if payload.permission_keys is not None:
        permissions = _load_permissions(db, payload.permission_keys)
        # Only permissions being ADDED must be ones the caller holds; the role as a whole
        # was already checked above.
        added = {p.key for p in permissions} - {p.key for p in role.permissions}
        forbid_granting_what_you_lack(added, caller_permissions)
        removed = {p.key for p in role.permissions} - {p.key for p in permissions}
        if added or removed:
            changes["permissions"] = {"added": sorted(added), "removed": sorted(removed)}
        role.permissions = permissions

    if changes:  # an update that changed nothing is not an event
        audit.record(
            db,
            organization_id=user.organization_id,
            actor_id=user.id,
            action="role.updated",
            target_type="role",
            target_id=role.id,
            details=changes,
        )
    _commit_or_409(db)
    return role


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(
    role_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("roles.manage")),
    caller_permissions: frozenset[str] = Depends(get_current_permissions),
):
    role = _get_role_or_404(db, user.organization_id, role_id)
    _forbid_system_role(role)
    forbid_managing_above_you({p.key for p in role.permissions}, caller_permissions, "role")
    # ON DELETE CASCADE removes the role's user_roles and role_permissions rows, so users
    # who held it simply lose it. Each of them gets an audit event of their own, so the
    # log can answer "why did this person lose access?".
    for member in role.users:
        audit.record(
            db,
            organization_id=user.organization_id,
            actor_id=user.id,
            action="user.roles_changed",
            target_type="user",
            target_id=member.id,
            details={"email": member.email, "added": [], "removed": [role.name]},
        )
    audit.record(
        db,
        organization_id=user.organization_id,
        actor_id=user.id,
        action="role.deleted",
        target_type="role",
        target_id=role.id,
        details={"name": role.name},  # the role is gone afterwards, so keep its name here
    )
    db.delete(role)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
