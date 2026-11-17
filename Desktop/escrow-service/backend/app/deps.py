import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.security import decode_token

bearer = HTTPBearer()


def get_current_user(creds: HTTPAuthorizationCredentials = Depends(bearer),
                     db: Session = Depends(get_db)) -> models.User:
    try:
        user_id = decode_token(creds.credentials)["sub"]
    except (jwt.PyJWTError, KeyError):
        raise HTTPException(401, "Invalid or expired token")
    user = db.get(models.User, user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "Invalid or expired token")
    return user
