import base64
import hashlib
import json
import logging
from typing import Optional, Dict, Any, Tuple
from cryptography.fernet import Fernet
from backend.app.config import settings

logger = logging.getLogger("codegraph.security")


def _get_cipher() -> Fernet:
    """Derives a deterministic 32-byte Fernet key from the application encryption key.
    Prefers ENCRYPTION_KEY if provided to decouple key encryption from JWT_SECRET rotation.
    """
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


def decrypt_api_key_with_status(ciphertext: Optional[str]) -> Tuple[Optional[str], bool]:
    """Decrypts ciphertext back into the plaintext API key.
    Returns (plaintext, was_legacy).
    was_legacy is True if decryption succeeded using a fallback key and needs re-encryption.
    """
    if not ciphertext or not ciphertext.strip():
        return None, False
    token_bytes = ciphertext.strip().encode("utf-8")

    # 1. Try primary cipher
    try:
        return _get_cipher().decrypt(token_bytes).decode("utf-8"), False
    except Exception:
        pass

    # 2. If ENCRYPTION_KEY is distinct from JWT_SECRET, try JWT_SECRET with salt
    enc_key = getattr(settings, "ENCRYPTION_KEY", None)
    if enc_key and enc_key != settings.JWT_SECRET:
        try:
            derived = hashlib.sha256(f"fernet-vault-salt:{settings.JWT_SECRET}".encode("utf-8")).digest()
            return Fernet(base64.urlsafe_b64encode(derived)).decrypt(token_bytes).decode("utf-8"), True
        except Exception:
            pass

    # 3. Try raw keys without salt (for transition compatibility)
    candidates = [enc_key, settings.JWT_SECRET] if enc_key else [settings.JWT_SECRET]
    for raw in candidates:
        if raw:
            try:
                key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode("utf-8")).digest())
                return Fernet(key).decrypt(token_bytes).decode("utf-8"), True
            except Exception:
                pass

    # 4. Try known legacy public keys from git history for migration
    for legacy_secret in [
        "codegraph-rag-secret-key-2026-production-v2",
        "codegraph-rag-secret-key-2026",
    ]:
        try:
            key = base64.urlsafe_b64encode(hashlib.sha256(legacy_secret.encode("utf-8")).digest())
            return Fernet(key).decrypt(token_bytes).decode("utf-8"), True
        except Exception:
            pass

    return None, False


def decrypt_api_key(ciphertext: Optional[str]) -> Optional[str]:
    """Decrypts ciphertext back into the plaintext API key."""
    plaintext, _ = decrypt_api_key_with_status(ciphertext)
    return plaintext


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


def decrypt_provider_keys_with_status(ciphertext: Optional[str]) -> Tuple[Dict[str, str], bool]:
    """Decrypts ciphertext into a dictionary of provider keys.
    Returns (keys_dict, was_legacy).
    """
    if not ciphertext or not ciphertext.strip():
        return {}, False
    decrypted_str, was_legacy = decrypt_api_key_with_status(ciphertext)
    if not decrypted_str:
        return {}, False
    try:
        data = json.loads(decrypted_str)
        if isinstance(data, dict):
            return data, was_legacy
    except Exception:
        pass
    return {}, False


def decrypt_provider_keys(ciphertext: Optional[str]) -> Dict[str, str]:
    """Decrypts ciphertext into a dictionary of provider keys."""
    data, _ = decrypt_provider_keys_with_status(ciphertext)
    return data


def get_user_encrypted_keys(user: Optional[Any] = None, user_id: Optional[str] = None) -> Dict[str, str]:
    """Retrieves and decrypts all provider API keys strictly for the specified user,
    transparently re-encrypting legacy ciphertexts with the primary ENCRYPTION_KEY on read.
    """
    keys: Dict[str, str] = {}
    target_user = user
    db = None
    needs_db_close = False

    if not target_user:
        # If no explicit user object or user_id provided, NEVER fall back to another user
        if not user_id or user_id in ("default", "anonymous", ""):
            return {}
        try:
            from backend.app.database import SessionLocal
            from backend.app.models.user import User
            db = SessionLocal()
            needs_db_close = True
            target_user = db.query(User).filter((User.id == user_id) | (User.email == user_id)).first()
            if not target_user:
                db.close()
                return {}
        except Exception:
            if db:
                db.close()
            return {}
    else:
        try:
            from sqlalchemy.orm import object_session
            db = object_session(target_user)
        except Exception:
            db = None

    try:
        dirty = False

        # 1. Decrypt bundled keys
        bundled_raw = getattr(target_user, "provider_keys_encrypted", None)
        if bundled_raw:
            bundle_dict, was_legacy = decrypt_provider_keys_with_status(bundled_raw)
            if bundle_dict:
                keys.update(bundle_dict)
                if was_legacy:
                    target_user.provider_keys_encrypted = encrypt_provider_keys(bundle_dict)
                    dirty = True

        # 2. Decrypt dedicated provider columns
        for prov, col_name in [
            ("gemini", "gemini_key_encrypted"),
            ("openai", "openai_key_encrypted"),
            ("anthropic", "anthropic_key_encrypted"),
            ("deepseek", "deepseek_key_encrypted"),
            ("groq", "groq_key_encrypted"),
        ]:
            val = getattr(target_user, col_name, None)
            if val:
                decrypted, was_legacy = decrypt_api_key_with_status(val)
                if decrypted:
                    if not keys.get(prov):
                        keys[prov] = decrypted
                    if was_legacy:
                        setattr(target_user, col_name, encrypt_api_key(decrypted))
                        dirty = True

        # 3. If any legacy ciphertexts were upgraded, persist immediately
        if dirty:
            if db:
                try:
                    db.commit()
                    logger.info("Migrated & re-encrypted stored credentials for user %s with primary key", getattr(target_user, "id", "unknown"))
                except Exception as e:
                    logger.warning("Failed to commit re-encrypted keys on read: %s", e)
            else:
                try:
                    from backend.app.database import SessionLocal
                    from backend.app.models.user import User
                    with SessionLocal() as commit_db:
                        u = commit_db.query(User).filter(User.id == target_user.id).first()
                        if u:
                            u.provider_keys_encrypted = target_user.provider_keys_encrypted
                            u.gemini_key_encrypted = target_user.gemini_key_encrypted
                            u.openai_key_encrypted = target_user.openai_key_encrypted
                            u.anthropic_key_encrypted = target_user.anthropic_key_encrypted
                            u.deepseek_key_encrypted = target_user.deepseek_key_encrypted
                            u.groq_key_encrypted = target_user.groq_key_encrypted
                            commit_db.commit()
                            logger.info("Persisted re-encrypted credentials for user %s", target_user.id)
                except Exception as e:
                    logger.warning("Failed to persist re-encrypted credentials: %s", e)

        return keys
    finally:
        if needs_db_close and db:
            try:
                db.close()
            except Exception:
                pass
