from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.errors import NotFound
from app.core.security import AuthenticatedUser
from app.models import Profile
from app.schemas.tenancy import ProfileOut, ProfileUpdate

router = APIRouter(prefix="/me", tags=["Profil"])


@router.get("", response_model=ProfileOut)
def get_me(db: Session = Depends(get_db), user: AuthenticatedUser = Depends(get_current_user)):
    profile = db.get(Profile, user.id)
    if profile is None:
        raise NotFound("Profil introuvable : le compte n'est pas encore initialisé")
    return profile


@router.patch("", response_model=ProfileOut)
def update_me(payload: ProfileUpdate, db: Session = Depends(get_db),
              user: AuthenticatedUser = Depends(get_current_user)):
    profile = db.get(Profile, user.id)
    if profile is None:
        raise NotFound("Profil introuvable")
    # seules les colonnes autorisées par GRANT UPDATE (...) peuvent être modifiées
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    db.flush()
    db.refresh(profile)
    return profile
