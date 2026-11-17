"""Fee maths. Integer minor units only — no floats anywhere near money."""
from app import config


def compute_fee(amount: int) -> int:
    """Platform fee, rounded half-up to the nearest minor unit."""
    return (amount * config.PLATFORM_FEE_BPS + 5000) // 10000


def fee_shares(fee_amount: int, fee_payer: str) -> tuple[int, int]:
    """Return (buyer_share, seller_share) of the fee. The two always sum to fee_amount."""
    if fee_payer == "buyer":
        return fee_amount, 0
    if fee_payer == "seller":
        return 0, fee_amount
    seller_share = fee_amount // 2          # 'split': odd cent goes to the buyer
    return fee_amount - seller_share, seller_share
