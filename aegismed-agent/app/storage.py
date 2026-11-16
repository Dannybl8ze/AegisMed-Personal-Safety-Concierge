"""All persistent AegisMed state behind one interface.

Four collections live here: patients, caregiver alerts, chat history and ADK
workflow sessions. Two backends implement the same contract:

* ``UpstashStorage``  - durable Redis over HTTPS, used when Upstash credentials
  are present in the environment (production on Vercel).
* ``JsonFileStorage`` - JSON files in a local data directory (development).

Pick the backend with ``get_storage()``; nothing else in the codebase reads or
writes state directly.
"""
from __future__ import annotations

import json
import os
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

SEED_PATIENTS_FILE = Path(__file__).parent / "data" / "patients.seed.json"
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / ".data"

# Either pair works: the first is Upstash's own naming, the second is what the
# Vercel Marketplace integration injects.
UPSTASH_ENV_PAIRS = (
    ("UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN"),
    ("KV_REST_API_URL", "KV_REST_API_TOKEN"),
)


class StorageNotConfigured(RuntimeError):
    """Raised when no usable storage backend is configured for this environment."""


def load_seed_patients() -> dict[str, dict]:
    """The demo patients every fresh store starts with."""
    with open(SEED_PATIENTS_FILE, encoding="utf-8") as f:
        return json.load(f)


class Storage(ABC):
    """Contract shared by every backend. All methods are synchronous."""

    # -- patients -----------------------------------------------------------
    @abstractmethod
    def get_patients(self) -> dict[str, dict]:
        """All patients keyed by id, seed patients first, then registration order."""

    @abstractmethod
    def save_patient(self, patient_id: str, patient: dict) -> None:
        """Create or replace one patient."""

    # -- caregiver alerts ---------------------------------------------------
    @abstractmethod
    def get_alerts(self) -> dict[str, dict]:
        """All alerts (pending and resolved) keyed by session id, oldest first."""

    @abstractmethod
    def get_alert(self, session_id: str) -> Optional[dict]:
        """One alert, or None."""

    @abstractmethod
    def save_alert(self, session_id: str, alert: dict) -> None:
        """Create or replace one alert, keeping its original position."""

    # -- chat history -------------------------------------------------------
    @abstractmethod
    def get_chat(self) -> list[dict]:
        """Every chat message, oldest first."""

    @abstractmethod
    def append_chat(self, *messages: dict) -> None:
        """Append messages to the chat history."""

    # -- ADK workflow sessions ---------------------------------------------
    @abstractmethod
    def get_session(self, key: str) -> Optional[str]:
        """Serialized session JSON, or None."""

    @abstractmethod
    def save_session(self, key: str, payload: str) -> None:
        """Create or replace one serialized session."""

    @abstractmethod
    def delete_session(self, key: str) -> None:
        """Remove one session if it exists."""

    @abstractmethod
    def get_sessions(self) -> dict[str, str]:
        """Every serialized session keyed by its key."""

    # -- demo reset ---------------------------------------------------------
    @abstractmethod
    def reset_demo_state(self) -> None:
        """Clear chat history, alerts and sessions. Registered patients remain."""


class JsonFileStorage(Storage):
    """JSON files in a directory. Suitable for one local process."""

    def __init__(self, data_dir: Path | str):
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, name: str) -> Path:
        return self._dir / f"{name}.json"

    def _read(self, name: str, default: Any) -> Any:
        path = self._path(name)
        if not path.exists():
            return default
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _write(self, name: str, value: Any) -> None:
        path = self._path(name)
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(value, f, indent=2, ensure_ascii=False)
        # A file-sync client can hold the target open for a moment on Windows.
        for attempt in range(5):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05 * (attempt + 1))

    def get_patients(self) -> dict[str, dict]:
        with self._lock:
            patients = self._read("patients", None)
            if patients is None:
                patients = load_seed_patients()
                self._write("patients", patients)
            return patients

    def save_patient(self, patient_id: str, patient: dict) -> None:
        with self._lock:
            patients = self.get_patients()
            patients[patient_id] = patient
            self._write("patients", patients)

    def get_alerts(self) -> dict[str, dict]:
        with self._lock:
            return self._read("alerts", {})

    def get_alert(self, session_id: str) -> Optional[dict]:
        return self.get_alerts().get(session_id)

    def save_alert(self, session_id: str, alert: dict) -> None:
        with self._lock:
            alerts = self.get_alerts()
            alerts[session_id] = alert
            self._write("alerts", alerts)

    def get_chat(self) -> list[dict]:
        with self._lock:
            return self._read("chat_history", [])

    def append_chat(self, *messages: dict) -> None:
        with self._lock:
            history = self.get_chat()
            history.extend(messages)
            self._write("chat_history", history)

    def get_session(self, key: str) -> Optional[str]:
        return self.get_sessions().get(key)

    def save_session(self, key: str, payload: str) -> None:
        with self._lock:
            sessions = self.get_sessions()
            sessions[key] = payload
            self._write("sessions", sessions)

    def delete_session(self, key: str) -> None:
        with self._lock:
            sessions = self.get_sessions()
            if sessions.pop(key, None) is not None:
                self._write("sessions", sessions)

    def get_sessions(self) -> dict[str, str]:
        with self._lock:
            return self._read("sessions", {})

    def reset_demo_state(self) -> None:
        with self._lock:
            for name in ("alerts", "chat_history", "sessions"):
                self._path(name).unlink(missing_ok=True)


