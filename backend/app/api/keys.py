import os
import time
import logging
from typing import Optional, Dict, Any, Union, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.database import get_db, SessionLocal
from backend.app.models.user import User
from backend.app.api.auth import get_current_user_optional
from backend.app.services.security import (
    encrypt_api_key,
    decrypt_api_key,
    mask_api_key,
    get_user_encrypted_keys,
    encrypt_provider_keys,
    decrypt_provider_keys,
)

logger = logging.getLogger("codegraph.keys")
router = APIRouter(prefix="/keys", tags=["Key Vault & Multi-Provider Credentials"])

SUPPORTED_PROVIDERS = ["gemini", "openai", "anthropic", "deepseek", "groq"]
ENV_MAP = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "groq": "GROQ_API_KEY",
}


def _is_valid_provider_key(prov: str, key_val: Optional[str]) -> bool:
    """Validates structural key prefix to guard against cross-provider key contamination."""
    if not key_val or len(key_val.strip()) < 10:
        return False
    val = key_val.strip()
    if prov == "gemini":
        return val.startswith("AIzaSy") or len(val) >= 20
    if prov == "openai":
        return val.startswith("sk-")
    if prov == "anthropic":
        return val.startswith("sk-ant-")
    if prov == "groq":
        return val.startswith("gsk_")
    if prov == "deepseek":
        return val.startswith("sk-") or len(val) >= 20
    return len(val) > 10


def _compute_status_map(existing_keys: Dict[str, str]) -> Dict[str, bool]:
    """Computes whether each provider has a valid key configured in DB or environment."""
    status_map = {}
    for prov in SUPPORTED_PROVIDERS:
        key_val = existing_keys.get(prov)
        if not key_val:
            env_var = ENV_MAP.get(prov, "")
            key_val = os.getenv(env_var, "").strip() if env_var else ""
        if prov == "gemini" and not key_val and settings.GEMINI_API_KEY:
            key_val = settings.GEMINI_API_KEY.strip()
        status_map[prov] = _is_valid_provider_key(prov, key_val)
    return status_map


# Baseline curated production models (used as defaults or when offline)
DEFAULT_CURATED_MODELS = [
    {
        "id": "gemini-2.0-flash",
        "name": "Gemini 2.0 Flash",
        "provider": "gemini",
        "tier": "Fast Reasoning",
        "description": "Next-gen multimodal, low latency & thinking capabilities",
        "recommended": True,
        "active": True,
    },
    {
        "id": "gemini-2.5-flash",
        "name": "Gemini 2.5 Flash",
        "provider": "gemini",
        "tier": "Production",
        "description": "Optimal latency-to-quality ratio for codebase analysis",
        "active": True,
    },
    {
        "id": "gemini-1.5-pro",
        "name": "Gemini 1.5 Pro",
        "provider": "gemini",
        "tier": "Deep Pro",
        "description": "Extended context window for comprehensive multi-file ASTs",
        "active": True,
    },
    {
        "id": "claude-3-7-sonnet",
        "name": "Claude 3.7 Sonnet",
        "provider": "anthropic",
        "tier": "Hybrid Thinking",
        "description": "State-of-the-art code refactoring and hybrid reasoning",
        "active": False,
    },
    {
        "id": "claude-3-5-sonnet",
        "name": "Claude 3.5 Sonnet",
        "provider": "anthropic",
        "tier": "Coding Expert",
        "description": "Industry benchmark for precise syntax and diff generation",
        "active": False,
    },
    {
        "id": "gpt-4o",
        "name": "GPT-4o",
        "provider": "openai",
        "tier": "Flagship",
        "description": "High-speed reasoning across complex dependency graphs",
        "active": False,
    },
    {
        "id": "o3-mini",
        "name": "o3-mini",
        "provider": "openai",
        "tier": "Reasoning",
        "description": "STEM & code specialized reasoning engine",
        "active": False,
    },
    {
        "id": "deepseek-r1",
        "name": "DeepSeek R1",
        "provider": "deepseek",
        "tier": "Open Reasoning",
        "description": "Open-weights reasoning model with chain-of-thought insights",
        "active": False,
    },
    {
        "id": "groq/openai/gpt-oss-120b",
        "name": "GPT-OSS 120B (Groq)",
        "provider": "groq",
        "tier": "Flagship Open-Weights",
        "description": "120B open weights reasoning running on ultra-fast Groq LPUs",
        "active": False,
    },
    {
        "id": "groq/qwen/qwen3.8-27b",
        "name": "Qwen 3.8 27B",
        "provider": "groq",
        "tier": "Code Expert",
        "description": "High-precision code comprehension and AST reasoning on Groq LPUs",
        "active": False,
    },
    {
        "id": "groq/openai/gpt-oss-20b",
        "name": "GPT-OSS 20B (Groq)",
        "provider": "groq",
        "tier": "Ultra Fast",
        "description": "Ultra-fast low-latency inference on Groq LPUs",
        "active": False,
    },
    {
        "id": "groq/llama-3.3-70b-versatile",
        "name": "Llama 3.3 70B",
        "provider": "groq",
        "tier": "Groq LPU Speed",
        "description": "Sub-second AST analysis powered by Groq LPU inference engine",
        "active": False,
    },
    {
        "id": "groq/allam-2-7b",
        "name": "Allam 2 7B",
        "provider": "groq",
        "tier": "Fast Reasoning",
        "description": "Lightweight multilingual open weights reasoning on Groq LPUs",
        "active": False,
    },
]

