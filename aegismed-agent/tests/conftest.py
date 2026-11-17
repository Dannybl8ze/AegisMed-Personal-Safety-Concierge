"""Shared fixtures: an isolated store per test and a stubbed Gemini call.

Only the network call to Gemini is replaced. The graph, security gate, rule
checks, session service and HTTP endpoints are the real code.
"""
import json

import pytest
from fastapi.testclient import TestClient
from google.adk.models.llm_response import LlmResponse
from google.genai import types

import app.agent as agent_mod
from app import storage as storage_mod

MOCK_ASSESSMENT = {
    "risk_level": "Medium",
    "warnings": ["MOCK: monitor the patient closely"],
    "explanation": "MOCK reviewer explanation.",
}

GEMINI_ENV = ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_CLOUD_PROJECT")


class FakeRedis:
    """In-memory stand-in for the Upstash client, limited to the calls storage makes.

    ``hgetall`` returns fields sorted by name rather than by insertion, because
    Redis does not promise hash ordering and the storage layer must not rely on it.
    """

    def __init__(self):
        self.data = {}

    def hgetall(self, key):
        return {field: self.data.get(key, {})[field] for field in sorted(self.data.get(key, {}))}

    def hget(self, key, field):
        return self.data.get(key, {}).get(field)

    def hset(self, key, field=None, value=None, values=None):
        bucket = self.data.setdefault(key, {})
        if field is not None:
            bucket[field] = value
        if values:
            bucket.update(values)

    def hdel(self, key, *fields):
        for field in fields:
            self.data.get(key, {}).pop(field, None)

    def rpush(self, key, *elements):
        self.data.setdefault(key, []).extend(elements)

    def lrange(self, key, start, stop):
        items = self.data.get(key, [])
        return items[start:] if stop == -1 else items[start:stop + 1]

    def delete(self, *keys):
        for key in keys:
            self.data.pop(key, None)

    def incr(self, key):
        self.data[key] = int(self.data.get(key, 0)) + 1
        return self.data[key]

    def expire(self, key, seconds):
        self.expiry = getattr(self, "expiry", {})
        self.expiry[key] = seconds
        return 1


class StoreFactory:
    """Builds storage objects that share one underlying data set, like separate processes would."""

    def __init__(self, kind, tmp_path):
        self.kind = kind
        self._dir = tmp_path / "data"
        self._redis = FakeRedis()

    def new(self):
        if self.kind == "file":
            return storage_mod.JsonFileStorage(self._dir)
        return storage_mod.UpstashStorage(self._redis, prefix="aegismed:test")


class FakeLLM:
    def __init__(self):
        self.prompts = []
        self.fail = False

    @property
    def calls(self):
        return len(self.prompts)


@pytest.fixture(params=["file", "upstash"])
def store_factory(request, tmp_path, monkeypatch):
    for names in storage_mod.UPSTASH_ENV_PAIRS:
        for name in names:
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    return StoreFactory(request.param, tmp_path)


@pytest.fixture
def storage(store_factory):
    store = store_factory.new()
    storage_mod.set_storage(store)
    yield store
    storage_mod.set_storage(None)


@pytest.fixture
def llm(monkeypatch):
    """Replace the Gemini network call and record every prompt it would have received."""
    for name in GEMINI_ENV:
        monkeypatch.delenv(name, raising=False)
    fake = FakeLLM()

    async def generate_content_async(self, llm_request, stream=False):
        if fake.fail:
            raise RuntimeError("simulated Gemini outage")
        prompt = " ".join(
            part.text for content in (llm_request.contents or []) for part in (content.parts or []) if part.text
        )
        fake.prompts.append(prompt)
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part.from_text(text=json.dumps(MOCK_ASSESSMENT))])
        )

    monkeypatch.setattr(agent_mod.LoopSafeGemini, "generate_content_async", generate_content_async)
    return fake


@pytest.fixture
def client(storage, llm):
    from dashboard_api.main import app

    return TestClient(app, raise_server_exceptions=False)
