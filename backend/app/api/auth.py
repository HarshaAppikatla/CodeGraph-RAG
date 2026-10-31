import secrets
import time
import logging
from collections import defaultdict
from threading import Lock
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from backend.app.config import settings
from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.services.security import (
    encrypt_api_key,
    decrypt_api_key,
    decrypt_api_key_with_status,
    mask_api_key,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

# Proxy-aware client IP extraction and rate limiter
_AUTH_RATE_LIMIT_LOCK = Lock()
_AUTH_IP_ATTEMPTS: dict = defaultdict(list)
_MAX_IP_ATTEMPTS = 10
_IP_WINDOW_SECONDS = 60

# Per-email lockout for protection against distributed credential-stuffing (Option D)
_FAILED_EMAIL_ATTEMPTS: dict = defaultdict(list)
_MAX_FAILED_EMAIL_ATTEMPTS = 5
_EMAIL_LOCKOUT_SECONDS = 15 * 60  # 15 minutes lockout


def _get_client_ip(request: Request) -> str:
    """Extracts client IP. Respects reverse proxies when uvicorn is configured with proxy-headers."""
    if request.client and request.client.host:
        return request.client.host
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # Use rightmost IP appended by nearest reverse proxy, never spoofable leftmost
        return forwarded.split(",")[-1].strip()
    return "127.0.0.1"


def _check_auth_ip_rate_limit(request: Request) -> None:
    """Sliding-window IP rate limiter with active pruning of stale entries."""
    client_ip = _get_client_ip(request)
    now = time.time()
    with _AUTH_RATE_LIMIT_LOCK:
        # Active prune of stale IPs to prevent memory leaks
        stale_ips = [ip for ip, timestamps in _AUTH_IP_ATTEMPTS.items() if not timestamps or now - timestamps[-1] >= _IP_WINDOW_SECONDS]
        for ip in stale_ips:
            del _AUTH_IP_ATTEMPTS[ip]

        timestamps = [t for t in _AUTH_IP_ATTEMPTS[client_ip] if now - t < _IP_WINDOW_SECONDS]
        if len(timestamps) >= _MAX_IP_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many authentication attempts from this IP. Please wait 1 minute before trying again.",
            )
        timestamps.append(now)
        _AUTH_IP_ATTEMPTS[client_ip] = timestamps


def _check_email_lockout(email: str) -> None:
    """Verifies that an account is not locked out due to repeated failed logins."""
    norm_email = email.strip().lower()
    now = time.time()
    with _AUTH_RATE_LIMIT_LOCK:
        # Prune stale lockout records
        stale_emails = [e for e, timestamps in _FAILED_EMAIL_ATTEMPTS.items() if not timestamps or now - timestamps[-1] >= _EMAIL_LOCKOUT_SECONDS]
        for e in stale_emails:
            del _FAILED_EMAIL_ATTEMPTS[e]

        failures = [t for t in _FAILED_EMAIL_ATTEMPTS[norm_email] if now - t < _EMAIL_LOCKOUT_SECONDS]
        if len(failures) >= _MAX_FAILED_EMAIL_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts for this account. Locked out for 15 minutes to protect your credentials.",
            )


def _record_failed_email_attempt(email: str) -> None:
    norm_email = email.strip().lower()
    now = time.time()
    with _AUTH_RATE_LIMIT_LOCK:
        failures = [t for t in _FAILED_EMAIL_ATTEMPTS[norm_email] if now - t < _EMAIL_LOCKOUT_SECONDS]
        failures.append(now)
        _FAILED_EMAIL_ATTEMPTS[norm_email] = failures


def _clear_failed_email_attempts(email: str) -> None:
    norm_email = email.strip().lower()
    with _AUTH_RATE_LIMIT_LOCK:
        _FAILED_EMAIL_ATTEMPTS.pop(norm_email, None)


