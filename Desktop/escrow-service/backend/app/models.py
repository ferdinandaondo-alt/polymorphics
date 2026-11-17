"""
Core data model for the escrow service.

Table overview
--------------
User             account-level identity, role, and KYC status
PayoutAccount    a user's verified destination for withdrawing funds
Transaction      one escrow deal between a buyer and a seller
Milestone        optional sub-part of a Transaction with its own amount
LedgerEntry      one leg of a double-entry bookkeeping record
Dispute          a disagreement raised on a Transaction (or one Milestone)
DisputeEvidence  a file or note submitted as part of a Dispute
DisputeMessage   a chat-style message inside a Dispute thread
Notification     an in-app/email/SMS notification queued for a user
AuditLog         an immutable record of who did what, when, and why

Design notes
------------
- Buyer/seller are per-Transaction (a user can be either, on different deals),
  so those are foreign keys on Transaction, not a role on User.
- Money is stored as integer minor units (cents), never float, to avoid
  rounding errors. amount=1050 + currency="USD" means $10.50.
- LedgerEntry rows are append-only: never UPDATE or DELETE a posted entry.
  A correction is a new, offsetting entry, so the ledger is a full history.
- AuditLog is populated by application code on every state-changing action,
  not by DB triggers, so it can capture *who* and *why*, not just *what changed*.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    String, Integer, BigInteger, Boolean, DateTime, ForeignKey, Text,
    Enum as SAEnum, UniqueConstraint, CheckConstraint, Index, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import (
    AccountRole, KYCStatus, TransactionStatus, MilestoneStatus,
    LedgerEntryType, DisputeStatus, DisputeDecision, NotificationType,
)


def uuid_pk() -> Mapped[str]:
    """Shared UUID primary key column factory."""
    return mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = uuid_pk()
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[AccountRole] = mapped_column(
        SAEnum(AccountRole, name="account_role"), nullable=False, default=AccountRole.USER
    )

    kyc_status: Mapped[KYCStatus] = mapped_column(
        SAEnum(KYCStatus, name="kyc_status"), nullable=False, default=KYCStatus.UNVERIFIED
    )
    kyc_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    payout_accounts: Mapped[list["PayoutAccount"]] = relationship(back_populates="user")

    __table_args__ = (
        Index("ix_users_role", "role"),
    )


class PayoutAccount(Base):
    """A verified external destination (bank account / card) a user can withdraw to."""
    __tablename__ = "payout_accounts"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

    provider: Mapped[str] = mapped_column(String(50), nullable=False)        # e.g. "stripe"
    external_account_id: Mapped[str] = mapped_column(String(255), nullable=False)  # provider's ID
    label: Mapped[str] = mapped_column(String(255), nullable=False)          # e.g. "Chase ••1234"
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="payout_accounts")

    __table_args__ = (
        UniqueConstraint("provider", "external_account_id", name="uq_payout_provider_account"),
    )


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = uuid_pk()

    buyer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    seller_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    # Whoever proposed the deal; the *other* party is the one who must accept it.
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    currency: Mapped[str] = mapped_column(String(3), nullable=False)          # ISO 4217, e.g. "USD"
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)           # minor units
    fee_amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    fee_payer: Mapped[str] = mapped_column(String(10), nullable=False, default="buyer")  # buyer|seller|split

    status: Mapped[TransactionStatus] = mapped_column(
        SAEnum(TransactionStatus, name="transaction_status"),
        nullable=False, default=TransactionStatus.DRAFT, index=True,
    )

    delivery_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auto_release_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=120)  # 5 days default

    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    funded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auto_release_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    buyer: Mapped["User"] = relationship(foreign_keys=[buyer_id])
    seller: Mapped["User"] = relationship(foreign_keys=[seller_id])
    milestones: Mapped[list["Milestone"]] = relationship(back_populates="transaction", cascade="all, delete-orphan")
    ledger_entries: Mapped[list["LedgerEntry"]] = relationship(back_populates="transaction")
    disputes: Mapped[list["Dispute"]] = relationship(back_populates="transaction")

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transaction_amount_positive"),
        CheckConstraint("buyer_id != seller_id", name="ck_buyer_seller_distinct"),
        CheckConstraint("fee_payer IN ('buyer','seller','split')", name="ck_fee_payer_valid"),
        Index("ix_transactions_buyer", "buyer_id"),
        Index("ix_transactions_seller", "seller_id"),
    )


class Milestone(Base):
    """Optional: splits a Transaction's amount into sub-deliverables, each released separately."""
    __tablename__ = "milestones"

    id: Mapped[str] = uuid_pk()
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), nullable=False)

    sequence: Mapped[int] = mapped_column(Integer, nullable=False)   # display order, 1-based
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)  # minor units; sum must == transaction.amount

    status: Mapped[MilestoneStatus] = mapped_column(
        SAEnum(MilestoneStatus, name="milestone_status"), nullable=False, default=MilestoneStatus.PENDING
    )

    delivery_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    transaction: Mapped["Transaction"] = relationship(back_populates="milestones")

    __table_args__ = (
        UniqueConstraint("transaction_id", "sequence", name="uq_milestone_sequence"),
        CheckConstraint("amount > 0", name="ck_milestone_amount_positive"),
    )


