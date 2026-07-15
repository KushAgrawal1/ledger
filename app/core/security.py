from datetime import datetime, timedelta, timezone
from typing import Any, Union
from jose import jwt
from passlib.context import CryptContext

# CryptContext configuration using standard bcrypt scheme
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Production note: In a real environment, load these configurations from env variables
JWT_SECRET = "super-secret-ledger-signing-key-do-not-leak"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(subject: Union[str, Any], role: str, expires_delta: timedelta = None) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Token payloads include 'sub' for owner identification and custom 'role' claim for RBAC
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "role": role
    }
    return jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)