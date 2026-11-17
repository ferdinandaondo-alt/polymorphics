from datetime import timedelta

from app import ledger, models, services
from tests.conftest import assert_ledger_sound, delivered_deal, funded_deal


def open_dispute(buyer, tid, reason="Work does not match the brief"):
    r = buyer.post(f"/transactions/{tid}/dispute", {"reason": reason})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_dispute_freezes_auto_release(client, db, buyer, seller):
    tid = delivered_deal(buyer, seller)["id"]
    open_dispute(buyer, tid)
    assert buyer.get(f"/transactions/{tid}").json()["status"] == "disputed"
    assert services.release_due_transactions(db, services.utcnow() + timedelta(days=30)) == []
    assert buyer.post(f"/transactions/{tid}/approve").status_code == 409   # can't bypass the arbiter


def test_arbiter_refunds_buyer(client, db, buyer, seller, arbiter):
    tid = delivered_deal(buyer, seller)["id"]
    did = open_dispute(buyer, tid)
    r = arbiter.post(f"/disputes/{did}/decision", {"decision": "refund_to_buyer", "reason": "Deliverable missing agreed pages"})
    assert r.status_code == 200 and r.json()["status"] == "decided"
    assert buyer.get(f"/transactions/{tid}").json()["status"] == "refunded"
    assert ledger.balance(db, ledger.ESCROW, tid) == 0
    assert ledger.balance(db, ledger.buyer_external(buyer.id)) == 0          # got every cent back, fee included
    assert ledger.balance(db, ledger.seller_payable(seller.id)) == 0
    assert ledger.balance(db, ledger.PLATFORM_REVENUE) == 0
    assert_ledger_sound(db)


def test_arbiter_releases_to_seller(client, db, buyer, seller, arbiter):
    tid = funded_deal(buyer, seller)["id"]
    did = open_dispute(seller, tid, "Buyer is unresponsive after funding")
    arbiter.post(f"/disputes/{did}/decision", {"decision": "release_to_seller", "reason": "Seller completed the agreed work"})
    assert ledger.balance(db, ledger.seller_payable(seller.id)) == 50_000
    assert ledger.balance(db, ledger.ESCROW, tid) == 0
    assert_ledger_sound(db)


def test_arbiter_split_conserves_every_cent(client, db, buyer, seller, arbiter):
    deal = delivered_deal(buyer, seller, amount=50_000, fee_payer="split")   # fee 1250: buyer 625, seller 625
    tid = deal["id"]
    did = open_dispute(buyer, tid)
    r = arbiter.post(f"/disputes/{did}/decision", {"decision": "split", "reason": "Half the pages were delivered", "split_to_seller_amount": 20_000})
    assert r.status_code == 200 and r.json()["split_to_seller_amount"] == 20_000
    assert ledger.balance(db, ledger.seller_payable(seller.id)) == 20_000 - 625
    assert ledger.balance(db, ledger.buyer_external(buyer.id)) == -(50_000 + 625) + 30_000   # paid 50,625, got 30,000 back
    assert ledger.balance(db, ledger.PLATFORM_REVENUE) == 1250
    assert ledger.balance(db, ledger.ESCROW, tid) == 0
    assert_ledger_sound(db)


def test_bad_split_amounts_rejected(client, db, buyer, seller, arbiter):
    tid = delivered_deal(buyer, seller)["id"]
    did = open_dispute(buyer, tid)
    body = lambda n: {"decision": "split", "reason": "reasoned decision", "split_to_seller_amount": n}
    assert arbiter.post(f"/disputes/{did}/decision", body(50_000)).status_code == 400    # that's a full release, not a split
    assert arbiter.post(f"/disputes/{did}/decision", body(999_999)).status_code == 400
    assert arbiter.post(f"/disputes/{did}/decision", {"decision": "split", "reason": "reasoned decision"}).status_code == 422
    assert arbiter.post(f"/disputes/{did}/decision", {"decision": "refund_to_buyer", "reason": "reasoned decision", "split_to_seller_amount": 5}).status_code == 422
    assert buyer.get(f"/transactions/{tid}").json()["status"] == "disputed"              # nothing moved
    assert ledger.balance(db, ledger.ESCROW, tid) == 51_250


