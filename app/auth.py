import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from . import models, database, schemas

SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_urlsafe(48)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_csrf_token(access_token: str) -> str:
    return hmac.new(
        SECRET_KEY.encode(), access_token.encode(), hashlib.sha256
    ).hexdigest()


def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    cookie_token: Optional[str] = Cookie(default=None, alias="access_token"),
    csrf_token: Optional[str] = Header(default=None, alias="X-CSRF-Token"),
    db: Session = Depends(database.get_db),
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    cookie_authentication = not token and cookie_token is not None
    token = token or cookie_token
    if token is None:
        raise credentials_exception
    if cookie_authentication and request.method not in {"GET", "HEAD", "OPTIONS"}:
        expected_csrf_token = create_csrf_token(token)
        if csrf_token is None or not hmac.compare_digest(
            csrf_token, expected_csrf_token
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token missing or invalid",
            )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = schemas.TokenData(email=email)
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.email == token_data.email).first()
    if user is None:
        raise credentials_exception
    return user