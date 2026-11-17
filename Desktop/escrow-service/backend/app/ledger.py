"""
Double-entry ledger helpers.

Convention: a transfer DEBITS the source account and CREDITS the destination.
An account's balance is therefore (credits - debits). Rows are append-only.
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.enums import LedgerEntryType

ESCROW = "escrow_holding"
PLATFORM_REVENUE = "platform_revenue"


def buyer_external(user_id: str) -> str:
    return f"buyer_external:{user_id}"


def seller_payable(user_id: str) -> str:
    return f"seller_payable:{user_id}"


def transfer(db: Session, txn: models.Transaction, entry_type: LedgerEntryType,
             source: str, destination: str, amount: int, external_reference: str | None = None) -> str:
    """Post one balanced movement (two rows sharing a transfer_group). Returns the group id."""
    if amount <= 0:
        raise ValueError("Ledger transfers must be for a positive amount")
    group = str(uuid.uuid4())
    for account, direction in ((source, "debit"), (destination, "credit")):
        db.add(models.LedgerEntry(
            transaction_id=txn.id, transfer_group=group, entry_type=entry_type,
            account=account, direction=direction, amount=amount, currency=txn.currency,
            external_reference=external_reference,
        ))
    return group


def balance(db: Session, account: str, transaction_id: str | None = None) -> int:
    q = select(
        func.coalesce(func.sum(models.LedgerEntry.amount).filter(models.LedgerEntry.direction == "credit"), 0)
        - func.coalesce(func.sum(models.LedgerEntry.amount).filter(models.LedgerEntry.direction == "debit"), 0)
    ).where(models.LedgerEntry.account == account)
    if transaction_id:
        q = q.where(models.LedgerEntry.transaction_id == transaction_id)
    return int(db.execute(q).scalar_one())
