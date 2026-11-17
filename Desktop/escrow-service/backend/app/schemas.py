from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.enums import (AccountRole, DisputeDecision, DisputeStatus, KYCStatus,
                       LedgerEntryType, TransactionStatus)
from app.fees import fee_shares


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth ----
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(ORM):
    id: str
    email: str
    full_name: str
    role: AccountRole
    kyc_status: KYCStatus
    mfa_enabled: bool


# ---- transactions ----
class TransactionCreate(BaseModel):
    counterparty_email: EmailStr
    my_role: Literal["buyer", "seller"]
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    currency: str = Field(min_length=3, max_length=3)
    amount: int = Field(gt=0, le=1_000_000_000, description="Minor units (cents). 1050 = 10.50")
    fee_payer: Literal["buyer", "seller", "split"] = "buyer"
    delivery_deadline: datetime | None = None
    auto_release_hours: int = Field(default=120, ge=24, le=24 * 30)

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str) -> str:
        if not v.isalpha():
            raise ValueError("currency must be a 3-letter ISO code")
        return v.upper()


class DeliverIn(BaseModel):
    note: str | None = Field(default=None, max_length=5000)


class TransactionOut(ORM):
    id: str
    buyer_id: str
    seller_id: str
    buyer_name: str
    seller_name: str
    created_by_id: str
    title: str
    description: str | None
    currency: str
    amount: int
    fee_amount: int
    fee_payer: str
    dispute_id: str | None  # most recent dispute on this deal, if any
    buyer_charge: int       # what the buyer pays in total (amount + their fee share)
    seller_net: int         # what the seller receives on a normal release
    status: TransactionStatus
    delivery_deadline: datetime | None
    auto_release_at: datetime | None
    created_at: datetime | None

    @classmethod
    def from_model(cls, t) -> "TransactionOut":
        buyer_share, seller_share = fee_shares(t.fee_amount, t.fee_payer)
        return cls(
            id=t.id, buyer_id=t.buyer_id, seller_id=t.seller_id, created_by_id=t.created_by_id,
            buyer_name=t.buyer.full_name, seller_name=t.seller.full_name,
            dispute_id=t.disputes[-1].id if t.disputes else None,
            title=t.title, description=t.description, currency=t.currency, amount=t.amount,
            fee_amount=t.fee_amount, fee_payer=t.fee_payer,
            buyer_charge=t.amount + buyer_share, seller_net=t.amount - seller_share,
            status=t.status, delivery_deadline=t.delivery_deadline,
            auto_release_at=t.auto_release_at, created_at=t.created_at,
        )


class LedgerEntryOut(ORM):
    id: str
    transfer_group: str
    entry_type: LedgerEntryType
    account: str
    direction: str
    amount: int
    currency: str
    created_at: datetime | None


# ---- disputes ----
class DisputeOpen(BaseModel):
    reason: str = Field(min_length=5, max_length=5000)


class EvidenceIn(BaseModel):
    note: str | None = Field(default=None, max_length=5000)
    file_url: str | None = Field(default=None, max_length=1024)

    @model_validator(mode="after")
    def _something(self):
        if not self.note and not self.file_url:
            raise ValueError("Provide a note or a file_url")
        return self


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


class DecisionIn(BaseModel):
    decision: DisputeDecision
    reason: str = Field(min_length=5, max_length=5000)
    split_to_seller_amount: int | None = Field(default=None, gt=0, description="Portion of the item price (minor units) the seller keeps. Only for 'split'.")

    @model_validator(mode="after")
    def _split(self):
        if self.decision == DisputeDecision.SPLIT and self.split_to_seller_amount is None:
            raise ValueError("split_to_seller_amount is required for a split decision")
        if self.decision != DisputeDecision.SPLIT and self.split_to_seller_amount is not None:
            raise ValueError("split_to_seller_amount is only allowed for a split decision")
        return self


class EvidenceOut(ORM):
    id: str
    uploaded_by_id: str
    file_url: str | None
    note: str | None
    created_at: datetime | None


class MessageOut(ORM):
    id: str
    sender_id: str
    content: str
    created_at: datetime | None


class DisputeOut(ORM):
    id: str
    transaction_id: str
    transaction_title: str
    buyer_name: str
    seller_name: str
    amount: int
    currency: str
    opened_by_id: str
    arbiter_id: str | None
    reason: str
    status: DisputeStatus
    decision: DisputeDecision | None
    decision_reason: str | None
    split_to_seller_amount: int | None
    evidence_deadline: datetime | None
    opened_at: datetime | None
    resolved_at: datetime | None
    evidence: list[EvidenceOut] = []
    messages: list[MessageOut] = []


# ---- admin ----
class AdminUserOut(ORM):
    id: str
    email: str
    full_name: str
    role: AccountRole
    kyc_status: KYCStatus
    is_active: bool
    created_at: datetime | None


class KYCIn(BaseModel):
    status: KYCStatus
    reason: str = Field(min_length=3, max_length=1000)


class FreezeIn(BaseModel):
    frozen: bool
    reason: str = Field(min_length=3, max_length=1000)


class RoleIn(BaseModel):
    role: Literal["user", "arbiter"]
    reason: str = Field(min_length=3, max_length=1000)


class AdminTransactionOut(TransactionOut):
    pass


class StatsOut(BaseModel):
    users: int
    pending_kyc: int
    open_disputes: int
    transactions_by_status: dict[str, int]
    released_volume_by_currency: dict[str, int]