# ---------------------------------------------------------------------------
# Ledger — the source of truth for money movement
# ---------------------------------------------------------------------------

class LedgerEntry(Base):
    """
    One leg of a double-entry record. Every real-world money movement produces
    at least two rows (a debit and a credit) that net to zero for that movement.
    Rows are never updated or deleted; corrections are new offsetting rows.
    """
    __tablename__ = "ledger_entries"

    id: Mapped[str] = uuid_pk()
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), nullable=False)

    # A transfer_group ties together the legs of one movement (e.g. one funding
    # event = a debit on buyer_external and a credit on escrow_holding, same group).
    transfer_group: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    entry_type: Mapped[LedgerEntryType] = mapped_column(
        SAEnum(LedgerEntryType, name="ledger_entry_type"), nullable=False
    )

    # Account names are logical, not separate tables: e.g. "escrow_holding",
    # "platform_revenue", "buyer_external:<user_id>", "seller_payable:<user_id>".
    account: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(6), nullable=False)  # "debit" | "credit"
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)    # minor units, always positive
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    external_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)  # provider charge/payout id
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    transaction: Mapped["Transaction"] = relationship(back_populates="ledger_entries")

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_ledger_amount_positive"),
        CheckConstraint("direction IN ('debit','credit')", name="ck_ledger_direction_valid"),
        Index("ix_ledger_transfer_group", "transfer_group"),
    )


# ---------------------------------------------------------------------------
# Disputes
# ---------------------------------------------------------------------------

class Dispute(Base):
    __tablename__ = "disputes"

    id: Mapped[str] = uuid_pk()
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), nullable=False)
    milestone_id: Mapped[str | None] = mapped_column(ForeignKey("milestones.id"), nullable=True)

    opened_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    arbiter_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[DisputeStatus] = mapped_column(
        SAEnum(DisputeStatus, name="dispute_status"), nullable=False, default=DisputeStatus.OPEN
    )

    decision: Mapped[DisputeDecision | None] = mapped_column(
        SAEnum(DisputeDecision, name="dispute_decision"), nullable=True
    )
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    split_to_seller_amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # only if SPLIT

    evidence_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    transaction: Mapped["Transaction"] = relationship(back_populates="disputes")

    # read-only conveniences so the API can show deal details next to a dispute
    @property
    def transaction_title(self) -> str: return self.transaction.title
    @property
    def buyer_name(self) -> str: return self.transaction.buyer.full_name
    @property
    def seller_name(self) -> str: return self.transaction.seller.full_name
    @property
    def amount(self) -> int: return self.transaction.amount
    @property
    def currency(self) -> str: return self.transaction.currency

    evidence: Mapped[list["DisputeEvidence"]] = relationship(back_populates="dispute", cascade="all, delete-orphan")
    messages: Mapped[list["DisputeMessage"]] = relationship(back_populates="dispute", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_disputes_status", "status"),
    )


class DisputeEvidence(Base):
    __tablename__ = "dispute_evidence"

    id: Mapped[str] = uuid_pk()
    dispute_id: Mapped[str] = mapped_column(ForeignKey("disputes.id"), nullable=False)
    uploaded_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

    file_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    dispute: Mapped["Dispute"] = relationship(back_populates="evidence")


class DisputeMessage(Base):
    __tablename__ = "dispute_messages"

    id: Mapped[str] = uuid_pk()
    dispute_id: Mapped[str] = mapped_column(ForeignKey("disputes.id"), nullable=False)
    sender_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    dispute: Mapped["Dispute"] = relationship(back_populates="messages")


# ---------------------------------------------------------------------------
# Notifications & audit
# ---------------------------------------------------------------------------

class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    type: Mapped[NotificationType] = mapped_column(
        SAEnum(NotificationType, name="notification_type"), nullable=False
    )
    transaction_id: Mapped[str | None] = mapped_column(ForeignKey("transactions.id"), nullable=True)

    payload: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON-encoded extra context
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_notifications_user_unread", "user_id", "read_at"),
    )


class AuditLog(Base):
    """
    Append-only. Never updated or deleted by application code (enforce this
    with DB permissions in production — the app's DB role should have no
    UPDATE/DELETE grant on this table).
    """
    __tablename__ = "audit_log"

    id: Mapped[str] = uuid_pk()
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # null = system
    action: Mapped[str] = mapped_column(String(100), nullable=False)        # e.g. "transaction.release"
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)    # e.g. "transaction"
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[str | None] = mapped_column(Text, nullable=True)           # JSON-encoded diff/context
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
    )
