"""The only place that decides which transaction status changes are legal."""
from fastapi import HTTPException

from app.enums import TransactionStatus as S

ALLOWED: dict[S, set[S]] = {
    S.DRAFT: {S.ACCEPTED, S.CANCELLED, S.EXPIRED},
    S.ACCEPTED: {S.FUNDED, S.CANCELLED, S.EXPIRED},
    S.FUNDED: {S.DELIVERED, S.DISPUTED},
    S.DELIVERED: {S.RELEASED, S.DISPUTED},
    S.DISPUTED: {S.RELEASED, S.REFUNDED},
    # terminal states: no way out
    S.RELEASED: set(), S.REFUNDED: set(), S.CANCELLED: set(), S.EXPIRED: set(),
}


def transition(txn, new_status: S) -> None:
    if new_status not in ALLOWED[txn.status]:
        raise HTTPException(409, f"Cannot move a transaction from '{txn.status.value}' to '{new_status.value}'")
    txn.status = new_status
