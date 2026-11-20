"""Writing to the audit log.

`record` only ADDS the row to the current session. It does not commit. The caller's
single commit then saves the change and its audit row together, or neither: a change
can never exist without its record, and a record never describes a change that was
rolled back (ADR 0005, decision 10).

Never put secrets in `details`: no passwords, hashes or tokens.
"""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def record(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    action: str,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            organization_id=organization_id,
            actor_user_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details or {},
        )
    )
