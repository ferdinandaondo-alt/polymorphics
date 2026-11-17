"""
Business logic for the escrow flow. Routers stay thin and call into here.

Rules of the road:
- Every money-moving function re-reads the transaction row WITH A LOCK
  (SELECT ... FOR UPDATE on Postgres) so two concurrent requests can't both
  release or refund the same funds.
- Every state change writes an AuditLog row and queues Notification rows, in the
  same database transaction as the change itself.
- Ledger rows are only ever appended (see ledger.py).
"""
import json
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, ledger, models
from app.enums import (AccountRole, DisputeDecision, DisputeStatus, KYCStatus, LedgerEntryType,
                       NotificationType, TransactionStatus as S)
from app.fees import compute_fee, fee_shares
from app.payments import get_provider
from app.schemas import DecisionIn, DeliverIn, EvidenceIn, MessageIn, TransactionCreate
from app.state_machine import transition


# ---------------------------------------------------------------- helpers
def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; treat them as UTC so comparisons work everywhere."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _audit(db, actor, action, entity_type, entity_id, reason=None, meta=None):
    db.add(models.AuditLog(
        actor_id=actor.id if actor else None, action=action, entity_type=entity_type,
        entity_id=entity_id, reason=reason, meta=json.dumps(meta) if meta else None,
    ))


def _notify(db, user_id, ntype: NotificationType, txn_id, payload=None):
    db.add(models.Notification(user_id=user_id, type=ntype, transaction_id=txn_id,
                               payload=json.dumps(payload) if payload else None))


def _get_txn(db: Session, txn_id: str, lock: bool = False) -> models.Transaction:
    q = select(models.Transaction).where(models.Transaction.id == txn_id)
    if lock:
        q = q.with_for_update()
    txn = db.execute(q).scalar_one_or_none()
    if not txn:
        raise HTTPException(404, "Transaction not found")
    return txn


def _is_party(txn, user) -> bool:
    return user.id in (txn.buyer_id, txn.seller_id)


def _require_buyer(txn, user):
    if user.id != txn.buyer_id:
        raise HTTPException(403, "Only the buyer can do this")


def _require_seller(txn, user):
    if user.id != txn.seller_id:
        raise HTTPException(403, "Only the seller can do this")


def _require_kyc(user, amount: int):
    if amount > config.KYC_THRESHOLD and user.kyc_status != KYCStatus.VERIFIED:
        raise HTTPException(403, "Identity verification (KYC) is required for transactions of this size")


def _can_view(db, txn, user) -> bool:
    if _is_party(txn, user) or user.role == AccountRole.ADMIN:
        return True
    if user.role == AccountRole.ARBITER:       # arbiters only see deals that are/were in dispute
        return db.execute(select(models.Dispute.id).where(models.Dispute.transaction_id == txn.id)).first() is not None
    return False


# ------------------------------------------------------------ reading
def get_transaction(db, user, txn_id) -> models.Transaction:
    txn = _get_txn(db, txn_id)
    if not _can_view(db, txn, user):
        raise HTTPException(404, "Transaction not found")   # 404, not 403: don't reveal it exists
    return txn


def list_transactions(db, user, status: S | None = None):
    q = select(models.Transaction).where(
        (models.Transaction.buyer_id == user.id) | (models.Transaction.seller_id == user.id))
    if status:
        q = q.where(models.Transaction.status == status)
    return db.execute(q.order_by(models.Transaction.created_at.desc())).scalars().all()


def get_ledger(db, user, txn_id):
    txn = get_transaction(db, user, txn_id)
    return db.execute(select(models.LedgerEntry).where(models.LedgerEntry.transaction_id == txn.id)
                      .order_by(models.LedgerEntry.created_at, models.LedgerEntry.direction.desc())).scalars().all()   # debit before credit