class UpstashStorage(Storage):
    """Redis (Upstash REST API). Safe across serverless instances.

    Layout under ``<prefix>``: ``patients`` and ``alerts`` are hashes whose
    values carry a sequence number so reads come back in insertion order,
    ``chat`` is a list, and ``sessions`` is a hash of serialized ADK sessions.
    """

    def __init__(self, client: Any, prefix: str = "aegismed"):
        self._redis = client
        self._prefix = prefix

    def _key(self, name: str) -> str:
        return f"{self._prefix}:{name}"

    @staticmethod
    def _wrap(seq: float, data: dict) -> str:
        return json.dumps({"seq": seq, "data": data}, ensure_ascii=False)

    def _ordered_get(self, name: str) -> dict[str, dict]:
        raw = self._redis.hgetall(self._key(name)) or {}
        entries = {field: json.loads(value) for field, value in raw.items()}
        return {field: entry["data"] for field, entry in sorted(entries.items(), key=lambda kv: kv[1]["seq"])}

    def _ordered_put(self, name: str, field: str, data: dict) -> None:
        existing = self._redis.hget(self._key(name), field)
        seq = json.loads(existing)["seq"] if existing else time.time()
        self._redis.hset(self._key(name), field, self._wrap(seq, data))

    def get_patients(self) -> dict[str, dict]:
        patients = self._ordered_get("patients")
        if not patients:
            patients = load_seed_patients()
            self._redis.hset(
                self._key("patients"),
                values={pid: self._wrap(float(i), p) for i, (pid, p) in enumerate(patients.items())},
            )
        return patients

    def save_patient(self, patient_id: str, patient: dict) -> None:
        self.get_patients()  # make sure the seed patients exist first
        self._ordered_put("patients", patient_id, patient)

    def get_alerts(self) -> dict[str, dict]:
        return self._ordered_get("alerts")

    def get_alert(self, session_id: str) -> Optional[dict]:
        raw = self._redis.hget(self._key("alerts"), session_id)
        return json.loads(raw)["data"] if raw else None

    def save_alert(self, session_id: str, alert: dict) -> None:
        self._ordered_put("alerts", session_id, alert)

    def get_chat(self) -> list[dict]:
        return [json.loads(item) for item in self._redis.lrange(self._key("chat"), 0, -1) or []]

    def append_chat(self, *messages: dict) -> None:
        if messages:
            self._redis.rpush(self._key("chat"), *[json.dumps(m, ensure_ascii=False) for m in messages])

    def get_session(self, key: str) -> Optional[str]:
        return self._redis.hget(self._key("sessions"), key)

    def save_session(self, key: str, payload: str) -> None:
        self._redis.hset(self._key("sessions"), key, payload)

    def delete_session(self, key: str) -> None:
        self._redis.hdel(self._key("sessions"), key)

    def get_sessions(self) -> dict[str, str]:
        return self._redis.hgetall(self._key("sessions")) or {}

    def reset_demo_state(self) -> None:
        self._redis.delete(self._key("alerts"), self._key("chat"), self._key("sessions"))


def upstash_credentials() -> Optional[tuple[str, str]]:
    """(url, token) from the environment, or None when Upstash is not configured."""
    for url_var, token_var in UPSTASH_ENV_PAIRS:
        url, token = os.environ.get(url_var), os.environ.get(token_var)
        if url and token:
            return url, token
    return None


def key_prefix() -> str:
    """Namespace for Redis keys, so preview and production never share state."""
    return os.environ.get("AEGISMED_KEY_PREFIX") or f"aegismed:{os.environ.get('VERCEL_ENV', 'local')}"


def build_storage() -> Storage:
    creds = upstash_credentials()
    if creds:
        from upstash_redis import Redis

        return UpstashStorage(Redis(url=creds[0], token=creds[1], allow_telemetry=False), prefix=key_prefix())
    if os.environ.get("VERCEL"):
        # Vercel functions have a read-only filesystem and no shared memory, so
        # falling back to local files would silently lose patients and alerts.
        raise StorageNotConfigured(
            "No durable store configured. Set UPSTASH_REDIS_REST_URL and "
            "UPSTASH_REDIS_REST_TOKEN (or KV_REST_API_URL and KV_REST_API_TOKEN)."
        )
    return JsonFileStorage(os.environ.get("AEGISMED_DATA_DIR") or DEFAULT_DATA_DIR)


_storage: Optional[Storage] = None
_storage_lock = threading.Lock()


def get_storage() -> Storage:
    """The process-wide storage backend, built on first use."""
    global _storage
    if _storage is None:
        with _storage_lock:
            if _storage is None:
                _storage = build_storage()
    return _storage


def set_storage(storage: Optional[Storage]) -> None:
    """Replace the process-wide backend (tests), or clear it with None."""
    global _storage
    _storage = storage
