from app.enums import AccountRole
from tests.conftest import Actor, delivered_deal, new_deal, funded_deal


def make_admin(client, db):
    return Actor(client, db, "admin@example.com", role=AccountRole.ADMIN)


def test_admin_endpoints_are_admin_only(client, db, buyer, seller, arbiter):
    admin = make_admin(client, db)
    for who in (buyer, arbiter):
        assert who.get("/admin/users").status_code == 403
        assert who.get("/admin/stats").status_code == 403
        assert who.get("/admin/transactions").status_code == 403
        assert who.post(f"/admin/users/{seller.id}/kyc", {"status": "verified", "reason": "sneaky"}).status_code == 403
        assert who.post(f"/admin/users/{seller.id}/freeze", {"frozen": True, "reason": "sneaky"}).status_code == 403
        assert who.post(f"/admin/users/{seller.id}/role", {"role": "arbiter", "reason": "sneaky"}).status_code == 403
    assert client.get("/admin/users").status_code in (401, 403)
    assert admin.get("/admin/users").status_code == 200


def test_admin_lists_and_searches_users(client, db, buyer, seller):
    admin = make_admin(client, db)
    assert len(admin.get("/admin/users").json()) == 3
    found = admin.get("/admin/users?search=SELL").json()
    assert [u["email"] for u in found] == ["seller@example.com"]
    assert "password_hash" not in found[0]


def test_admin_sets_kyc_and_it_unlocks_large_deals(client, db, buyer, seller):
    admin = make_admin(client, db)
    big = {"counterparty_email": "seller@example.com", "my_role": "buyer", "title": "Big job", "currency": "USD", "amount": 500_000}
    assert buyer.post("/transactions", big).status_code == 403
    r = admin.post(f"/admin/users/{buyer.id}/kyc", {"status": "verified", "reason": "Passport checked"})
    assert r.status_code == 200 and r.json()["kyc_status"] == "verified"
    assert buyer.post("/transactions", big).status_code == 201


def test_freeze_locks_user_out_immediately_and_unfreeze_restores(client, db, buyer, seller):
    admin = make_admin(client, db)
    assert buyer.get("/auth/me").status_code == 200
    assert admin.post(f"/admin/users/{buyer.id}/freeze", {"frozen": True, "reason": "Suspected fraud"}).status_code == 200
    assert buyer.get("/auth/me").status_code == 401                          # existing token dies at once
    assert client.post("/auth/login", json={"email": "buyer@example.com", "password": "correct-horse-1"}).status_code == 401
    assert seller.post("/transactions", {"counterparty_email": "buyer@example.com", "my_role": "seller",
                                         "title": "x", "currency": "USD", "amount": 1000}).status_code == 404
    admin.post(f"/admin/users/{buyer.id}/freeze", {"frozen": False, "reason": "Cleared after review"})
    assert buyer.get("/auth/me").status_code == 200


def test_admin_cannot_freeze_self_or_other_admins(client, db):
    admin = make_admin(client, db)
    other = Actor(client, db, "admin2@example.com", role=AccountRole.ADMIN)
    assert admin.post(f"/admin/users/{admin.id}/freeze", {"frozen": True, "reason": "oops"}).status_code == 400
    assert admin.post(f"/admin/users/{other.id}/freeze", {"frozen": True, "reason": "oops"}).status_code == 400
    assert admin.post(f"/admin/users/{other.id}/role", {"role": "user", "reason": "demote"}).status_code == 400
    assert admin.post("/admin/users/does-not-exist/kyc", {"status": "verified", "reason": "nope"}).status_code == 404


