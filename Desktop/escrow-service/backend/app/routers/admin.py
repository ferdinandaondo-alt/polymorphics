from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import services
from app.database import get_db
from app.deps import get_current_user
from app.enums import TransactionStatus
from app.schemas import (AdminTransactionOut, AdminUserOut, FreezeIn, KYCIn, RoleIn, StatsOut)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats", response_model=StatsOut)
def stats(db: Session = Depends(get_db), admin=Depends(get_current_user)):
    return services.admin_stats(db, admin)


@router.get("/users", response_model=list[AdminUserOut])
def users(search: str | None = None, db: Session = Depends(get_db), admin=Depends(get_current_user)):
    return services.admin_list_users(db, admin, search)


@router.post("/users/{user_id}/kyc", response_model=AdminUserOut)
def set_kyc(user_id: str, data: KYCIn, db: Session = Depends(get_db), admin=Depends(get_current_user)):
    return services.admin_set_kyc(db, admin, user_id, data.status, data.reason)


@router.post("/users/{user_id}/freeze", response_model=AdminUserOut)
def freeze(user_id: str, data: FreezeIn, db: Session = Depends(get_db), admin=Depends(get_current_user)):
    return services.admin_set_frozen(db, admin, user_id, data.frozen, data.reason)


@router.post("/users/{user_id}/role", response_model=AdminUserOut)
def role(user_id: str, data: RoleIn, db: Session = Depends(get_db), admin=Depends(get_current_user)):
    return services.admin_set_role(db, admin, user_id, data.role, data.reason)


@router.get("/transactions", response_model=list[AdminTransactionOut])
def transactions(status: TransactionStatus | None = None, db: Session = Depends(get_db), admin=Depends(get_current_user)):
    return [AdminTransactionOut.from_model(t) for t in services.admin_list_transactions(db, admin, status)]