_MODELS_CACHE = {
    "timestamp": 0.0,
    "user_id": None,
    "models": []
}
CACHE_TTL = 300.0  # 5 minutes


def _fetch_groq_models(api_key: str) -> List[Dict[str, Any]]:
    """Live queries Groq GET /openai/v1/models to discover active models."""
    if not api_key:
        return []
    try:
        import httpx
        url = "https://api.groq.com/openai/v1/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        with httpx.Client(timeout=4.0) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                models = []
                for item in data:
                    mid = item.get("id", "")
                    if not item.get("active", True):
                        continue
                    # Filter out non-chat, audio, safety-guard, and terms-restricted models (like canopylabs/orpheus)
                    if any(x in mid.lower() for x in [
                        "whisper", "guard", "audio", "embed", "safeguard",
                        "canopylabs", "orpheus", "prompt-guard", "tts", "stt"
                    ]):
                        continue

                    # Prepend groq/ for LiteLLM routing
                    litellm_id = f"groq/{mid}" if not mid.startswith("groq/") else mid

                    if "gpt-oss-120b" in mid.lower():
                        name = "GPT-OSS 120B (Groq)"
                        tier = "Flagship Open-Weights"
                        desc = "120B open weights reasoning running on ultra-fast Groq LPUs"
                    elif "gpt-oss-20b" in mid.lower():
                        name = "GPT-OSS 20B (Groq)"
                        tier = "Ultra Fast"
                        desc = "Ultra-fast low-latency inference on Groq LPUs"
                    elif "qwen" in mid.lower():
                        name = "Qwen 3.8 27B" if "3.8" in mid else "Qwen 2.5 Coder 32B"
                        tier = "Code Expert"
                        desc = "High-precision code comprehension and AST reasoning on Groq LPUs"
                    elif "allam" in mid.lower():
                        name = "Allam 2 7B"
                        tier = "Fast Multilingual"
                        desc = "Lightweight multilingual open weights reasoning on Groq LPUs"
                    elif "llama-3.3-70b" in mid.lower():
                        name = "Llama 3.3 70B"
                        tier = "Groq LPU Speed"
                        desc = "Sub-second AST analysis powered by Groq LPU inference engine"
                    elif "llama-3.1-8b" in mid.lower():
                        name = "Llama 3.1 8B Instant"
                        tier = "Ultra Fast"
                        desc = "Ultra-fast open weights reasoning on Groq LPUs"
                    elif "llama3-70b" in mid.lower():
                        name = "Llama 3 70B"
                        tier = "High Capacity"
                        desc = "High-capacity open weights reasoning"
                    elif "deepseek-r1" in mid.lower():
                        name = "DeepSeek R1 (Groq)"
                        tier = "Open Reasoning"
                        desc = "Open-weights reasoning model with chain-of-thought insights"
                    elif "mixtral" in mid.lower():
                        name = "Mixtral 8x7B"
                        tier = "High Throughput"
                        desc = "Fast MoE architecture for code reasoning"
                    else:
                        name = mid.replace("groq/", "").replace("-", " ").title()
                        tier = "Groq LPU"
                        desc = "Sub-second inference via Groq LPUs"

                    models.append({
                        "id": litellm_id,
                        "name": name,
                        "provider": "groq",
                        "tier": tier,
                        "description": desc,
                        "active": True,
                        "discovered": True,
                        "live": True,
                    })

                def _sort_groq(m):
                    mid = m["id"].lower()
                    if "gpt-oss-120b" in mid:
                        return 0
                    if "qwen" in mid:
                        return 1
                    if "llama-3.3-70b" in mid:
                        return 2
                    if "gpt-oss-20b" in mid:
                        return 3
                    if "allam" in mid:
                        return 4
                    if "llama-3.1-8b" in mid:
                        return 5
                    return 6

                models.sort(key=lambda m: (_sort_groq(m), m["name"]))
                if models:
                    return models
            else:
                logger.warning("Groq models endpoint returned HTTP %s", resp.status_code)
    except Exception as e:
        logger.warning("Failed to fetch Groq models dynamically: %s", e)

    # Static fallback if endpoint query fails
    return [
        {
            "id": "groq/openai/gpt-oss-120b",
            "name": "GPT-OSS 120B (Groq)",
            "provider": "groq",
            "tier": "Flagship Open-Weights",
            "description": "120B open weights reasoning running on ultra-fast Groq LPUs",
            "active": True,
            "live": False,
        },
        {
            "id": "groq/qwen/qwen3.8-27b",
            "name": "Qwen 3.8 27B",
            "provider": "groq",
            "tier": "Code Expert",
            "description": "High-precision code comprehension and AST reasoning on Groq LPUs",
            "active": True,
            "live": False,
        },
        {
            "id": "groq/openai/gpt-oss-20b",
            "name": "GPT-OSS 20B (Groq)",
            "provider": "groq",
            "tier": "Ultra Fast",
            "description": "Ultra-fast low-latency inference on Groq LPUs",
            "active": True,
            "live": False,
        },
        {
            "id": "groq/llama-3.3-70b-versatile",
            "name": "Llama 3.3 70B",
            "provider": "groq",
            "tier": "Groq LPU Speed",
            "description": "Sub-second AST analysis powered by Groq LPU inference engine",
            "active": True,
            "live": False,
        },
    ]