def test_role_change_rules(client, db, buyer, seller):
    admin = make_admin(client, db)
    assert admin.post(f"/admin/users/{seller.id}/role", {"role": "arbiter", "reason": "Trusted staff"}).json()["role"] == "arbiter"
    assert admin.post(f"/admin/users/{seller.id}/role", {"role": "admin", "reason": "escalate"}).status_code == 422   # can't mint admins via API
    # a user with money in play can't become an arbiter
    busy_seller = Actor(client, db, "busy@example.com")
    r = buyer.post("/transactions", {"counterparty_email": "busy@example.com", "my_role": "buyer", "title": "x", "currency": "USD", "amount": 5000})
    busy_seller.post(f"/transactions/{r.json()['id']}/accept"); buyer.post(f"/transactions/{r.json()['id']}/fund")
    assert admin.post(f"/admin/users/{busy_seller.id}/role", {"role": "arbiter", "reason": "Trusted staff"}).status_code == 409


def test_admin_admin_actions_are_audited(client, db, buyer):
    from app import models
    admin = make_admin(client, db)
    admin.post(f"/admin/users/{buyer.id}/kyc", {"status": "rejected", "reason": "Blurry ID"})
    admin.post(f"/admin/users/{buyer.id}/freeze", {"frozen": True, "reason": "Chargeback ring"})
    rows = db.query(models.AuditLog).filter(models.AuditLog.entity_id == buyer.id).all()
    assert {(r.action, r.reason) for r in rows} == {("admin.kyc", "Blurry ID"), ("admin.freeze", "Chargeback ring")}
    assert all(r.actor_id == admin.id for r in rows)


def test_admin_transactions_and_stats(client, db, buyer, seller, arbiter):
    admin = make_admin(client, db)
    done = delivered_deal(buyer, seller)["id"]; buyer.post(f"/transactions/{done}/approve")
    disputed = delivered_deal(buyer, seller)["id"]; buyer.post(f"/transactions/{disputed}/dispute", {"reason": "Not as described"})
    new_deal(buyer, seller)
    allt = admin.get("/admin/transactions").json()
    assert len(allt) == 3 and {"buyer_name", "seller_name"} <= set(allt[0])
    assert [t["id"] for t in admin.get("/admin/transactions?status=disputed").json()] == [disputed]
    s = admin.get("/admin/stats").json()
    assert s["users"] == 4 and s["open_disputes"] == 1
    assert s["transactions_by_status"]["released"] == 1 and s["transactions_by_status"]["disputed"] == 1
    assert s["released_volume_by_currency"] == {"USD": 50_000}


def test_transaction_exposes_names_and_dispute_link(client, db, buyer, seller):
    tid = delivered_deal(buyer, seller)["id"]
    t = buyer.get(f"/transactions/{tid}").json()
    assert t["buyer_name"] == "buyer" and t["seller_name"] == "seller" and t["dispute_id"] is None
    did = buyer.post(f"/transactions/{tid}/dispute", {"reason": "Not as described"}).json()["id"]
    assert seller.get(f"/transactions/{tid}").json()["dispute_id"] == did


def test_public_config_and_dispute_details(client, db, buyer, seller, arbiter):
    cfg = client.get("/config").json()
    assert cfg["platform_fee_bps"] == 250 and cfg["kyc_threshold"] == 100_000
    tid = delivered_deal(buyer, seller)["id"]
    did = buyer.post(f"/transactions/{tid}/dispute", {"reason": "Not as described"}).json()["id"]
    row = arbiter.get("/disputes?status=open").json()[0]
    assert row["id"] == did and row["transaction_title"] == "Logo design"
    assert (row["buyer_name"], row["seller_name"], row["amount"], row["currency"]) == ("buyer", "seller", 50_000, "USD")


def test_database_url_normalisation():
    from app.database import normalize_database_url as n
    assert n("postgres://u:p@h:5432/db") == "postgresql+psycopg://u:p@h:5432/db"
    assert n("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert n("postgresql+psycopg://u:p@h/db") == "postgresql+psycopg://u:p@h/db"     # already explicit: untouched
    assert n("sqlite:///./x.db") == "sqlite:///./x.db"


def test_ledger_is_listed_debit_before_credit(client, db, buyer, seller):
    tid = funded_deal(buyer, seller)["id"]
    entries = buyer.get(f"/transactions/{tid}/ledger").json()
    assert [e["direction"] for e in entries] == ["debit", "credit"]
