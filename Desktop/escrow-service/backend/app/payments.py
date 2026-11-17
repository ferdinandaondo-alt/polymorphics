"""
Payment provider boundary.

Business logic only ever talks to `PaymentProvider`. Today that's a mock that
always succeeds; swapping in Stripe Connect later means writing one new class,
not touching the transaction flow.

NOTE for the real integration: charging a card and committing our DB row can't
be atomic. Real funding should be confirmed by a signed provider WEBHOOK (with
an idempotency key), and only then move the transaction to FUNDED.
"""
import uuid
from typing import Protocol


class PaymentProvider(Protocol):
    def charge(self, payer_id: str, amount: int, currency: str, idempotency_key: str) -> str:
        """Collect funds from the buyer. Returns the provider's reference."""


class MockPaymentProvider:
    def charge(self, payer_id: str, amount: int, currency: str, idempotency_key: str) -> str:
        return f"mock_ch_{uuid.uuid4().hex[:16]}"


def get_provider() -> PaymentProvider:
    return MockPaymentProvider()