# ------------------------------------------------- pre-funding lifecycle
def create_transaction(db, user, data: TransactionCreate) -> models.Transaction:
    if user.role != AccountRole.USER:
        raise HTTPException(403, "Only regular user accounts can create transactions")
    counterparty = db.execute(select(models.User).where(models.User.email == data.counterparty_email.lower())).scalar_one_or_none()
    if not counterparty or not counterparty.is_active:
        raise HTTPException(404, "No active user with that email")
    if counterparty.id == user.id:
        raise HTTPException(400, "You can't open an escrow with yourself")
    if counterparty.role != AccountRole.USER:
        raise HTTPException(400, "The counterparty must be a regular user account")
    _require_kyc(user, data.amount)

    buyer, seller = (user, counterparty) if data.my_role == "buyer" else (counterparty, user)
    txn = models.Transaction(
        buyer_id=buyer.id, seller_id=seller.id, created_by_id=user.id,
        title=data.title, description=data.description, currency=data.currency,
        amount=data.amount, fee_amount=compute_fee(data.amount), fee_payer=data.fee_payer,
        delivery_deadline=data.delivery_deadline, auto_release_hours=data.auto_release_hours,
        status=S.DRAFT,
    )
    db.add(txn)
    db.flush()
    _audit(db, user, "transaction.create", "transaction", txn.id, meta={"amount": txn.amount, "currency": txn.currency})
    db.commit()
    return txn


def accept_transaction(db, user, txn_id) -> models.Transaction:
    txn = _get_txn(db, txn_id, lock=True)
    if not _is_party(txn, user) or user.id == txn.created_by_id:
        raise HTTPException(403, "Only the other party can accept this transaction")
    _require_kyc(user, txn.amount)
    transition(txn, S.ACCEPTED)
    txn.accepted_at = utcnow()
    _audit(db, user, "transaction.accept", "transaction", txn.id)
    db.commit()
    return txn


def cancel_transaction(db, user, txn_id) -> models.Transaction:
    txn = _get_txn(db, txn_id, lock=True)
    if not _is_party(txn, user):
        raise HTTPException(404, "Transaction not found")
    transition(txn, S.CANCELLED)          # only legal from DRAFT / ACCEPTED, i.e. before any money moved
    txn.cancelled_at = utcnow()
    _audit(db, user, "transaction.cancel", "transaction", txn.id)
    db.commit()
    return txn


# ----------------------------------------------- funding -> delivery -> release
def fund_transaction(db, user, txn_id) -> models.Transaction:
    txn = _get_txn(db, txn_id, lock=True)
    _require_buyer(txn, user)
    transition(txn, S.FUNDED)             # raises 409 if not ACCEPTED -> a duplicate call can't double-post
    buyer_share, _ = fee_shares(txn.fee_amount, txn.fee_payer)
    charge = txn.amount + buyer_share
    ref = get_provider().charge(user.id, charge, txn.currency, idempotency_key=f"fund:{txn.id}")
    ledger.transfer(db, txn, LedgerEntryType.FUNDING, ledger.buyer_external(txn.buyer_id), ledger.ESCROW, charge, ref)
    txn.funded_at = utcnow()
    _audit(db, user, "transaction.fund", "transaction", txn.id, meta={"charged": charge, "provider_ref": ref})
    _notify(db, txn.seller_id, NotificationType.TRANSACTION_FUNDED, txn.id)
    db.commit()
    return txn


def deliver_transaction(db, user, txn_id, data: DeliverIn) -> models.Transaction:
    txn = _get_txn(db, txn_id, lock=True)
    _require_seller(txn, user)
    transition(txn, S.DELIVERED)
    now = utcnow()
    txn.delivered_at = now
    txn.auto_release_at = now + timedelta(hours=txn.auto_release_hours)
    _audit(db, user, "transaction.deliver", "transaction", txn.id, meta={"note": data.note})
    _notify(db, txn.buyer_id, NotificationType.TRANSACTION_DELIVERED, txn.id)
    db.commit()
    return txn


