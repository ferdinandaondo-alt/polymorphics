# Backend (FastAPI)

The API: accounts, the escrow state machine, double-entry ledger, disputes, admin, and the auto-release job.
Full setup and deployment instructions are in `../DEPLOYMENT.md`; the quick version:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest                       # 34 pass, 3 skip on SQLite (the 3 race-condition tests need PostgreSQL)
uvicorn app.main:app --reload          # http://localhost:8000/docs
```

| File | Job |
|---|---|
| `app/models.py`, `app/enums.py` | Database tables |
| `app/state_machine.py` | The only place that decides which status changes are legal |
| `app/services.py` | All business rules (routers stay thin) |
| `app/ledger.py` | Double-entry, append-only; escrow returns to zero when a deal ends |
| `app/fees.py` | Integer-cent fee maths |
| `app/payments.py` | Payment provider interface + **mock** (swap for Stripe here) |
| `app/scheduler.py` | Background auto-release job |
| `app/routers/` | HTTP endpoints |
| `app/cli.py` | `init-db`, `set-role`, `verify-kyc`, `release-due` |
| `scripts/dump_fixtures.py` | Captures real API responses for the frontend tests |

Settings (environment variables): `DATABASE_URL`, `JWT_SECRET`, `ENVIRONMENT`, `PLATFORM_FEE_BPS`, `KYC_THRESHOLD`,
`DISPUTE_EVIDENCE_HOURS`, `AUTO_RELEASE_INTERVAL_SECONDS`, `CORS_ORIGINS`, `JWT_EXPIRE_MINUTES`.
