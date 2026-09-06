from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.core.permissions import Permission
from app.models import User
from app.services import audit_service, settings_service

router = APIRouter(prefix="/settings", tags=["admin: settings"])


class SettingOut(BaseModel):
    key: str
    value: Any
    value_type: str
    default: Any
    description: str
    updated_at: Optional[Any] = None


class SettingUpdate(BaseModel):
    value: Any


@router.get("", response_model=list[SettingOut])
def list_settings(db: Session = Depends(get_db), _: User = Depends(require_permission(Permission.settings_manage))):
    return settings_service.all_settings(db)


@router.put("/{key}", response_model=SettingOut)
def update_setting(
    key: str, payload: SettingUpdate, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.settings_manage))
):
    before = settings_service.get_setting(db, key) if key in settings_service.SETTING_DEFINITIONS else None
    result = settings_service.set_setting(db, key, payload.value, actor)
    audit_service.record(
        db, "setting_updated", actor=actor, entity_type="setting", reason=key, before={"value": before}, after={"value": result["value"]}
    )
    db.commit()
    return next(s for s in settings_service.all_settings(db) if s["key"] == key)