def approve_transaction(db, user, txn_id) -> models.Transaction:
    txn = _get_txn(db, txn_id, lock=True)
    _require_buyer(txn, user)
    # The state machine also allows DISPUTED -> RELEASED (for arbiter rulings), so the buyer's own
    # approve action must insist on DELIVERED, or a buyer could bypass an open dispute.
    if txn.status != S.DELIVERED:
        raise HTTPException(409, f"Cannot approve a transaction that is '{txn.status.value}'")
    transition(txn, S.RELEASED)
    _post_release(db, txn)
    txn.released_at = utcnow()
    _audit(db, user, "transaction.release", "transaction", txn.id, reason="buyer approved delivery")
    _notify(db, txn.seller_id, NotificationType.TRANSACTION_RELEASED, txn.id)
    db.commit()
    return txn


def release_due_transactions(db, now: datetime | None = None) -> list[str]:
    """Auto-release delivered deals whose window passed with no approval or dispute.
    Run this on a schedule (cron / Celery beat). Returns the ids it released."""
    now = now or utcnow()
    candidates = db.execute(select(models.Transaction.id).where(
        models.Transaction.status == S.DELIVERED, models.Transaction.auto_release_at.is_not(None))).scalars().all()
    released = []
    for txn_id in candidates:
        txn = _get_txn(db, txn_id, lock=True)
        if txn.status != S.DELIVERED or as_utc(txn.auto_release_at) > now:   # re-check under lock
            db.rollback()
            continue
        transition(txn, S.RELEASED)
        _post_release(db, txn)
        txn.released_at = now
        _audit(db, None, "transaction.auto_release", "transaction", txn.id, reason="buyer did not respond in time")
        _notify(db, txn.seller_id, NotificationType.TRANSACTION_RELEASED, txn.id)
        _notify(db, txn.buyer_id, NotificationType.TRANSACTION_RELEASED, txn.id)
        db.commit()
        released.append(txn.id)
    return released


# ------------------------------------------------------- ledger postings
def _amounts(txn):
    buyer_share, seller_share = fee_shares(txn.fee_amount, txn.fee_payer)
    return buyer_share, seller_share


def _post_fee(db, txn):
    if txn.fee_amount > 0:
        ledger.transfer(db, txn, LedgerEntryType.FEE, ledger.ESCROW, ledger.PLATFORM_REVENUE, txn.fee_amount)


def _post_release(db, txn):
    """Escrow -> seller (amount minus their fee share) and platform (full fee)."""
    _, seller_share = _amounts(txn)
    ledger.transfer(db, txn, LedgerEntryType.RELEASE, ledger.ESCROW,
                    ledger.seller_payable(txn.seller_id), txn.amount - seller_share)
    _post_fee(db, txn)


def _post_refund(db, txn):
    """Everything the buyer paid goes back to them (platform keeps no fee on a full refund)."""
    buyer_share, _ = _amounts(txn)
    ledger.transfer(db, txn, LedgerEntryType.REFUND, ledger.ESCROW,
                    ledger.buyer_external(txn.buyer_id), txn.amount + buyer_share)


def _post_split(db, txn, seller_amount: int):
    """Seller keeps `seller_amount` of the item price (less their fee share); buyer gets the rest back."""
    _, seller_share = _amounts(txn)
    ledger.transfer(db, txn, LedgerEntryType.RELEASE, ledger.ESCROW,
                    ledger.seller_payable(txn.seller_id), seller_amount - seller_share)
    ledger.transfer(db, txn, LedgerEntryType.REFUND, ledger.ESCROW,
                    ledger.buyer_external(txn.buyer_id), txn.amount - seller_amount)
    _post_fee(db, txn)


# --------------------------------------------------------------- disputes
def _get_dispute(db, dispute_id, lock=False) -> models.Dispute:
    q = select(models.Dispute).where(models.Dispute.id == dispute_id)
    if lock:
        q = q.with_for_update()
    d = db.execute(q).scalar_one_or_none()
    if not d:
        raise HTTPException(404, "Dispute not found")
    return d


def get_dispute(db, user, dispute_id) -> models.Dispute:
    d = _get_dispute(db, dispute_id)
    if not _can_view(db, d.transaction, user):
        raise HTTPException(404, "Dispute not found")
    return d


def list_disputes(db, user, status: DisputeStatus | None = None):
    if user.role not in (AccountRole.ARBITER, AccountRole.ADMIN):
        raise HTTPException(403, "Arbiters and admins only")
    q = select(models.Dispute)
    if status:
        q = q.where(models.Dispute.status == status)
    return db.execute(q.order_by(models.Dispute.opened_at)).scalars().all()


