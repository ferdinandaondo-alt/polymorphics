"""
Race-condition test: needs real Postgres (SQLite has no row locks), so it only runs when
TEST_DATABASE_URL is set. Proves that SELECT ... FOR UPDATE stops simultaneous requests
from releasing / refunding the same escrowed funds more than once.
"""
import threading

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from app import ledger, models, services
from tests.conftest import TEST_DATABASE_URL, assert_ledger_sound, delivered_deal

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="needs PostgreSQL (set TEST_DATABASE_URL)")


def race(db, actions):
    """Run each `action(session)` in its own thread, all released at the same instant. Returns outcomes."""
    Session = sessionmaker(bind=db.get_bind())
    barrier, outcomes = threading.Barrier(len(actions)), []

    def worker(action):
        with Session() as s:
            barrier.wait()
            try:
                action(s)
                outcomes.append("ok")
            except HTTPException as e:
                outcomes.append(e.status_code)
    threads = [threading.Thread(target=worker, args=(a,)) for a in actions]
    [t.start() for t in threads]
    [t.join() for t in threads]
    db.expire_all()
    return outcomes


def test_simultaneous_approvals_release_only_once(client, db, buyer, seller):
    tid = delivered_deal(buyer, seller)["id"]

    def approve(s):
        services.approve_transaction(s, s.get(models.User, buyer.id), tid)

    outcomes = race(db, [approve] * 8)
    assert outcomes.count("ok") == 1 and outcomes.count(409) == 7, outcomes
    assert ledger.balance(db, ledger.seller_payable(seller.id)) == 50_000      # paid once, not 8 times
    assert ledger.balance(db, ledger.ESCROW, tid) == 0
    assert_ledger_sound(db)


def test_simultaneous_funding_charges_only_once(client, db, buyer, seller):
    from tests.conftest import new_deal
    tid = new_deal(buyer, seller)["id"]
    seller.post(f"/transactions/{tid}/accept")

    def fund(s):
        services.fund_transaction(s, s.get(models.User, buyer.id), tid)

    outcomes = race(db, [fund] * 8)
    assert outcomes.count("ok") == 1, outcomes
    assert ledger.balance(db, ledger.ESCROW, tid) == 51_250                    # one charge only
    assert_ledger_sound(db)


def test_auto_release_and_buyer_approval_cannot_both_pay(client, db, buyer, seller):
    from datetime import timedelta
    tid = delivered_deal(buyer, seller)["id"]
    later = services.utcnow() + timedelta(days=30)
    results = []

    def approve(s):
        services.approve_transaction(s, s.get(models.User, buyer.id), tid)

    def sweep(s):
        results.append(len(services.release_due_transactions(s, later)))

    outcomes = race(db, [approve, sweep])
    assert outcomes.count("ok") >= 1             # whoever loses gets a clean 409 or finds nothing left to do
    assert ledger.balance(db, ledger.seller_payable(seller.id)) == 50_000      # exactly once, whichever won
    assert ledger.balance(db, ledger.ESCROW, tid) == 0
    assert_ledger_sound(db)
