from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models, schemas
from ..security import (hash_password, verify_password, create_access_token,
                        create_stream_token, get_current_user)
from ..config import STREAM_TOKEN_EXPIRE_MINUTES
from .. import config as _config

router = APIRouter(prefix="/auth", tags=["auth"])

# Límite de intentos de login (DP-06): por email+IP, ventana de 5 min, 5 fallos → bloqueo temporal.
_LOGIN_WINDOW = timedelta(minutes=5)
_LOGIN_MAX_FAILS = 5
_login_attempts: dict[str, tuple[int, datetime]] = {}


def _login_key(email: str, request: Request) -> str:
    ip = request.client.host if request.client else "?"
    return f"{email.lower()}|{ip}"


def _check_login_limit(email: str, request: Request) -> None:
    key = _login_key(email, request)
    fails, last = _login_attempts.get(key, (0, datetime.min))
    if fails >= _LOGIN_MAX_FAILS and (datetime.utcnow() - last) < _LOGIN_WINDOW:
        raise HTTPException(429, "Demasiados intentos. Espera unos minutos.")


def _record_login_fail(email: str, request: Request) -> None:
    key = _login_key(email, request)
    fails, last = _login_attempts.get(key, (0, datetime.min))
    _login_attempts[key] = (fails + 1, datetime.utcnow())


def _reset_login_fail(email: str, request: Request) -> None:
    _login_attempts.pop(_login_key(email, request), None)


@router.post("/register", response_model=schemas.TokenOut)
def register(data: schemas.RegisterIn, db: Session = Depends(get_db)):
    invite = _config.INVITE_CODE
    if invite and data.invite_code != invite:
        raise HTTPException(403, "Código de invitación inválido")
    if db.query(models.User).filter(models.User.email == data.email.lower()).first():
        raise HTTPException(400, "Email ya registrado")
    user = models.User(email=data.email.lower(),
                       hashed_password=hash_password(data.password),
                       display_name=data.display_name or data.email.split("@")[0])
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"access_token": create_access_token(user.id, user.token_version), "user": user}


@router.post("/login", response_model=schemas.TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db),
          request: Request = None):
    _check_login_limit(form.username, request)
    user = db.query(models.User).filter(models.User.email == form.username.lower()).first()
    if not user or not verify_password(form.password, user.hashed_password):
        _record_login_fail(form.username, request)
        raise HTTPException(401, "Credenciales inválidas")
    _reset_login_fail(form.username, request)
    user.last_login = datetime.utcnow()
    db.commit()
    return {"access_token": create_access_token(user.id, user.token_version), "user": user}


@router.get("/me", response_model=schemas.UserOut)
def me(current: models.User = Depends(get_current_user)):
    return current


@router.patch("/me", response_model=schemas.UserOut)
def update_me(data: schemas.UserPatchIn, current: models.User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    """Perfil editable (D3): cambiar el nombre visible (y, opcional, el email)."""
    if data.display_name is not None and data.display_name.strip():
        current.display_name = data.display_name.strip()
    if data.email is not None and data.email.strip():
        if data.email.strip().lower() != current.email:
            if db.query(models.User).filter(models.User.email == data.email.strip().lower()).first():
                raise HTTPException(400, "Email ya registrado")
            current.email = data.email.strip().lower()
    db.commit()
    db.refresh(current)
    return current


@router.post("/logout")
def logout(current: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    current.token_version += 1
    db.commit()
    return {"ok": True}


@router.post("/stream-token")
def stream_token(current: models.User = Depends(get_current_user)):
    """Token corto de streaming (30 min) para que el <audio> se autentique por URL."""
    return {"token": create_stream_token(current.id),
            "expires_in": STREAM_TOKEN_EXPIRE_MINUTES * 60}
