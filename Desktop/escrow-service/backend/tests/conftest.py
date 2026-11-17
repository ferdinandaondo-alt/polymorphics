import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base, get_db
from app.enums import AccountRole, KYCStatus
from app.main import app


# By default tests run on in-memory SQLite. To run them against real Postgres:
#   TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost/testdb python -m pytest
# (the target database is wiped for every test - never point this at real data)
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture()
def db():
    if TEST_DATABASE_URL:
        engine = create_engine(TEST_DATABASE_URL)
        Base.metadata.drop_all(engine)
    else:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def client(db):
    def override():
        try:
            yield db
        finally:
            db.rollback()      # mirrors a real request ending: uncommitted work is discarded
    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


class Actor:
    """A registered, logged-in user plus convenience request helpers."""
    def __init__(self, client, db, email, role=AccountRole.USER, kyc=False):
        r = client.post("/auth/register", json={"email": email, "password": "correct-horse-1", "full_name": email.split("@")[0]})
        assert r.status_code == 201, r.text
        self.id = r.json()["id"]
        user = db.get(models.User, self.id)
        user.role = role
        if kyc:
            user.kyc_status = KYCStatus.VERIFIED
        db.commit()
        token = client.post("/auth/login", json={"email": email, "password": "correct-horse-1"}).json()["access_token"]
        self.client, self.headers = client, {"Authorization": f"Bearer {token}"}

    def get(self, url, **kw):
        return self.client.get(url, headers=self.headers, **kw)

    def post(self, url, json=None):
        return self.client.post(url, headers=self.headers, json=json)


@pytest.fixture()
def buyer(client, db):
    return Actor(client, db, "buyer@example.com")


@pytest.fixture()
def seller(client, db):
    return Actor(client, db, "seller@example.com")


@pytest.fixture()
def arbiter(client, db):
    return Actor(client, db, "arbiter@example.com", role=AccountRole.ARBITER)


@pytest.fixture()
def stranger(client, db):
    return Actor(client, db, "stranger@example.com")


def new_deal(buyer, seller, amount=50_000, fee_payer="buyer", **extra):
    r = buyer.post("/transactions", {
        "counterparty_email": "seller@example.com", "my_role": "buyer", "title": "Logo design",
        "currency": "usd", "amount": amount, "fee_payer": fee_payer, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def funded_deal(buyer, seller, **kw):
    deal = new_deal(buyer, seller, **kw)
    assert seller.post(f"/transactions/{deal['id']}/accept").status_code == 200
    assert buyer.post(f"/transactions/{deal['id']}/fund").status_code == 200
    return deal


def delivered_deal(buyer, seller, **kw):
    deal = funded_deal(buyer, seller, **kw)
    assert seller.post(f"/transactions/{deal['id']}/deliver", {"note": "done"}).status_code == 200
    return deal


def assert_ledger_sound(db, txn_id=None):
    """Every transfer group balances, and (for finished deals) escrow is empty."""
    q = select(models.LedgerEntry.transfer_group,
               func.sum(models.LedgerEntry.amount).filter(models.LedgerEntry.direction == "debit"),
               func.sum(models.LedgerEntry.amount).filter(models.LedgerEntry.direction == "credit")
               ).group_by(models.LedgerEntry.transfer_group)
    for group, debits, credits in db.execute(q):
        assert debits == credits, f"unbalanced transfer group {group}: {debits} != {credits}"
