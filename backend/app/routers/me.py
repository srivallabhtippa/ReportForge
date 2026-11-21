from fastapi import APIRouter, Depends

from app.dependencies import get_current_permissions, get_current_user
from app.models import User
from app.schemas import MeResponse

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me", response_model=MeResponse)
def me(
    current_user: User = Depends(get_current_user),
    permissions: frozenset[str] = Depends(get_current_permissions),
):
    # All the protection is in the dependency. If the token is missing or invalid,
    # FastAPI answers 401 and this function body never runs.
    return MeResponse(
        organization=current_user.organization,
        user=current_user,
        permissions=sorted(permissions),
    )
