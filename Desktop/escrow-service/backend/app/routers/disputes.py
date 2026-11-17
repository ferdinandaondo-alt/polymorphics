from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import services
from app.database import get_db
from app.deps import get_current_user
from app.enums import DisputeStatus
from app.schemas import DecisionIn, DisputeOut, EvidenceIn, MessageIn

router = APIRouter(prefix="/disputes", tags=["disputes"])


@router.get("", response_model=list[DisputeOut])
def queue(status: DisputeStatus | None = None, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return services.list_disputes(db, user, status)


@router.get("/{dispute_id}", response_model=DisputeOut)
def get_one(dispute_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return services.get_dispute(db, user, dispute_id)


@router.post("/{dispute_id}/evidence", response_model=DisputeOut)
def evidence(dispute_id: str, data: EvidenceIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return services.add_evidence(db, user, dispute_id, data)


@router.post("/{dispute_id}/messages", response_model=DisputeOut)
def message(dispute_id: str, data: MessageIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return services.add_message(db, user, dispute_id, data)


@router.post("/{dispute_id}/decision", response_model=DisputeOut)
def decide(dispute_id: str, data: DecisionIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return services.decide_dispute(db, user, dispute_id, data)
