"""Settings. Everything sensitive or tunable comes from the environment."""
import os

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")  # MUST be overridden in production
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))

PLATFORM_FEE_BPS = int(os.environ.get("PLATFORM_FEE_BPS", "250"))   # 250 basis points = 2.5%
KYC_THRESHOLD = int(os.environ.get("KYC_THRESHOLD", "100000"))      # minor units; above this, KYC is required
DISPUTE_EVIDENCE_HOURS = int(os.environ.get("DISPUTE_EVIDENCE_HOURS", "72"))

ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")          # set to "production" when deployed
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]  
AUTO_RELEASE_INTERVAL = int(os.environ.get("AUTO_RELEASE_INTERVAL_SECONDS", "60"))  