def _fetch_openai_models(api_key: str) -> List[Dict[str, Any]]:
    """Live queries OpenAI GET /v1/models to discover active chat/reasoning models."""
    try:
        import httpx
        url = "https://api.openai.com/v1/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        with httpx.Client(timeout=3.5) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning("OpenAI models endpoint returned HTTP %s", resp.status_code)
                return []
            data = resp.json()
            models = []
            seen = set()
            wanted_prefixes = ("gpt-4o", "gpt-4-turbo", "o1", "o3")
            for item in data.get("data", []):
                mid = item.get("id", "")
                if any(mid.startswith(p) for p in wanted_prefixes):
                    if any(x in mid for x in ["audio", "realtime", "transcription", "2024", "preview-"]):
                        continue
                    if mid in seen:
                        continue
                    seen.add(mid)
                    name = mid.upper() if len(mid) <= 6 else mid
                    tier = "Reasoning" if (mid.startswith("o1") or mid.startswith("o3")) else "Flagship"
                    models.append({
                        "id": mid,
                        "name": name,
                        "provider": "openai",
                        "tier": tier,
                        "description": "High-speed reasoning across complex dependency graphs",
                        "active": True,
                        "discovered": True,
                    })
            models.sort(key=lambda m: (0 if m["id"] == "gpt-4o" else 1, 0 if m["id"] == "o3-mini" else 2, m["name"]))
            return models
    except Exception as e:
        logger.warning("Error fetching OpenAI models: %s", e)
        return []