def open_dispute(db, user, txn_id, reason: str) -> models.Dispute:
    txn = _get_txn(db, txn_id, lock=True)
    if not _is_party(txn, user):
        raise HTTPException(404, "Transaction not found")
    transition(txn, S.DISPUTED)           # legal only from FUNDED / DELIVERED; also freezes auto-release
    d = models.Dispute(
        transaction_id=txn.id, opened_by_id=user.id, reason=reason, status=DisputeStatus.OPEN,
        evidence_deadline=utcnow() + timedelta(hours=config.DISPUTE_EVIDENCE_HOURS),
    )
    db.add(d)
    db.flush()
    other = txn.seller_id if user.id == txn.buyer_id else txn.buyer_id
    _audit(db, user, "dispute.open", "dispute", d.id, reason=reason, meta={"transaction_id": txn.id})
    _notify(db, other, NotificationType.DISPUTE_OPENED, txn.id)
    db.commit()
    return d


def add_evidence(db, user, dispute_id, data: EvidenceIn) -> models.Dispute:
    d = _get_dispute(db, dispute_id)
    if not _is_party(d.transaction, user):
        raise HTTPException(404, "Dispute not found")
    if d.status != DisputeStatus.OPEN:
        raise HTTPException(409, "This dispute is no longer open")
    if as_utc(d.evidence_deadline) < utcnow():
        raise HTTPException(409, "The evidence deadline has passed")
    db.add(models.DisputeEvidence(dispute_id=d.id, uploaded_by_id=user.id, note=data.note, file_url=data.file_url))
    _audit(db, user, "dispute.evidence", "dispute", d.id)
    db.commit()
    db.refresh(d)
    return d


def add_message(db, user, dispute_id, data: MessageIn) -> models.Dispute:
    d = _get_dispute(db, dispute_id)
    if not _can_view(db, d.transaction, user):
        raise HTTPException(404, "Dispute not found")
    if d.status != DisputeStatus.OPEN:
        raise HTTPException(409, "This dispute is no longer open")
    db.add(models.DisputeMessage(dispute_id=d.id, sender_id=user.id, content=data.content))
    db.commit()
    db.refresh(d)
    return d


def decide_dispute(db, user, dispute_id, data: DecisionIn) -> models.Dispute:
    if user.role not in (AccountRole.ARBITER, AccountRole.ADMIN):
        raise HTTPException(403, "Only an arbiter or admin can decide a dispute")
    d = _get_dispute(db, dispute_id, lock=True)
    txn = _get_txn(db, d.transaction_id, lock=True)
    if d.status != DisputeStatus.OPEN:
        raise HTTPException(409, "This dispute has already been decided")

    if data.decision == DisputeDecision.RELEASE_TO_SELLER:
        transition(txn, S.RELEASED)
        _post_release(db, txn)
        txn.released_at = utcnow()
        notif = NotificationType.TRANSACTION_RELEASED
    elif data.decision == DisputeDecision.REFUND_TO_BUYER:
        transition(txn, S.REFUNDED)
        _post_refund(db, txn)
        notif = NotificationType.TRANSACTION_REFUNDED
    else:                                  # SPLIT
        _, seller_share = _amounts(txn)
        sa = data.split_to_seller_amount
        if not (seller_share <= sa < txn.amount):
            raise HTTPException(400, f"Split must be at least the seller's fee share ({seller_share}) and less than the full amount ({txn.amount})")
        transition(txn, S.RELEASED)
        _post_split(db, txn, sa)
        txn.released_at = utcnow()
        notif = NotificationType.TRANSACTION_RELEASED
        d.split_to_seller_amount = sa

    d.decision, d.decision_reason = data.decision, data.reason
    d.arbiter_id, d.status, d.resolved_at = user.id, DisputeStatus.DECIDED, utcnow()
    _audit(db, user, "dispute.decide", "dispute", d.id, reason=data.reason,
           meta={"decision": data.decision.value, "transaction_id": txn.id})
    for uid in (txn.buyer_id, txn.seller_id):
        _notify(db, uid, NotificationType.DISPUTE_DECIDED, txn.id, {"decision": data.decision.value})
        _notify(db, uid, notif, txn.id)
    db.commit()
    return d


