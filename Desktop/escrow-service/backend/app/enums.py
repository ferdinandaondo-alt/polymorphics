"""
Enumerations shared across the escrow schema.

Keeping these as Python enums (mapped to native Postgres ENUM types) means
illegal values are rejected at the database level, not just in application
code.
"""
import enum


class AccountRole(str, enum.Enum):
    """Account-level role. Buyer/seller are NOT here — see Transaction."""
    USER = "user"          # ordinary user; can be buyer or seller per-transaction
    ARBITER = "arbiter"    # can be assigned to resolve disputes
    ADMIN = "admin"        # platform staff


class KYCStatus(str, enum.Enum):
    UNVERIFIED = "unverified"
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class TransactionStatus(str, enum.Enum):
    DRAFT = "draft"                # created, awaiting counterparty acceptance
    ACCEPTED = "accepted"          # both parties agreed, awaiting funding
    FUNDED = "funded"              # buyer's payment confirmed, held in escrow
    DELIVERED = "delivered"        # seller marked delivered, awaiting buyer action
    RELEASED = "released"          # funds released to seller — terminal
    REFUNDED = "refunded"          # funds returned to buyer — terminal
    DISPUTED = "disputed"          # under arbiter review
    CANCELLED = "cancelled"        # cancelled pre-funding — terminal
    EXPIRED = "expired"            # cancelled pre-funding due to timeout — terminal


class MilestoneStatus(str, enum.Enum):
    PENDING = "pending"
    FUNDED = "funded"
    DELIVERED = "delivered"
    RELEASED = "released"
    REFUNDED = "refunded"
    DISPUTED = "disputed"


class LedgerEntryType(str, enum.Enum):
    FUNDING = "funding"              # buyer external account -> escrow holding
    RELEASE = "release"              # escrow holding -> seller payable
    REFUND = "refund"                # escrow holding -> buyer external account
    FEE = "fee"                      # escrow holding -> platform revenue
    PAYOUT = "payout"                # seller payable -> seller external account
    ADJUSTMENT = "adjustment"        # manual admin correction (always logged)


class DisputeStatus(str, enum.Enum):
    OPEN = "open"
    AWAITING_ARBITER = "awaiting_arbiter"
    DECIDED = "decided"
    CLOSED = "closed"


class DisputeDecision(str, enum.Enum):
    RELEASE_TO_SELLER = "release_to_seller"
    REFUND_TO_BUYER = "refund_to_buyer"
    SPLIT = "split"


class NotificationType(str, enum.Enum):
    TRANSACTION_FUNDED = "transaction_funded"
    TRANSACTION_DELIVERED = "transaction_delivered"
    TRANSACTION_RELEASED = "transaction_released"
    TRANSACTION_REFUNDED = "transaction_refunded"
    DISPUTE_OPENED = "dispute_opened"
    DISPUTE_DECIDED = "dispute_decided"
    PAYOUT_SENT = "payout_sent"
    KYC_STATUS_CHANGED = "kyc_status_changed"
