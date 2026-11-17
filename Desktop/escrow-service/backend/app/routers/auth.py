from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.deps import get_current_user
from app.schemas import LoginIn, RegisterIn, TokenOut, UserOut
from app.security import create_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    email = data.email.lower()
    if db.execute(select(models.User.id).where(models.User.email == email)).first():
        raise HTTPException(409, "An account with that email already exists")
    user = models.User(email=email, password_hash=hash_password(data.password), full_name=data.full_name)
    db.add(user)
    db.commit()
    return user


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.execute(select(models.User).where(models.User.email == data.email.lower())).scalar_one_or_none()
    if not user or not user.is_active or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")   # same message either way
    return TokenOut(access_token=create_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: models.User = Depends(get_current_user)):
    return user