# ------------------------------------------------------------------ admin
def _require_admin(user):
    if user.role != AccountRole.ADMIN:
        raise HTTPException(403, "Admins only")


def _get_user(db, user_id) -> models.User:
    u = db.get(models.User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    return u


def admin_list_users(db, admin, search: str | None = None):
    _require_admin(admin)
    q = select(models.User)
    if search:
        like = f"%{search.lower()}%"
        q = q.where(models.User.email.ilike(like) | models.User.full_name.ilike(like))
    return db.execute(q.order_by(models.User.created_at.desc()).limit(200)).scalars().all()


def admin_set_kyc(db, admin, user_id, status: KYCStatus, reason: str):
    _require_admin(admin)
    u = _get_user(db, user_id)
    before = u.kyc_status
    u.kyc_status = status
    u.kyc_verified_at = utcnow() if status == KYCStatus.VERIFIED else None
    _audit(db, admin, "admin.kyc", "user", u.id, reason=reason, meta={"from": before.value, "to": status.value})
    _notify(db, u.id, NotificationType.KYC_STATUS_CHANGED, None, {"status": status.value})
    db.commit()
    return u


def admin_set_frozen(db, admin, user_id, frozen: bool, reason: str):
    _require_admin(admin)
    u = _get_user(db, user_id)
    if u.id == admin.id:
        raise HTTPException(400, "You can't freeze your own account")
    if u.role == AccountRole.ADMIN:
        raise HTTPException(400, "Admin accounts can't be frozen here")
    u.is_active = not frozen            # a frozen user's token stops working on their very next request
    _audit(db, admin, "admin.freeze" if frozen else "admin.unfreeze", "user", u.id, reason=reason)
    db.commit()
    return u


def admin_set_role(db, admin, user_id, role: str, reason: str):
    _require_admin(admin)
    u = _get_user(db, user_id)
    if u.role == AccountRole.ADMIN:
        raise HTTPException(400, "Admin roles can only be changed from the server CLI")
    busy = db.execute(select(models.Transaction.id).where(
        ((models.Transaction.buyer_id == u.id) | (models.Transaction.seller_id == u.id)),
        models.Transaction.status.in_([S.FUNDED, S.DELIVERED, S.DISPUTED]))).first()
    if busy and role != "user":
        raise HTTPException(409, "This user has deals in progress; an arbiter can't also be a party to a deal")
    u.role = AccountRole(role)
    _audit(db, admin, "admin.role", "user", u.id, reason=reason, meta={"role": role})
    db.commit()
    return u


def admin_list_transactions(db, admin, status: S | None = None):
    _require_admin(admin)
    q = select(models.Transaction)
    if status:
        q = q.where(models.Transaction.status == status)
    return db.execute(q.order_by(models.Transaction.created_at.desc()).limit(200)).scalars().all()


def admin_stats(db, admin) -> dict:
    from sqlalchemy import func
    _require_admin(admin)
    by_status = {s.value: 0 for s in S}
    for status, n in db.execute(select(models.Transaction.status, func.count()).group_by(models.Transaction.status)):
        by_status[status.value] = n
    volume = {c: int(v) for c, v in db.execute(
        select(models.Transaction.currency, func.sum(models.Transaction.amount))
        .where(models.Transaction.status == S.RELEASED).group_by(models.Transaction.currency))}
    return {
        "users": db.execute(select(func.count()).select_from(models.User)).scalar_one(),
        "pending_kyc": db.execute(select(func.count()).select_from(models.User).where(models.User.kyc_status == KYCStatus.PENDING)).scalar_one(),
        "open_disputes": db.execute(select(func.count()).select_from(models.Dispute).where(models.Dispute.status == DisputeStatus.OPEN)).scalar_one(),
        "transactions_by_status": by_status,
        "released_volume_by_currency": volume,
    }