def _fetch_gemini_models(api_key: str) -> List[Dict[str, Any]]:
    """Live queries Google Gemini models endpoint to discover active models."""
    try:
        import httpx
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        with httpx.Client(timeout=3.5) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return []
            data = resp.json()
            models = []
            for item in data.get("models", []):
                raw_name = item.get("name", "")
                mid = raw_name.replace("models/", "")
                methods = item.get("supportedGenerationMethods", [])
                if "generateContent" not in methods or not mid.startswith("gemini"):
                    continue
                if any(x in mid.lower() for x in ["embed", "aqa", "vision", "001", "experimental", "tts", "image", "transcribe", "robotics"]):
                    continue
                
                name = item.get("displayName") or mid.replace("-", " ").title()
                tier = "Fast Reasoning" if "flash" in mid else "Deep Pro"
                desc = item.get("description", "Multimodal code & AST reasoning")
                if len(desc) > 85:
                    desc = desc[:82] + "..."
                models.append({
                    "id": mid,
                    "name": name,
                    "provider": "gemini",
                    "tier": tier,
                    "description": desc,
                    "active": True,
                    "recommended": "2.0-flash" in mid,
                    "discovered": True,
                })
            
            # Ensure primary production models are represented
            if not any("2.0-flash" in m["id"] for m in models):
                models.insert(0, {
                    "id": "gemini-2.0-flash",
                    "name": "Gemini 2.0 Flash",
                    "provider": "gemini",
                    "tier": "Fast Reasoning",
                    "description": "Next-gen multimodal, low latency & thinking capabilities",
                    "active": True,
                    "recommended": True,
                    "discovered": True,
                })

            models.sort(key=lambda m: (
                0 if m["id"] == "gemini-2.0-flash" else
                1 if m["id"] == "gemini-2.5-flash" else
                2 if m["id"] == "gemini-2.5-pro" else
                3 if m["id"] == "gemini-1.5-pro" else 4,
                m["name"]
            ))
            # Keep top 8 concise models to avoid UI clutter
            return models[:8]
    except Exception as e:
        logger.warning("Error fetching Gemini models: %s", e)
        return []


class SaveKeyRequest(BaseModel):
    provider: Optional[str] = None
    api_key: Optional[str] = None
    keys: Optional[Dict[str, str]] = None


class TestKeyRequest(BaseModel):
    provider: str
    api_key: Optional[str] = None


def _get_target_user(current_user: Optional[User], db: Session) -> User:
    """Returns active user or falls back to standard demo user for seamless local development."""
    if current_user:
        return current_user
    demo_user = db.query(User).filter(User.id == "usr-demo-777").first()
    if not demo_user:
        demo_user = db.query(User).first()
    if not demo_user:
        demo_user = User(
            id="usr-demo-777",
            email="harsha.demo@codegraph.ai",
            password_hash="demopassword2026",
            role="Lead Architect",
        )
        db.add(demo_user)
        db.commit()
        db.refresh(demo_user)
    return demo_user


