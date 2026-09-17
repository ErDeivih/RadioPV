import os
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from .config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, STREAM_TOKEN_EXPIRE_MINUTES
from .database import get_db
from . import models

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    return pwd.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd.verify(password, hashed)


def create_access_token(user_id: int, token_version: int) -> str:
    payload = {
        "sub": str(user_id),
        "ver": token_version,
        "scope": "access",
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_stream_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "scope": "stream",
        "exp": datetime.utcnow() + timedelta(minutes=STREAM_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_stream_token(t: str) -> int:
    """Valida un token de streaming y devuelve el user_id. Lanza 401 si es inválido."""
    creds = HTTPException(status.HTTP_401_UNAUTHORIZED, "Token de streaming inválido o caducado")
    try:
        payload = jwt.decode(t, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("scope") != "stream":
            raise creds
        return int(payload["sub"])
    except (JWTError, ValueError, KeyError):
        raise creds


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.User:
    creds = HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales inválidas",
                          headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # Rechazar tokens de streaming en endpoints de sesión (tolerar tokens antiguos sin scope)
        scope = payload.get("scope", "access")
        if scope != "access":
            raise creds
        user_id = int(payload.get("sub"))
        version = payload.get("ver", 0)
    except (JWTError, ValueError):
        raise creds
    user = db.get(models.User, user_id)
    if not user or user.token_version != version:
        raise creds
    return user
