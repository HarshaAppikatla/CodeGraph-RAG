import base64
import hashlib
import json
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet
from backend.app.config import settings


def _get_cipher() -> Fernet:
    """Derives a deterministic 32-byte Fernet key from the application encryption key."""
    raw_secret = getattr(settings, "ENCRYPTION_KEY", None) or settings.JWT_SECRET
    derived = hashlib.sha256(f"fernet-vault-salt:{raw_secret}".encode("utf-8")).digest()
    url_safe_key = base64.urlsafe_b64encode(derived)
    return Fernet(url_safe_key)


def encrypt_api_key(raw_key: str) -> Optional[str]:
    """Encrypts raw API key into authenticated ciphertext using Fernet (AES-128-CBC + HMAC)."""
    if not raw_key or not raw_key.strip():
        return None
    cipher = _get_cipher()
    encrypted = cipher.encrypt(raw_key.strip().encode("utf-8"))
    return encrypted.decode("utf-8")


def decrypt_api_key(ciphertext: Optional[str]) -> Optional[str]:
    """Decrypts ciphertext back into the plaintext API key."""
    if not ciphertext or not ciphertext.strip():
        return None
    token_bytes = ciphertext.strip().encode("utf-8")
    
    # 1. Try primary cipher
    try:
        return _get_cipher().decrypt(token_bytes).decode("utf-8")
    except Exception:
        pass

    # 2. Try raw JWT_SECRET without salt (for transition compatibility)
    try:
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.JWT_SECRET.encode("utf-8")).digest())
        return Fernet(key).decrypt(token_bytes).decode("utf-8")
    except Exception:
        pass

    # 3. Try legacy secret keys for seamless backward compatibility with existing DB records
    for legacy_secret in [
        "codegraph-rag-secret-key-2026-production-v2",
        "codegraph-rag-secret-key-2026"
    ]:
        try:
            key = base64.urlsafe_b64encode(hashlib.sha256(legacy_secret.encode("utf-8")).digest())
            return Fernet(key).decrypt(token_bytes).decode("utf-8")
        except Exception:
            pass
    return None


def mask_api_key(raw_key: Optional[str]) -> Optional[str]:
    """Masks API key for safe UI display (e.g. AIzaSy****...5f2a)."""
    if not raw_key:
        return None
    cleaned = raw_key.strip()
    if len(cleaned) <= 10:
        return "****"
    return f"{cleaned[:6]}...{cleaned[-4:]}"


def encrypt_provider_keys(keys_dict: Dict[str, str]) -> Optional[str]:
    """Encrypts a dictionary of provider keys into authenticated ciphertext using AES-128-CBC."""
    if not keys_dict:
        return None
    raw_json = json.dumps(keys_dict)
    return encrypt_api_key(raw_json)


def decrypt_provider_keys(ciphertext: Optional[str]) -> Dict[str, str]:
    """Decrypts ciphertext into a dictionary of provider keys."""
    if not ciphertext or not ciphertext.strip():
        return {}
    decrypted_str = decrypt_api_key(ciphertext)
    if not decrypted_str:
        return {}
    try:
        data = json.loads(decrypted_str)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def get_user_encrypted_keys(user: Optional[Any] = None, user_id: Optional[str] = None) -> Dict[str, str]:
    """Retrieves and decrypts all provider API keys strictly for the specified user."""
    keys: Dict[str, str] = {}

    target_user = user
    if not target_user:
        # If no explicit user object or user_id provided, NEVER fall back to another user
        if not user_id or user_id in ("default", "anonymous", ""):
            return {}
        try:
            from backend.app.database import SessionLocal
            from backend.app.models.user import User
            with SessionLocal() as db:
                target_user = db.query(User).filter((User.id == user_id) | (User.email == user_id)).first()
                if not target_user:
                    return {}
                # Extract and decrypt keys while DB session is open
                target_dict = {
                    "gemini": decrypt_api_key(getattr(target_user, "gemini_key_encrypted", None)),
                    "openai": decrypt_api_key(getattr(target_user, "openai_key_encrypted", None)),
                    "anthropic": decrypt_api_key(getattr(target_user, "anthropic_key_encrypted", None)),
                    "deepseek": decrypt_api_key(getattr(target_user, "deepseek_key_encrypted", None)),
                    "groq": decrypt_api_key(getattr(target_user, "groq_key_encrypted", None)),
                    "bundle": decrypt_provider_keys(getattr(target_user, "provider_keys_encrypted", None)),
                }
                if target_dict["bundle"]:
                    keys.update(target_dict["bundle"])
                for prov in ["gemini", "openai", "anthropic", "deepseek", "groq"]:
                    if target_dict[prov] and not keys.get(prov):
                        keys[prov] = target_dict[prov]
                return keys
        except Exception:
            return {}

    if target_user:
        # 1. Unbundle JSON payload if present
        bundled = decrypt_provider_keys(getattr(target_user, "provider_keys_encrypted", None))
        if bundled:
            keys.update(bundled)

        # 2. Check dedicated provider columns
        for prov, col_name in [
            ("gemini", "gemini_key_encrypted"),
            ("openai", "openai_key_encrypted"),
            ("anthropic", "anthropic_key_encrypted"),
            ("deepseek", "deepseek_key_encrypted"),
            ("groq", "groq_key_encrypted"),
        ]:
            val = getattr(target_user, col_name, None)
            if val and not keys.get(prov):
                decrypted = decrypt_api_key(val)
                if decrypted:
                    keys[prov] = decrypted

    return keys
