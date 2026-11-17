import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config, models  # noqa: F401  (models registers tables on Base.metadata)
from app.database import Base, engine
from app.routers import admin, auth, disputes, transactions
from app.scheduler import auto_release_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    if config.ENVIRONMENT == "production" and (config.JWT_SECRET == "dev-secret-change-me" or len(config.JWT_SECRET) < 32):
        raise RuntimeError("Refusing to start: set JWT_SECRET to a random string of at least 32 characters")
    Base.metadata.create_all(engine)   # dev convenience; switch to Alembic migrations before real data
    task = asyncio.create_task(auto_release_loop(config.AUTO_RELEASE_INTERVAL)) if config.AUTO_RELEASE_INTERVAL > 0 else None
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


_prod = config.ENVIRONMENT == "production"
# In production the interactive API docs and schema are switched off (less to probe).
app = FastAPI(title="Escrow Service API", version="0.2.0", lifespan=lifespan,
              docs_url=None if _prod else "/docs", redoc_url=None if _prod else "/redoc",
              openapi_url=None if _prod else "/openapi.json")
if config.CORS_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth.router)
app.include_router(transactions.router)
app.include_router(disputes.router)
app.include_router(admin.router)


@app.get("/config")
def public_config():
    """Non-secret settings the UI needs (so its fee preview always matches the server)."""
    return {"platform_fee_bps": config.PLATFORM_FEE_BPS, "kyc_threshold": config.KYC_THRESHOLD,
            "dispute_evidence_hours": config.DISPUTE_EVIDENCE_HOURS}


@app.get("/health")
def health():
    return {"status": "ok"}
