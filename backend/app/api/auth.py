from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from backend.app.config import settings
from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.services.security import encrypt_api_key, decrypt_api_key, mask_api_key

router = APIRouter(prefix="/auth", tags=["Authentication"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)


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
    """Creates or returns the pre-configured demo developer account for 1-click access."""
    demo_email = "harsha.demo@codegraph.ai"
    user = db.query(User).filter(User.email == demo_email).first()
    if not user:
        user = User(
            id="usr-demo-777",
            email=demo_email,
            password_hash=pwd_context.hash("demopassword2026"),
            role="Lead Architect",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token({"sub": user.id, "email": user.email, "role": user.role})
    return AuthResponse(
        access_token=token,
        user=UserResponse(
            id=user.id,
            name="Harsha Vardhan (Demo Dev)",
            email=user.email,
            role=user.role,
            isDemo=True,
        ),
    )


@router.post("/register", response_model=AuthResponse)
def register_user(req: AuthRequest, db: Session = Depends(get_db)):
    """Registers a new developer account and issues a JWT token."""
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
def login_user(req: AuthRequest, db: Session = Depends(get_db)):
    """Authenticates standard credentials and issues a JWT token."""
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not pwd_context.verify(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    token = create_access_token({"sub": user.id, "email": user.email, "role": user.role})
    return AuthResponse(
        access_token=token,
        user=UserResponse(
            id=user.id,
            name=user.email.split("@")[0],
            email=user.email,
            role=user.role,
            isDemo=(user.email == "harsha.demo@codegraph.ai"),
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
):
    """Returns the masked status of the user's encrypted Gemini API key."""
    if not current_user or not current_user.gemini_key_encrypted:
        return GeminiKeyResponse(status="not_configured", configured=False, masked_key=None)
    raw = decrypt_api_key(current_user.gemini_key_encrypted)
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
