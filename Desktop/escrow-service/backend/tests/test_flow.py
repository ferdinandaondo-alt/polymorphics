"""Happy path + money maths + permissions + illegal transitions."""
from datetime import timedelta

from app import ledger, models, services
from tests.conftest import assert_ledger_sound, delivered_deal, funded_deal, new_deal


def test_full_happy_path_buyer_pays_fee(client, db, buyer, seller):
    deal = new_deal(buyer, seller, amount=50_000)        # $500.00, fee 2.5% = $12.50
    assert deal["status"] == "draft" and deal["currency"] == "USD"
    assert deal["fee_amount"] == 1250 and deal["buyer_charge"] == 51_250 and deal["seller_net"] == 50_000
    tid = deal["id"]

    assert seller.post(f"/transactions/{tid}/accept").json()["status"] == "accepted"
    assert buyer.post(f"/transactions/{tid}/fund").json()["status"] == "funded"
    assert ledger.balance(db, ledger.ESCROW, tid) == 51_250          # buyer's money is held

    delivered = seller.post(f"/transactions/{tid}/deliver", {"note": "files sent"}).json()
    assert delivered["status"] == "delivered" and delivered["auto_release_at"]

    assert buyer.post(f"/transactions/{tid}/approve").json()["status"] == "released"
    assert ledger.balance(db, ledger.ESCROW, tid) == 0               # escrow fully emptied
    assert ledger.balance(db, ledger.seller_payable(seller.id)) == 50_000
    assert ledger.balance(db, ledger.PLATFORM_REVENUE) == 1250
    assert ledger.balance(db, ledger.buyer_external(buyer.id)) == -51_250
    assert_ledger_sound(db)

    entries = buyer.get(f"/transactions/{tid}/ledger").json()
    assert {e["entry_type"] for e in entries} == {"funding", "release", "fee"}


def test_fee_payer_seller_and_split(client, db, buyer, seller):
    d1 = funded_deal(buyer, seller, amount=50_000, fee_payer="seller")
    assert d1["buyer_charge"] == 50_000 and d1["seller_net"] == 48_750
    seller.post(f"/transactions/{d1['id']}/deliver"); buyer.post(f"/transactions/{d1['id']}/approve")
    assert ledger.balance(db, ledger.seller_payable(seller.id)) == 48_750

    d2 = new_deal(buyer, seller, amount=10_001, fee_payer="split")   # fee = 250.025 -> 250, split 125/125
    assert d2["fee_amount"] == 250 and d2["buyer_charge"] + (d2["amount"] - d2["seller_net"]) == d2["amount"] + d2["fee_amount"]
    assert_ledger_sound(db)


def test_only_the_right_party_can_act(client, db, buyer, seller, stranger):
    deal = new_deal(buyer, seller)
    tid = deal["id"]
    assert buyer.post(f"/transactions/{tid}/accept").status_code == 403      # creator can't accept own deal
    assert stranger.post(f"/transactions/{tid}/accept").status_code == 403
    seller.post(f"/transactions/{tid}/accept")
    assert seller.post(f"/transactions/{tid}/fund").status_code == 403       # seller can't fund
    assert stranger.post(f"/transactions/{tid}/fund").status_code == 403
    buyer.post(f"/transactions/{tid}/fund")
    assert buyer.post(f"/transactions/{tid}/deliver").status_code == 403     # buyer can't mark delivered
    seller.post(f"/transactions/{tid}/deliver")
    assert seller.post(f"/transactions/{tid}/approve").status_code == 403    # seller can't release own money
    assert stranger.get(f"/transactions/{tid}").status_code == 404           # outsiders can't even see it
    assert stranger.get(f"/transactions/{tid}/ledger").status_code == 404
    assert client.get(f"/transactions/{tid}").status_code in (401, 403)      # no token at all


def test_illegal_transitions_are_rejected(client, db, buyer, seller):
    tid = new_deal(buyer, seller)["id"]
    assert buyer.post(f"/transactions/{tid}/fund").status_code == 409        # not accepted yet
    assert seller.post(f"/transactions/{tid}/deliver").status_code == 409    # not funded yet
    assert buyer.post(f"/transactions/{tid}/approve").status_code == 409     # not delivered yet
    seller.post(f"/transactions/{tid}/accept")
    assert seller.post(f"/transactions/{tid}/accept").status_code == 409     # already accepted


def test_double_fund_does_not_double_charge(client, db, buyer, seller):
    tid = funded_deal(buyer, seller)["id"]
    assert buyer.post(f"/transactions/{tid}/fund").status_code == 409
    assert ledger.balance(db, ledger.ESCROW, tid) == 51_250
    n = db.query(models.LedgerEntry).filter_by(transaction_id=tid, entry_type="funding").count()
    assert n == 2                                                            # one debit + one credit, not four


