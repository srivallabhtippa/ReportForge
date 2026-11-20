from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.models import AuditLog, User
from app.schemas import AuditLogOut

router = APIRouter(prefix="/api/audit-log", tags=["audit"])


@router.get("", response_model=list[AuditLogOut])
def list_audit_log(
    action: str | None = Query(default=None, max_length=100, description="Only this action"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("audit.view")),
):
    """Newest first. Read-only: there is deliberately no endpoint that changes the log."""
    query = (
        select(AuditLog, User.email)
        .outerjoin(User, User.id == AuditLog.actor_user_id)
        # The organization filter is the tenant boundary: never trust one from the client.
        .where(AuditLog.organization_id == user.organization_id)
        # id as a tiebreaker keeps the order stable when timestamps are equal.
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if action is not None:
        query = query.where(AuditLog.action == action)

    return [
        AuditLogOut(
            id=row.id,
            created_at=row.created_at,
            action=row.action,
            actor_user_id=row.actor_user_id,
            actor_email=email,
            target_type=row.target_type,
            target_id=row.target_id,
            details=row.details,
        )
        for row, email in db.execute(query)
    ]