def _cleanup_expired_demo_users(db: Session) -> None:
    """Lightweight prune of ephemeral demo visitors older than 24 hours to keep DB tidy."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        expired_users = (
            db.query(User)
            .filter(User.id.like("usr-demo-%"))
            .filter(User.id != "usr-demo-777")
            .filter(User.created_at < cutoff)
            .all()
        )
        for eu in expired_users:
            db.delete(eu)
        db.commit()
    except Exception as e:
        logger.debug("Demo user cleanup notice: %s", e)


def ensure_demo_user(db: Session) -> User:
    """Guarantees the existence of the demo user record to satisfy PostgreSQL foreign keys."""
    demo_email = "harsha.demo@codegraph.ai"
    user = db.query(User).filter((User.id == "usr-demo-777") | (User.email == demo_email)).first()
    if not user:
        random_secret = secrets.token_urlsafe(32)
        user = User(
            id="usr-demo-777",
            email=demo_email,
            password_hash=pwd_context.hash(random_secret),
            role="Lead Architect",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


class AuthRequest(BaseModel):
    email: EmailStr
    password: str
    role: Optional[str] = "Software Engineer"


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    isDemo: bool = False


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[User]:
    if not credentials:
        return None
    try:
        payload = jwt.decode(credentials.credentials, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            return None
        return db.query(User).filter((User.id == user_id) | (User.email == user_id)).first()
    except Exception:
        return None


@router.post("/demo", response_model=AuthResponse)
def login_demo(db: Session = Depends(get_db)):
    """Creates an isolated per-visitor demo developer session for 1-click evaluation."""
    _cleanup_expired_demo_users(db)

    visitor_suffix = secrets.token_hex(4)
    visitor_id = f"usr-demo-{visitor_suffix}"
    visitor_email = f"guest-{visitor_suffix}@codegraph.ai"
    visitor_name = f"Guest Dev ({visitor_suffix})"

    user = User(
        id=visitor_id,
        email=visitor_email,
        password_hash=pwd_context.hash(secrets.token_urlsafe(32)),
        role="Demo Developer",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": user.id, "email": user.email, "role": user.role})
    return AuthResponse(
        access_token=token,
        user=UserResponse(
            id=user.id,
            name=visitor_name,
            email=user.email,
            role=user.role,
            isDemo=True,
        ),
    )


@router.post("/register", response_model=AuthResponse)
def register_user(req: AuthRequest, request: Request, db: Session = Depends(get_db)):
    """Registers a new developer account and issues a JWT token."""
    _check_auth_ip_rate_limit(request)

    if not req.password or len(req.password.strip()) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters long.",
        )

    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Account with this email already exists.")

    new_user = User(
        email=req.email,
        password_hash=pwd_context.hash(req.password),
        role=req.role or "Software Engineer",
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token = create_access_token({"sub": new_user.id, "email": new_user.email, "role": new_user.role})
    return AuthResponse(
        access_token=token,
        user=UserResponse(
            id=new_user.id,
            name=new_user.email.split("@")[0],
            email=new_user.email,
            role=new_user.role,
            isDemo=False,
        ),
    )


@router.post("/login", response_model=AuthResponse)
def login_user(req: AuthRequest, request: Request, db: Session = Depends(get_db)):
    """Authenticates standard credentials and issues a JWT token."""
    _check_auth_ip_rate_limit(request)
    _check_email_lockout(req.email)

    user = db.query(User).filter(User.email == req.email).first()
    if not user or not pwd_context.verify(req.password, user.password_hash):
        _record_failed_email_attempt(req.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    _clear_failed_email_attempts(req.email)
    token = create_access_token({"sub": user.id, "email": user.email, "role": user.role})
    return AuthResponse(
        access_token=token,
        user=UserResponse(
            id=user.id,
            name=user.email.split("@")[0],
            email=user.email,
            role=user.role,
            isDemo=user.id.startswith("usr-demo-"),
        ),
    )


class GeminiKeyRequest(BaseModel):
    gemini_api_key: str


class GeminiKeyResponse(BaseModel):
    status: str
    configured: bool
    masked_key: Optional[str] = None


@router.post("/gemini-key", response_model=GeminiKeyResponse)
def save_user_gemini_key(
    req: GeminiKeyRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Securely encrypts and stores the user's Gemini API key in the database."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required to store API key.")
    raw = req.gemini_api_key.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Gemini API key cannot be empty.")
    encrypted = encrypt_api_key(raw)
    current_user.gemini_key_encrypted = encrypted
    db.commit()
    db.refresh(current_user)
    return GeminiKeyResponse(
        status="saved",
        configured=True,
        masked_key=mask_api_key(raw),
    )


@router.get("/gemini-key", response_model=GeminiKeyResponse)
def get_user_gemini_key(
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Returns the masked status of the user's encrypted Gemini API key."""
    if not current_user or not current_user.gemini_key_encrypted:
        return GeminiKeyResponse(status="not_configured", configured=False, masked_key=None)
    raw, was_legacy = decrypt_api_key_with_status(current_user.gemini_key_encrypted)
    if raw and was_legacy:
        current_user.gemini_key_encrypted = encrypt_api_key(raw)
        db.commit()
    return GeminiKeyResponse(
        status="configured",
        configured=bool(raw),
        masked_key=mask_api_key(raw),
    )


@router.delete("/gemini-key", response_model=GeminiKeyResponse)
def delete_user_gemini_key(
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Deletes the stored encrypted Gemini API key for the current user."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required.")
    current_user.gemini_key_encrypted = None
    db.commit()
    return GeminiKeyResponse(status="cleared", configured=False, masked_key=None)
