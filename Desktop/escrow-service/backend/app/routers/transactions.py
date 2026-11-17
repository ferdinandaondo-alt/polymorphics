from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import services
from app.database import get_db
from app.deps import get_current_user
from app.enums import TransactionStatus
from app.schemas import (DeliverIn, DisputeOpen, DisputeOut, LedgerEntryOut,
                         TransactionCreate, TransactionOut)

router = APIRouter(prefix="/transactions", tags=["transactions"])
Out = TransactionOut.from_model


@router.post("", response_model=TransactionOut, status_code=201)
def create(data: TransactionCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return Out(services.create_transaction(db, user, data))


@router.get("", response_model=list[TransactionOut])
def list_mine(status: TransactionStatus | None = None, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return [Out(t) for t in services.list_transactions(db, user, status)]


@router.get("/{txn_id}", response_model=TransactionOut)
def get_one(txn_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return Out(services.get_transaction(db, user, txn_id))


@router.get("/{txn_id}/ledger", response_model=list[LedgerEntryOut])
def ledger_entries(txn_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return services.get_ledger(db, user, txn_id)


@router.post("/{txn_id}/accept", response_model=TransactionOut)
def accept(txn_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return Out(services.accept_transaction(db, user, txn_id))


@router.post("/{txn_id}/cancel", response_model=TransactionOut)
def cancel(txn_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return Out(services.cancel_transaction(db, user, txn_id))


@router.post("/{txn_id}/fund", response_model=TransactionOut)
def fund(txn_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return Out(services.fund_transaction(db, user, txn_id))


@router.post("/{txn_id}/deliver", response_model=TransactionOut)
def deliver(txn_id: str, data: DeliverIn | None = None, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return Out(services.deliver_transaction(db, user, txn_id, data or DeliverIn()))


@router.post("/{txn_id}/approve", response_model=TransactionOut)
def approve(txn_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return Out(services.approve_transaction(db, user, txn_id))


@router.post("/{txn_id}/dispute", response_model=DisputeOut, status_code=201)
def open_dispute(txn_id: str, data: DisputeOpen, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return services.open_dispute(db, user, txn_id, data.reason)
