"""Seed the two persistent Glitch Hermes sessions without a model call."""

from __future__ import annotations

import uuid

from hermes_state import SessionDB


def ensure(db: SessionDB, title: str) -> str:
    existing = db.resolve_session_by_title(title)
    if existing:
        return db.resolve_resume_session_id(existing)
    session_id = str(uuid.uuid4())
    db.create_session(session_id, "cli")
    db.set_session_title(session_id, title)
    return session_id


if __name__ == "__main__":
    database = SessionDB()
    print(f"chat={ensure(database, 'chat')}")
    print(f"trading={ensure(database, 'trading')}")
