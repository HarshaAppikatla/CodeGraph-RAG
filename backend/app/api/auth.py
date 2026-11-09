import secrets
import time
import ipaddress
import logging
from collections import defaultdict
from threading import Lock
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from backend.app.config import settings
from backend.app.database import get_db
from backend.app.models.user import User, is_demo_user
from backend.app.services.security import (
    encrypt_api_key,
    decrypt_api_key,
    decrypt_api_key_with_status,
    mask_api_key,
)

logger = logging.getLogger("codegraph.auth")
router = APIRouter(prefix="/auth", tags=["Authentication"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

# Pre-hash a single secret at startup and reuse for all ephemeral guest users.
# Eliminates expensive 250ms bcrypt hashing on 0.1 vCPU per guest login.
_PREHASHED_DEMO_PASSWORD: str = pwd_context.hash(secrets.token_urlsafe(32))

MAX_LIVE_GUEST_USERS = 200

# Private IP CIDRs for walking X-Forwarded-For securely
PRIVATE_CIDRS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_private_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str.strip())
        return any(ip in cidr for cidr in PRIVATE_CIDRS)
    except ValueError:
        return False


def _get_client_ip(request: Request) -> str:
    """Extracts client IP. Uses verified edge headers (CF-Connecting-IP, True-Client-IP)
    enforced by Cloudflare and Render's ingress to prevent client spoofing.
    """
    # 1. Cloudflare & Render edge connecting headers (verified immune to client forgery)
    for edge_header in ("cf-connecting-ip", "true-client-ip"):
        val = request.headers.get(edge_header)
        if val and not _is_private_ip(val):
            return val.strip()

    # 2. Walk X-Forwarded-For from right to left (Render's proxy appends the real caller IP at the end)
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        for hop in reversed(hops):
            if not _is_private_ip(hop):
                return hop
        if hops:
            return hops[-1]

    # 3. Connection client host
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


# Sliding window IP rate limiter
_AUTH_RATE_LIMIT_LOCK = Lock()
_AUTH_IP_ATTEMPTS: dict = defaultdict(list)
_MAX_IP_ATTEMPTS = 10
_IP_WINDOW_SECONDS = 60

# Per (email, IP) lockout to prevent abusive third-party account lockout (Item 4)
_FAILED_EMAIL_IP_ATTEMPTS: dict = defaultdict(list)
_MAX_FAILED_EMAIL_IP_ATTEMPTS = 5
_EMAIL_LOCKOUT_SECONDS = 15 * 60  # 15 minutes lockout


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


def _check_email_ip_lockout(email: str, client_ip: str) -> None:
    """Verifies that the (email, IP) pair is not locked out due to repeated failed logins."""
    key = (email.strip().lower(), client_ip)
    now = time.time()
    with _AUTH_RATE_LIMIT_LOCK:
        stale_keys = [k for k, timestamps in _FAILED_EMAIL_IP_ATTEMPTS.items() if not timestamps or now - timestamps[-1] >= _EMAIL_LOCKOUT_SECONDS]
        for k in stale_keys:
            del _FAILED_EMAIL_IP_ATTEMPTS[k]

        failures = [t for t in _FAILED_EMAIL_IP_ATTEMPTS[key] if now - t < _EMAIL_LOCKOUT_SECONDS]
        if len(failures) >= _MAX_FAILED_EMAIL_IP_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts for this account from your IP. Locked out for 15 minutes.",
            )


def _record_failed_email_attempt(email: str, client_ip: str) -> None:
    key = (email.strip().lower(), client_ip)
    now = time.time()
    with _AUTH_RATE_LIMIT_LOCK:
        failures = [t for t in _FAILED_EMAIL_IP_ATTEMPTS[key] if now - t < _EMAIL_LOCKOUT_SECONDS]
        failures.append(now)
        _FAILED_EMAIL_IP_ATTEMPTS[key] = failures


def _clear_failed_email_attempts(email: str, client_ip: str) -> None:
    key = (email.strip().lower(), client_ip)
    with _AUTH_RATE_LIMIT_LOCK:
        _FAILED_EMAIL_IP_ATTEMPTS.pop(key, None)


def _cleanup_expired_guests_task(user_ids: List[str]) -> None:
    """Background task purging Qdrant vectors, Neo4j nodes, and DB records for expired guests (Item 3)."""
    if not user_ids:
        return
    try:
        from backend.app.database import SessionLocal
        from backend.app.models.workspace import Workspace
        from backend.app.services.registry import get_vector_store, get_graph_store

        gs = get_graph_store()
        vs = get_vector_store()

        with SessionLocal() as db:
            for uid in user_ids:
                try:
                    workspaces = db.query(Workspace).filter(Workspace.user_id == uid).all()
                    for ws in workspaces:
                        if gs:
                            try:
                                gs.delete_workspace(ws.id)
                            except Exception as ge:
                                logger.warning("Failed to purge Neo4j for guest ws %s: %s", ws.id, ge)
                        if vs:
                            try:
                                vs.delete_workspace(ws.id)
                            except Exception as ve:
                                logger.warning("Failed to purge Qdrant for guest ws %s: %s", ws.id, ve)

                    user = db.query(User).filter(User.id == uid).first()
                    if user:
                        db.delete(user)
                    db.commit()
                except Exception as ue:
                    db.rollback()
                    logger.warning("Error purging guest user %s: %s", uid, ue)
    except Exception as e:
        logger.error("Guest cleanup background task error: %s", e)