def test_double_approve_does_not_double_release(client, db, buyer, seller):
    tid = delivered_deal(buyer, seller)["id"]
    assert buyer.post(f"/transactions/{tid}/approve").status_code == 200
    assert buyer.post(f"/transactions/{tid}/approve").status_code == 409
    assert ledger.balance(db, ledger.seller_payable(seller.id)) == 50_000
    assert_ledger_sound(db)


def test_cancel_only_before_funding(client, db, buyer, seller):
    t1 = new_deal(buyer, seller)["id"]
    assert seller.post(f"/transactions/{t1}/cancel").json()["status"] == "cancelled"
    t2 = funded_deal(buyer, seller)["id"]
    assert buyer.post(f"/transactions/{t2}/cancel").status_code == 409       # money is held: use a dispute


def test_validation_and_kyc(client, db, buyer, seller):
    base = {"counterparty_email": "seller@example.com", "my_role": "buyer", "title": "x", "currency": "USD", "amount": 1000}
    assert buyer.post("/transactions", {**base, "counterparty_email": "buyer@example.com"}).status_code == 400   # self-deal
    assert buyer.post("/transactions", {**base, "counterparty_email": "ghost@example.com"}).status_code == 404
    assert buyer.post("/transactions", {**base, "amount": 0}).status_code == 422
    assert buyer.post("/transactions", {**base, "amount": -5}).status_code == 422
    assert buyer.post("/transactions", {**base, "currency": "US"}).status_code == 422
    assert buyer.post("/transactions", {**base, "amount": 100_001}).status_code == 403   # over KYC threshold, unverified


def test_auto_release_after_window(client, db, buyer, seller):
    tid = delivered_deal(buyer, seller)["id"]
    now = services.utcnow()
    assert services.release_due_transactions(db, now) == []                  # window hasn't passed
    assert services.release_due_transactions(db, now + timedelta(hours=121)) == [tid]
    assert buyer.get(f"/transactions/{tid}").json()["status"] == "released"
    assert ledger.balance(db, ledger.seller_payable(seller.id)) == 50_000
    assert services.release_due_transactions(db, now + timedelta(hours=500)) == []   # idempotent
    assert_ledger_sound(db)


def test_every_state_change_is_audited(client, db, buyer, seller):
    tid = delivered_deal(buyer, seller)["id"]
    buyer.post(f"/transactions/{tid}/approve")
    actions = [a.action for a in db.query(models.AuditLog).filter_by(entity_id=tid).order_by(models.AuditLog.created_at)]
    assert set(actions) == {"transaction.create", "transaction.accept", "transaction.fund",
                            "transaction.deliver", "transaction.release"}


def test_auth_basics(client, db):
    ok = {"email": "a@example.com", "password": "correct-horse-1", "full_name": "A"}
    assert client.post("/auth/register", json=ok).status_code == 201
    assert client.post("/auth/register", json=ok).status_code == 409                       # duplicate email
    assert client.post("/auth/register", json={**ok, "email": "b@example.com", "password": "short"}).status_code == 422
    assert client.post("/auth/login", json={"email": "a@example.com", "password": "wrong-password"}).status_code == 401
    assert client.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever-1"}).status_code == 401
    token = client.post("/auth/login", json={"email": "A@Example.com", "password": "correct-horse-1"}).json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["email"] == "a@example.com" and "password_hash" not in me
    assert client.get("/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_scheduler_sweep_releases_overdue_deals_only(client, db, buyer, seller):
    """The background job's unit of work: pays out overdue deals, leaves fresh ones alone."""
    from contextlib import nullcontext
    from app.scheduler import run_auto_release_once
    overdue = delivered_deal(buyer, seller)["id"]
    fresh = delivered_deal(buyer, seller)["id"]
    db.get(models.Transaction, overdue).auto_release_at = services.utcnow() - timedelta(minutes=1)
    db.commit()
    assert run_auto_release_once(lambda: nullcontext(db)) == [overdue]
    assert buyer.get(f"/transactions/{overdue}").json()["status"] == "released"
    assert buyer.get(f"/transactions/{fresh}").json()["status"] == "delivered"
    assert run_auto_release_once(lambda: nullcontext(db)) == []            # nothing left to do
    assert ledger.balance(db, ledger.seller_payable(seller.id)) == 50_000   # only the overdue deal was paid
    assert_ledger_sound(db)
