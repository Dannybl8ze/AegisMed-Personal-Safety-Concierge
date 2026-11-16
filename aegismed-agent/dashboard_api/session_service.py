"""ADK session service backed by the AegisMed storage module.

The caregiver pause/resume flow needs the paused workflow to survive between
requests, which may be served by different processes. Each session is stored as
one JSON document, so any instance can load it and resume.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Optional

from google.adk.events.event import Event
from google.adk.sessions.base_session_service import (
    BaseSessionService,
    GetSessionConfig,
    ListSessionsResponse,
)
from google.adk.sessions.session import Session

from app.storage import get_storage


def session_key(app_name: str, user_id: str, session_id: str) -> str:
    return f"{app_name}:{user_id}:{session_id}"


class StorageSessionService(BaseSessionService):
    """Persists whole sessions through ``app.storage``.

    State keys are stored per session; the ``app:`` and ``user:`` sharing
    scopes are not implemented because the workflow does not use them.
    """

    async def _save(self, session: Session) -> None:
        session.last_update_time = time.time()
        key = session_key(session.app_name, session.user_id, session.id)
        await asyncio.to_thread(get_storage().save_session, key, session.model_dump_json())

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Session:
        session = Session(
            id=session_id or uuid.uuid4().hex,
            app_name=app_name,
            user_id=user_id,
            state=state or {},
        )
        await self._save(session)
        return session

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: Optional[GetSessionConfig] = None,
    ) -> Optional[Session]:
        payload = await asyncio.to_thread(get_storage().get_session, session_key(app_name, user_id, session_id))
        if not payload:
            return None
        session = Session.model_validate_json(payload)
        if config:
            if config.after_timestamp:
                session.events = [e for e in session.events if e.timestamp >= config.after_timestamp]
            if config.num_recent_events:
                session.events = session.events[-config.num_recent_events:]
        return session

    async def list_sessions(self, *, app_name: str, user_id: Optional[str] = None) -> ListSessionsResponse:
        payloads = await asyncio.to_thread(get_storage().get_sessions)
        sessions = []
        for payload in payloads.values():
            session = Session.model_validate_json(payload)
            if session.app_name == app_name and (user_id is None or session.user_id == user_id):
                session.events = []
                sessions.append(session)
        return ListSessionsResponse(sessions=sessions)

    async def delete_session(self, *, app_name: str, user_id: str, session_id: str) -> None:
        await asyncio.to_thread(get_storage().delete_session, session_key(app_name, user_id, session_id))

    async def append_event(self, session: Session, event: Event) -> Event:
        event = await super().append_event(session, event)
        if not event.partial:
            await self._save(session)
        return event