def ensure_demo_user(db: Session) -> User:
    """Guarantees the existence of the base demo user record to satisfy PostgreSQL foreign keys."""
    demo_email = "harsha.demo@codegraph.ai"
    user = db.query(User).filter((User.id == "usr-demo-777") | (User.email == demo_email)).first()
    if not user:
        user = User(
            id="usr-demo-777",
            email=demo_email,
            password_hash=_PREHASHED_DEMO_PASSWORD,
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


@router.get("/me", response_model=AuthResponse)
def get_current_user_profile(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
):
    """Restores the current user session from their existing JWT token."""
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        user = db.query(User).filter((User.id == user_id) | (User.email == user_id)).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        is_demo = is_demo_user(user)
        name = f"Guest Dev ({user.id.replace('usr-demo-', '')})" if is_demo else user.email.split("@")[0]
        token = create_access_token({"sub": user.id, "email": user.email, "role": user.role})
        return AuthResponse(
            access_token=token,
            user=UserResponse(
                id=user.id,
                name=name,
                email=user.email,
                role=user.role,
                isDemo=is_demo,
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Token validation failed: {e}")


@router.post("/demo", response_model=AuthResponse)
def login_demo(
    request: Request,
    background_tasks: BackgroundTasks,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
):
    """Creates an isolated per-visitor demo developer session with capped guests and zero CPU hashing."""
    # If client already has a valid demo session token, preserve their account across page reloads
    if credentials:
        try:
            payload = jwt.decode(credentials.credentials, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
            user_id = payload.get("sub")
            if user_id:
                existing_user = db.query(User).filter(User.id == user_id).first()
                if existing_user and is_demo_user(existing_user):
                    token = create_access_token({"sub": existing_user.id, "email": existing_user.email, "role": existing_user.role})
                    suffix = existing_user.id.replace("usr-demo-", "")
                    return AuthResponse(
                        access_token=token,
                        user=UserResponse(
                            id=existing_user.id,
                            name=f"Guest Dev ({suffix})",
                            email=existing_user.email,
                            role=existing_user.role,
                            isDemo=True,
                        ),
                    )
        except Exception:
            pass

    _check_auth_ip_rate_limit(request)

    # Check for expired guests (> 24 hours) or if guest count exceeds MAX_LIVE_GUEST_USERS
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    expired_uids = [
        u[0] for u in db.query(User.id)
        .filter(User.id.like("usr-demo-%"), User.id != "usr-demo-777", User.created_at < cutoff)
        .all()
    ]

    live_guest_count = db.query(User).filter(User.id.like("usr-demo-%"), User.id != "usr-demo-777").count()
    if live_guest_count >= MAX_LIVE_GUEST_USERS:
        oldest_uids = [
            u[0] for u in db.query(User.id)
            .filter(User.id.like("usr-demo-%"), User.id != "usr-demo-777")
            .order_by(User.created_at.asc())
            .limit(50)
            .all()
        ]
        expired_uids.extend(oldest_uids)

    if expired_uids:
        background_tasks.add_task(_cleanup_expired_guests_task, list(set(expired_uids)))

    visitor_suffix = secrets.token_hex(4)
    visitor_id = f"usr-demo-{visitor_suffix}"
    visitor_email = f"guest-{visitor_suffix}@codegraph.ai"
    visitor_name = f"Guest Dev ({visitor_suffix})"

    user = User(
        id=visitor_id,
        email=visitor_email,
        password_hash=_PREHASHED_DEMO_PASSWORD,
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
    normalized_email = (req.email or "").strip().lower()

    if normalized_email.endswith("@codegraph.ai"):
        raise HTTPException(
            status_code=400,
            detail="The @codegraph.ai domain is reserved for internal system accounts.",
        )

    if not req.password or len(req.password.strip()) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters long.",
        )

    existing = db.query(User).filter(User.email == normalized_email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Account with this email already exists.")

    new_user = User(
        email=normalized_email,
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
    client_ip = _get_client_ip(request)
    normalized_email = (req.email or "").strip().lower()
    _check_auth_ip_rate_limit(request)
    _check_email_ip_lockout(normalized_email, client_ip)

    user = db.query(User).filter(User.email == normalized_email).first()
    if not user or not pwd_context.verify(req.password, user.password_hash):
        _record_failed_email_attempt(normalized_email, client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    _clear_failed_email_attempts(normalized_email, client_ip)
    token = create_access_token({"sub": user.id, "email": user.email, "role": user.role})
    return AuthResponse(
        access_token=token,
        user=UserResponse(
            id=user.id,
            name=user.email.split("@")[0],
            email=user.email,
            role=user.role,
            isDemo=is_demo_user(user),
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
