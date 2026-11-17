"""Tiny admin CLI.  Usage:  python -m app.cli set-role someone@example.com arbiter"""
import sys

from sqlalchemy import select

from app import models
from app.database import Base, SessionLocal, engine
from app.enums import AccountRole, KYCStatus


def main(argv):
    Base.metadata.create_all(engine)
    if len(argv) == 2 and argv[1] == "init-db":
        print("Tables are ready.")      # create_all() above already did the work
    elif len(argv) == 2 and argv[1] == "release-due":
        from app.scheduler import run_auto_release_once
        released = run_auto_release_once()
        print(f"Released {len(released)} overdue transaction(s)." + (" " + ", ".join(released) if released else ""))
    elif len(argv) == 4 and argv[1] == "set-role":
        role = AccountRole(argv[3])
        with SessionLocal() as db:
            user = db.execute(select(models.User).where(models.User.email == argv[2].lower())).scalar_one_or_none()
            if not user:
                sys.exit(f"No user {argv[2]}")
            user.role = role
            db.commit()
            print(f"{user.email} is now {role.value}")
    elif len(argv) == 3 and argv[1] == "verify-kyc":
        with SessionLocal() as db:
            user = db.execute(select(models.User).where(models.User.email == argv[2].lower())).scalar_one_or_none()
            if not user:
                sys.exit(f"No user {argv[2]}")
            user.kyc_status = KYCStatus.VERIFIED
            db.commit()
            print(f"{user.email} KYC marked verified (dev shortcut)")
    else:
        sys.exit("usage: python -m app.cli init-db\n       python -m app.cli release-due\n       python -m app.cli set-role <email> <user|arbiter|admin>\n       python -m app.cli verify-kyc <email>")


if __name__ == "__main__":
    main(sys.argv)