@router.post("/save")
def save_provider_key(
    req: SaveKeyRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Securely stores and encrypts one or more provider keys using authenticated AES-128-CBC."""
    user = _get_target_user(current_user, db)

    # 1. Load existing decrypted dictionary
    existing_keys = get_user_encrypted_keys(user=user)

    updates = {}
    if req.provider and req.api_key is not None:
        prov = req.provider.lower().strip()
        updates[prov] = req.api_key.strip()
    if req.keys:
        for k, v in req.keys.items():
            if v is not None:
                updates[k.lower().strip()] = v.strip()

    if not updates:
        raise HTTPException(status_code=400, detail="No provider or key payload provided.")

    # 2. Update keys dictionary
    for prov, val in updates.items():
        if val:
            existing_keys[prov] = val
            # Update dedicated column if present
            encrypted_val = encrypt_api_key(val)
            col_name = f"{prov}_key_encrypted"
            if hasattr(user, col_name):
                setattr(user, col_name, encrypted_val)
        else:
            existing_keys.pop(prov, None)
            col_name = f"{prov}_key_encrypted"
            if hasattr(user, col_name):
                setattr(user, col_name, None)

    # 3. Store full bundle
    user.provider_keys_encrypted = encrypt_provider_keys(existing_keys)
    db.commit()
    db.refresh(user)

    # Invalidate model discovery cache on key change
    _MODELS_CACHE["timestamp"] = 0.0

    # 4. Compute status map
    status_map = _compute_status_map(existing_keys)

    return {
        "status": "saved",
        "provider": req.provider,
        "keys_status": status_map,
        **status_map,
    }


@router.get("/status")
def get_keys_status(
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Returns provider key configuration status and safe masked previews."""
    user = _get_target_user(current_user, db)
    existing_keys = get_user_encrypted_keys(user=user)

    status_map = _compute_status_map(existing_keys)
    masked_map: Dict[str, Optional[str]] = {}

    for prov in SUPPORTED_PROVIDERS:
        key_val = existing_keys.get(prov)
        if not key_val:
            env_var = ENV_MAP.get(prov, "")
            key_val = os.getenv(env_var, "").strip() if env_var else ""
        if prov == "gemini" and not key_val and settings.GEMINI_API_KEY:
            key_val = settings.GEMINI_API_KEY.strip()

        is_configured = status_map.get(prov, False)
        masked_map[prov] = mask_api_key(key_val) if (is_configured and key_val) else None

    # Merge status_map top-level keys for direct spec matching: { "gemini": true, "openai": false, ... }
    return {
        "success": True,
        "status": status_map,
        "masked_keys": masked_map,
        **status_map,
    }


@router.delete("/{provider}")
def delete_provider_key(
    provider: str,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Clears the stored encrypted key for a specific provider."""
    user = _get_target_user(current_user, db)
    existing_keys = get_user_encrypted_keys(user=user)

    prov = provider.lower().strip()
    existing_keys.pop(prov, None)
    col_name = f"{prov}_key_encrypted"
    if hasattr(user, col_name):
        setattr(user, col_name, None)

    user.provider_keys_encrypted = encrypt_provider_keys(existing_keys)
    db.commit()

    # Invalidate model discovery cache on key deletion
    _MODELS_CACHE["timestamp"] = 0.0

    status_map = _compute_status_map(existing_keys)

    return {
        "status": "cleared",
        "provider": prov,
        "keys_status": status_map,
        **status_map,
    }


@router.get("/models")
@router.post("/models")
def get_available_models(
    refresh: bool = False,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """
    Live Model Discovery Pipeline:
    Inspects configured API keys and queries provider model listing endpoints (e.g., Groq GET /openai/v1/models)
    to discover active production models. Falls back to curated defaults if unconfigured or offline.
    """
    user = _get_target_user(current_user, db)
    user_id = str(user.id)
    now = time.time()

    # Cache hit check
    if not refresh and _MODELS_CACHE["user_id"] == user_id and (now - _MODELS_CACHE["timestamp"]) < CACHE_TTL:
        if _MODELS_CACHE["models"]:
            return {
                "success": True,
                "cached": True,
                "models": _MODELS_CACHE["models"],
                "total": len(_MODELS_CACHE["models"]),
            }

    existing_keys = get_user_encrypted_keys(user=user)
    status_map = _compute_status_map(existing_keys)

    consolidated_models: List[Dict[str, Any]] = []

    for prov in SUPPORTED_PROVIDERS:
        has_key = status_map.get(prov, False)
        discovered = []

        if has_key:
            key_val = existing_keys.get(prov)
            if not key_val:
                env_var = ENV_MAP.get(prov, "")
                key_val = os.getenv(env_var, "").strip() if env_var else ""
            if prov == "gemini" and not key_val and settings.GEMINI_API_KEY:
                key_val = settings.GEMINI_API_KEY.strip()

            if prov == "groq" and key_val:
                discovered = _fetch_groq_models(key_val)
            elif prov == "openai" and key_val:
                discovered = _fetch_openai_models(key_val)
            elif prov == "gemini" and key_val:
                discovered = _fetch_gemini_models(key_val)

        if discovered:
            consolidated_models.extend(discovered)
        else:
            defaults = [
                dict(m, active=has_key)
                for m in DEFAULT_CURATED_MODELS
                if m["provider"] == prov
            ]
            consolidated_models.extend(defaults)

    _MODELS_CACHE["timestamp"] = now
    _MODELS_CACHE["user_id"] = user_id
    _MODELS_CACHE["models"] = consolidated_models

    return {
        "success": True,
        "cached": False,
        "models": consolidated_models,
        "total": len(consolidated_models),
    }


@router.post("/test")
def test_provider_key(
    req: TestKeyRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Live validates API key connectivity against the provider endpoint."""
    prov = req.provider.lower().strip()
    user = _get_target_user(current_user, db)

    # Resolve key
    key_val = req.api_key.strip() if req.api_key and len(req.api_key.strip()) > 15 else None
    if not key_val:
        existing_keys = get_user_encrypted_keys(user=user)
        key_val = existing_keys.get(prov) or os.getenv(ENV_MAP.get(prov, ""))
    if prov == "gemini" and not key_val and settings.GEMINI_API_KEY:
        key_val = settings.GEMINI_API_KEY.strip()

    if not key_val:
        raise HTTPException(
            status_code=400,
            detail=f"No key provided or stored for provider '{prov}'. Enter a key to test."
        )

    t0 = time.time()
    try:
        if prov == "gemini":
            from google import genai
            client = genai.Client(api_key=key_val)
            models = list(client.models.list(config={"page_size": 5}))
            elapsed_ms = int((time.time() - t0) * 1000)
            return {
                "success": True,
                "provider": prov,
                "latency_ms": elapsed_ms,
                "message": f"Successfully authenticated with Google Gemini ({len(models)} models available).",
            }
        elif prov == "groq":
            import httpx
            # Query Groq's official model catalog endpoint directly
            url = "https://api.groq.com/openai/v1/models"
            headers = {"Authorization": f"Bearer {key_val}"}
            with httpx.Client(timeout=6.0) as client:
                resp = client.get(url, headers=headers)
                elapsed_ms = int((time.time() - t0) * 1000)
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    models = [
                        m["id"] for m in data 
                        if m.get("active", True) and not any(x in m["id"].lower() for x in [
                            "whisper", "guard", "embed", "audio", "safeguard",
                            "canopylabs", "orpheus", "prompt-guard"
                        ])
                    ]
                    active_model = next((m for m in [
                        "openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b",
                        "llama-3.3-70b-versatile", "allam-2-7b"
                    ] if m in models), (models[0] if models else "Groq LPU"))
                    return {
                        "success": True,
                        "provider": prov,
                        "latency_ms": elapsed_ms,
                        "message": f"Successfully authenticated with Groq ({len(models)} models authorized, active: {active_model}).",
                        "active_model": active_model,
                    }
                elif resp.status_code == 401:
                    return {
                        "success": False,
                        "provider": prov,
                        "error": "Authentication failed: Invalid Groq API key (HTTP 401 Unauthorized).",
                        "message": "Invalid Groq API key: Please verify your key on console.groq.com/keys.",
                    }
                else:
                    return {
                        "success": False,
                        "provider": prov,
                        "error": f"Groq validation notice (HTTP {resp.status_code}): {resp.text[:150]}",
                        "message": f"Groq endpoint returned HTTP {resp.status_code}",
                    }
        elif prov == "openai":
            import httpx
            url = "https://api.openai.com/v1/models"
            headers = {"Authorization": f"Bearer {key_val}"}
            with httpx.Client(timeout=6.0) as client:
                resp = client.get(url, headers=headers)
                elapsed_ms = int((time.time() - t0) * 1000)
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    return {
                        "success": True,
                        "provider": prov,
                        "latency_ms": elapsed_ms,
                        "message": f"Successfully authenticated with OpenAI ({len(data)} models available).",
                    }
                elif resp.status_code == 401:
                    return {
                        "success": False,
                        "provider": prov,
                        "error": "Authentication failed: Invalid OpenAI API key (HTTP 401 Unauthorized).",
                        "message": "Invalid OpenAI API key: Please verify your key on platform.openai.com/account/api-keys.",
                    }
                else:
                    return {
                        "success": False,
                        "provider": prov,
                        "error": f"OpenAI validation notice (HTTP {resp.status_code}): {resp.text[:150]}",
                        "message": f"OpenAI endpoint returned HTTP {resp.status_code}",
                    }
        else:
            import litellm
            test_models = {
                "anthropic": "anthropic/claude-3-haiku-20240307",
                "deepseek": "deepseek/deepseek-chat",
            }
            model_to_test = test_models.get(prov, f"{prov}/default")
            resp = litellm.completion(
                model=model_to_test,
                messages=[{"role": "user", "content": "ping"}],
                api_key=key_val,
                max_tokens=2,
                timeout=10,
            )
            elapsed_ms = int((time.time() - t0) * 1000)
            return {
                "success": True,
                "provider": prov,
                "latency_ms": elapsed_ms,
                "message": f"Successfully authenticated with {prov.upper()} via LiteLLM ({elapsed_ms}ms).",
            }
    except Exception as e:
        err_msg = str(e).replace(key_val, "***")
        logger.warning(f"Key test failed for provider '{prov}': {err_msg}")
        return {
            "success": False,
            "provider": prov,
            "error": err_msg[:250],
            "message": f"Validation failed: {err_msg[:180]}",
        }
