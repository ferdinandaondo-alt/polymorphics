"""
Runs a realistic scenario against the real API (in-memory DB) and saves the JSON responses.
The front-end tests render pages with THESE responses, so the UI is always tested against the
backend's true response shapes. Re-run after changing the API:

    cd backend && python scripts/dump_fixtures.py
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base, get_db
from app.enums import AccountRole
from app.main import app

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Base.metadata.create_all(engine)
db = sessionmaker(bind=engine, autoflush=False)()


def override():
    yield db
app.dependency_overrides[get_db] = override
client = TestClient(app)


def make(email, name, role=AccountRole.USER):
    uid = client.post("/auth/register", json={"email": email, "password": "correct-horse-1", "full_name": name}).json()["id"]
    u = db.get(models.User, uid); u.role = role; db.commit()
    tok = client.post("/auth/login", json={"email": email, "password": "correct-horse-1"}).json()["access_token"]
    return {"id": uid, "h": {"Authorization": f"Bearer {tok}"}}


admin = make("admin@example.com", "Ada Admin", AccountRole.ADMIN)
arbiter = make("arb@example.com", "Arlo Arbiter", AccountRole.ARBITER)
buyer = make("bea@example.com", "Bea Buyer")
seller = make("sam@example.com", "Sam Seller")


def call(who, method, url, body=None):
    r = client.request(method, url, headers=who["h"], json=body)
    assert r.status_code < 300, (method, url, r.status_code, r.text)
    return r.json()


def deal(title, amount=50_000):
    return call(buyer, "POST", "/transactions", {"counterparty_email": "sam@example.com", "my_role": "buyer",
                "title": title, "description": "Brand identity: logo, palette and typography.", "currency": "USD", "amount": amount})["id"]


ids = {}
ids["draft"] = deal("Draft deal")
ids["accepted"] = deal("Accepted deal"); call(seller, "POST", f"/transactions/{ids['accepted']}/accept")
ids["funded"] = deal("Funded deal"); call(seller, "POST", f"/transactions/{ids['funded']}/accept"); call(buyer, "POST", f"/transactions/{ids['funded']}/fund")
ids["delivered"] = deal("Delivered deal")
for step, who in (("accept", seller), ("fund", buyer), ("deliver", seller)):
    call(who, "POST", f"/transactions/{ids['delivered']}/{step}")
ids["disputed"] = deal("Disputed deal")
for step, who in (("accept", seller), ("fund", buyer), ("deliver", seller)):
    call(who, "POST", f"/transactions/{ids['disputed']}/{step}")
dispute_id = call(buyer, "POST", f"/transactions/{ids['disputed']}/dispute", {"reason": "The logo files were never delivered."})["id"]
call(seller, "POST", f"/disputes/{dispute_id}/evidence", {"note": "Delivery email sent on the agreed date", "file_url": "https://files.example.com/proof.pdf"})
call(buyer, "POST", f"/disputes/{dispute_id}/messages", {"content": "I only received a draft."})
call(arbiter, "POST", f"/disputes/{dispute_id}/messages", {"content": "Please upload the original brief."})
ids["released"] = deal("Released deal")
for step, who in (("accept", seller), ("fund", buyer), ("deliver", seller), ("approve", buyer)):
    call(who, "POST", f"/transactions/{ids['released']}/{step}")
call(admin, "POST", f"/admin/users/{seller['id']}/kyc", {"status": "verified", "reason": "ID verified"})

fx = {
    "ids": {**ids, "dispute": dispute_id},
    "users": {"buyer": buyer["id"], "seller": seller["id"], "arbiter": arbiter["id"], "admin": admin["id"]},
    "config": client.get("/config").json(),
    "me": {k: call(w, "GET", "/auth/me") for k, w in (("buyer", buyer), ("seller", seller), ("arbiter", arbiter), ("admin", admin))},
    "transactions": call(buyer, "GET", "/transactions"),
    "transaction": {k: call(buyer, "GET", f"/transactions/{v}") for k, v in ids.items()},
    "ledger": {k: call(buyer, "GET", f"/transactions/{ids[k]}/ledger") for k in ("funded", "released")},
    "dispute": call(arbiter, "GET", f"/disputes/{dispute_id}"),
    "disputes": call(arbiter, "GET", "/disputes"),
    "admin": {"stats": call(admin, "GET", "/admin/stats"), "users": call(admin, "GET", "/admin/users"),
              "transactions": call(admin, "GET", "/admin/transactions")},
}
out = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "test" / "fixtures.json"
out.write_text(json.dumps(fx, indent=1, default=str))
print("wrote", out, f"({out.stat().st_size // 1024} KB)")
print("sample transaction keys:", sorted(fx["transaction"]["funded"].keys()))
