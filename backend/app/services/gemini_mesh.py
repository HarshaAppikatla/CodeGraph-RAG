import time
import logging
from typing import Dict, List, Optional
from google import genai
from google.genai import types
from google.genai.errors import APIError

logger = logging.getLogger("codegraph.gemini_mesh")

# Verified Gemini models in order of performance, response latency and availability
DEFAULT_PREFERRED_CHAIN = [
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
    "gemini-2.5-pro",
]


class DynamicModelMesh:
    """Discovers available models on initialization and provides dynamic runtime fallback

    with automatic cooldowns for 429 (rate limits), 503 (high demand), and 404 (deprecated models).
    """

    def __init__(self, api_key: str, preferred_priority: Optional[List[str]] = None):
        self.api_key = api_key
        self.client = genai.Client(api_key=api_key)
        self.preferred_priority = preferred_priority or DEFAULT_PREFERRED_CHAIN
        self.cooldowns: Dict[str, float] = {}
        self.cooldown_duration = 60  # seconds

        # Step 1: Discover and validate available models once on startup
        self.active_chain = self._build_validated_chain()

    def _build_validated_chain(self) -> List[str]:
        """Queries the API key on startup to discover available models matching preferences."""
        try:
            remote_models = [
                m.name.replace("models/", "")
                for m in self.client.models.list()
                if "generateContent" in (getattr(m, "supported_actions", []) or [])
            ]

            # Intersect available models with user's priority list
            valid_chain = [m for m in self.preferred_priority if m in remote_models]

            # Fallback to any available gemini model if none of the preferred models match
            if not valid_chain:
                valid_chain = [m for m in remote_models if "gemini" in m]

            logger.info("DynamicModelMesh validated chain: %s", valid_chain)
            return valid_chain or ["gemini-flash-latest"]
        except Exception as e:
            logger.warning("Could not fetch remote models (%s). Falling back to preferred list.", e)
            return self.preferred_priority

    def generate_content(self, prompt: str, json_mode: bool = False, timeout_ms: int = 15000) -> str:
        """Executes prompt against the highest priority available model, falling back dynamically."""
        errors: Dict[str, str] = {}
        config = types.GenerateContentConfig(
            response_mime_type="application/json" if json_mode else None,
            http_options={"timeout": timeout_ms},
        )

        for model_name in self.active_chain:
            # Skip model if currently in cooldown
            if time.time() < self.cooldowns.get(model_name, 0):
                remaining = int(self.cooldowns[model_name] - time.time())
                logger.warning("Skipping '%s' (cooldown: %ds remaining)", model_name, remaining)
                continue

            try:
                logger.info("Generating content with model: '%s'", model_name)
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config,
                )
                # Clear cooldown on success
                self.cooldowns.pop(model_name, None)
                return response.text or ""

            except APIError as e:
                err_msg = str(e)
                logger.warning("Model '%s' failed (code %s): %s", model_name, getattr(e, "code", "N/A"), err_msg[:120])
                errors[model_name] = err_msg

                # 404 (deprecated / not available) gets 1 hr cooldown; 429/503 get normal cooldown
                duration = 3600 if "404" in err_msg or "NOT_FOUND" in err_msg else self.cooldown_duration
                self.cooldowns[model_name] = time.time() + duration
                logger.info("Placed '%s' on cooldown for %ds. Shifting to next model...", model_name, duration)

            except Exception as e:
                err_msg = str(e)
                logger.warning("Model '%s' failed: %s", model_name, err_msg[:120])
                errors[model_name] = err_msg
                duration = 3600 if "404" in err_msg or "NOT_FOUND" in err_msg else self.cooldown_duration
                self.cooldowns[model_name] = time.time() + duration

        raise RuntimeError(f"All available models in the priority chain failed: {errors}")


# Global cache of meshes keyed by API key to avoid re-discovering on every call
_mesh_cache: Dict[str, DynamicModelMesh] = {}


def get_gemini_mesh(api_key: str, preferred_priority: Optional[List[str]] = None) -> DynamicModelMesh:
    """Returns or creates a cached DynamicModelMesh instance for the given API key."""
    if api_key not in _mesh_cache:
        _mesh_cache[api_key] = DynamicModelMesh(api_key=api_key, preferred_priority=preferred_priority)
    return _mesh_cache[api_key]
