from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.core.errors import NotFoundError, ValidationError
from app.core.pagination import Page, PageParams, paginate_query
from app.core.permissions import Permission, Role
from app.core.security import hash_password, validate_password_strength
from app.models import Customer, User
from app.schemas.auth import UserCreate, UserPublic, UserUpdate
from app.services import audit_service, auth_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=Page[UserPublic])
def list_users(
    params: PageParams = Depends(),
    q: Optional[str] = Query(None, description="Search by name or email"),
    role: Optional[Role] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.user_manage)),
):
    query = db.query(User)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(User.full_name.ilike(like), User.email.ilike(like)))
    if role is not None:
        query = query.filter(User.role == role)
    if is_active is not None:
        query = query.filter(User.is_active.is_(is_active))
    rows, total = paginate_query(query.order_by(User.full_name), params)
    return Page.build([UserPublic.model_validate(u) for u in rows], total, params)


@router.get("/reps", response_model=list[UserPublic], summary="Active sales reps and managers (for assignment pickers)")
def list_reps(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.quote_read, Permission.customer_read)),
):
    rows = (
        db.query(User)
        .filter(User.is_active.is_(True), User.role.in_([Role.sales_rep, Role.sales_manager, Role.admin]))
        .order_by(User.full_name)
        .all()
    )
    return [UserPublic.model_validate(u) for u in rows]


@router.post("", response_model=UserPublic, status_code=201)
def create_user(
    payload: UserCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.user_manage))
):
    if payload.customer_id is not None and db.get(Customer, payload.customer_id) is None:
        raise NotFoundError("Customer not found")
    user = auth_service.create_user(
        db,
        email=payload.email,
        full_name=payload.full_name,
        password=payload.password,
        role=payload.role,
        team=payload.team,
        customer_id=payload.customer_id,
        is_active=payload.is_active,
        actor=actor,
    )
    db.commit()
    return UserPublic.model_validate(user)


@router.get("/{user_id}", response_model=UserPublic)
def get_user(user_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission(Permission.user_manage))):
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    return UserPublic.model_validate(user)


@router.patch("/{user_id}", response_model=UserPublic)
def update_user(
    user_id: int, payload: UserUpdate, db: Session = Depends(get_db), actor: User = Depends(require_permission(Permission.user_manage))
):
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    before = {"full_name": user.full_name, "role": user.role.value, "team": user.team, "is_active": user.is_active}
    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()
    if payload.role is not None:
        if user.id == actor.id and payload.role != actor.role:
            raise ValidationError("You cannot change your own role.")
        user.role = payload.role
    if payload.team is not None:
        user.team = payload.team or None
    if payload.customer_id is not None:
        if db.get(Customer, payload.customer_id) is None:
            raise NotFoundError("Customer not found")
        user.customer_id = payload.customer_id
    if user.role != Role.customer:
        user.customer_id = None
    if payload.is_active is not None:
        if user.id == actor.id and not payload.is_active:
            raise ValidationError("You cannot deactivate your own account.")
        user.is_active = payload.is_active
        if not payload.is_active:
            auth_service.revoke_all_sessions(db, user)
    if payload.password:
        validate_password_strength(payload.password)
        user.hashed_password = hash_password(payload.password)
        auth_service.revoke_all_sessions(db, user)
    after = {"full_name": user.full_name, "role": user.role.value, "team": user.team, "is_active": user.is_active}
    audit_service.record(db, "user_updated", actor=actor, entity_type="user", entity_id=user.id, before=before, after=after)
    db.commit()
    return UserPublic.model_validate(user)