def test_decision_permissions_and_finality(client, db, buyer, seller, arbiter, stranger):
    tid = delivered_deal(buyer, seller)["id"]
    did = open_dispute(buyer, tid)
    d = {"decision": "refund_to_buyer", "reason": "reasoned decision"}
    assert buyer.post(f"/disputes/{did}/decision", d).status_code == 403
    assert seller.post(f"/disputes/{did}/decision", d).status_code == 403
    assert stranger.post(f"/disputes/{did}/decision", d).status_code == 403
    assert arbiter.post(f"/disputes/{did}/decision", d).status_code == 200
    assert arbiter.post(f"/disputes/{did}/decision", {"decision": "release_to_seller", "reason": "changed my mind"}).status_code == 409
    assert_ledger_sound(db)


def test_dispute_access_and_participation(client, db, buyer, seller, arbiter, stranger):
    tid = delivered_deal(buyer, seller)["id"]
    assert stranger.post(f"/transactions/{tid}/dispute", {"reason": "not even my deal"}).status_code == 404
    did = open_dispute(buyer, tid)
    assert buyer.post(f"/transactions/{tid}/dispute", {"reason": "second dispute attempt"}).status_code == 409
    assert seller.post(f"/disputes/{did}/evidence", {"note": "Here is the delivery log"}).status_code == 200
    assert buyer.post(f"/disputes/{did}/evidence", {"file_url": "https://files.example/brief.pdf"}).status_code == 200
    assert buyer.post(f"/disputes/{did}/evidence", {}).status_code == 422
    assert seller.post(f"/disputes/{did}/messages", {"content": "Happy to revise"}).status_code == 200
    assert arbiter.post(f"/disputes/{did}/messages", {"content": "Please share the original brief"}).status_code == 200
    detail = arbiter.get(f"/disputes/{did}").json()
    assert len(detail["evidence"]) == 2 and len(detail["messages"]) == 2
    assert stranger.get(f"/disputes/{did}").status_code == 404
    assert stranger.post(f"/disputes/{did}/messages", {"content": "hello"}).status_code == 404
    assert arbiter.post(f"/disputes/{did}/evidence", {"note": "arbiters don't submit evidence"}).status_code == 404
    assert buyer.get("/disputes").status_code == 403                    # queue is staff-only
    assert [x["id"] for x in arbiter.get("/disputes?status=open").json()] == [did]


def test_arbiter_only_sees_disputed_deals(client, db, buyer, seller, arbiter):
    quiet = delivered_deal(buyer, seller)["id"]
    assert arbiter.get(f"/transactions/{quiet}").status_code == 404
    open_dispute(buyer, quiet)
    assert arbiter.get(f"/transactions/{quiet}").status_code == 200


def test_evidence_deadline_and_closed_disputes(client, db, buyer, seller, arbiter):
    tid = delivered_deal(buyer, seller)["id"]
    did = open_dispute(buyer, tid)
    d = db.get(models.Dispute, did)
    d.evidence_deadline = services.utcnow() - timedelta(hours=1)
    db.commit()
    assert buyer.post(f"/disputes/{did}/evidence", {"note": "too late"}).status_code == 409
    arbiter.post(f"/disputes/{did}/decision", {"decision": "refund_to_buyer", "reason": "reasoned decision"})
    assert seller.post(f"/disputes/{did}/messages", {"content": "after the fact"}).status_code == 409


def test_cannot_dispute_before_funding_or_after_completion(client, db, buyer, seller):
    from tests.conftest import new_deal
    tid = new_deal(buyer, seller)["id"]
    assert buyer.post(f"/transactions/{tid}/dispute", {"reason": "nothing to dispute yet"}).status_code == 409
    done = delivered_deal(buyer, seller)["id"]
    buyer.post(f"/transactions/{done}/approve")
    assert buyer.post(f"/transactions/{done}/dispute", {"reason": "changed my mind later"}).status_code == 409
