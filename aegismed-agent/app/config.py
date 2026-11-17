"""Runtime configuration for the AegisMed agent. Everything comes from the environment.

Gemini authentication is handled by google-genai from these variables:

* API-key mode: ``GOOGLE_API_KEY`` (or ``GEMINI_API_KEY``).
* Vertex AI mode: ``GOOGLE_GENAI_USE_VERTEXAI=true`` with ``GOOGLE_CLOUD_PROJECT``
  and ``GOOGLE_CLOUD_LOCATION``, plus Application Default Credentials.

The model comes from ``GEMINI_MODEL``. ``gemini-2.5-flash`` is scheduled to be
retired by Google on 2026-12-01, so the default is its current replacement.
"""
import os

DEFAULT_MODEL = "gemini-3.8-flash"
MODEL_NAME = os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL

# One Gemini call may take this long (seconds) before it is given up on. A hosted
# request has a hard limit of several minutes, so this keeps the failure visible.
GEMINI_CALL_TIMEOUT_SECONDS = 75

_THINKING_LEVELS = ("MINIMAL", "LOW", "MEDIUM", "HIGH")


def thinking_level(model_name: str) -> "str | None":
    """How much Gemini 3 models should think before answering, or None for other models.

    Gemini 3 models think at a high level unless told otherwise. For this short
    advisory review that took over two minutes, so the default here is "low".
    ``GEMINI_THINKING_LEVEL`` (minimal, low, medium or high) overrides it. Older
    models use a different control, so they are left alone.
    """
    if not model_name.startswith("gemini-3"):
        return None
    level = (os.environ.get("GEMINI_THINKING_LEVEL") or "low").strip().upper()
    return level if level in _THINKING_LEVELS else "LOW"
WARFARIN_THRESHOLD_MG = 10.0


def gemini_mode() -> str:
    """Which Gemini auth mode the environment selects: 'vertex', 'api_key' or 'unconfigured'."""
    if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("true", "1"):
        return "vertex"
    if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        return "api_key"
    return "unconfigured"
