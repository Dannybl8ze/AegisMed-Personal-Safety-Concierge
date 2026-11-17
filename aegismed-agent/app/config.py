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
WARFARIN_THRESHOLD_MG = 10.0


def gemini_mode() -> str:
    """Which Gemini auth mode the environment selects: 'vertex', 'api_key' or 'unconfigured'."""
    if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("true", "1"):
        return "vertex"
    if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        return "api_key"
    return "unconfigured"
