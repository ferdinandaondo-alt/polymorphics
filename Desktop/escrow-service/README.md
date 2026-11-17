# Escrow Service

A working escrow platform: a buyer pays into escrow, the seller delivers, and the money is released when the
buyer approves, a timer runs out, or an arbiter settles a dispute.

> **Status: complete workflow, simulated payments.** No real money moves. See
> [DEPLOYMENT.md → Part 7](DEPLOYMENT.md#part-7--before-real-money) for what's needed before holding real funds.

## What it does
- **Users** register, log in, and trade as buyer or seller. The same account can be either on different deals.
- **Deal flow:** create → counterparty accepts → buyer funds → seller delivers → buyer approves (or auto-release after a set window).
- **Money handling:** integer-cent amounts, a 2.5% configurable platform fee (buyer, seller, or split), and an append-only
  **double-entry ledger** that always balances. Row locks stop simultaneous requests from paying out twice.
- **Disputes:** either party opens one (freezing the funds); both add evidence and messages; an **arbiter** releases, refunds, or splits.
- **Admin panel:** platform stats, user search, KYC decisions, freeze/unfreeze, arbiter assignment, all transactions. Every action requires a reason and is audit-logged.
- **Safeguards:** KYC required above a size threshold, audit log on every state change, security headers + CSP, production mode refuses weak secrets.

## Quick start (on your computer)
```bash
# terminal 1 — backend
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && uvicorn app.main:app --reload

# terminal 2 — frontend
cd frontend && npm install && npm run dev        # open http://localhost:5173
```
Deploying to a server: **[DEPLOYMENT.md](DEPLOYMENT.md)** (step by step).

## How it was tested
| Layer | What | Result |
|---|---|---|
| Backend | 37 tests: happy path, permissions, illegal transitions, duplicate calls, disputes, admin, ledger balance, **race conditions** | pass on PostgreSQL 16 (34 + 3 skipped on SQLite) |
| Race protection | 8 simultaneous "approve" requests → exactly 1 succeeds. With the lock removed, all 8 succeeded (so the test has teeth) | verified |
| Frontend | 40 tests rendering real pages against **real API responses** captured from the backend | pass |
| End to end | Real Chromium drives buyer, seller, arbiter and admin through every flow, incl. auto-release | pass in dev mode **and** against PostgreSQL + production mode + the production Caddy config |
| Not tested | The Docker images themselves (Docker wasn't available where this was built) | see DEPLOYMENT.md troubleshooting |

## Project layout
`backend/` Python API · `frontend/` React app · `e2e/` browser test · `docker-compose.yml` + `.env.example` for deployment.

## API summary
Interactive docs at `/docs` in development (disabled in production).

| Area | Method | Path |
|---|---|---|
| auth | POST | `/auth/login` |
| auth | GET | `/auth/me` |
| auth | POST | `/auth/register` |
| transactions | POST | `/transactions` |
| transactions | GET | `/transactions` |
| transactions | GET | `/transactions/{txn_id}` |
| transactions | POST | `/transactions/{txn_id}/accept` |
| transactions | POST | `/transactions/{txn_id}/approve` |
| transactions | POST | `/transactions/{txn_id}/cancel` |
| transactions | POST | `/transactions/{txn_id}/deliver` |
| transactions | POST | `/transactions/{txn_id}/dispute` |
| transactions | POST | `/transactions/{txn_id}/fund` |
| transactions | GET | `/transactions/{txn_id}/ledger` |
| disputes | GET | `/disputes` |
| disputes | GET | `/disputes/{dispute_id}` |
| disputes | POST | `/disputes/{dispute_id}/decision` |
| disputes | POST | `/disputes/{dispute_id}/evidence` |
| disputes | POST | `/disputes/{dispute_id}/messages` |
| admin | GET | `/admin/stats` |
| admin | GET | `/admin/transactions` |
| admin | GET | `/admin/users` |
| admin | POST | `/admin/users/{user_id}/freeze` |
| admin | POST | `/admin/users/{user_id}/kyc` |
| admin | POST | `/admin/users/{user_id}/role` |
| system | GET | `/config` |
| system | GET | `/health` |

