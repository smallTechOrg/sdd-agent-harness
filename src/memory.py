"""Memory — four flavours. Only SESSION memory is wired (a SQLite transcript by
conversation_id). Episodic + semantic are LABELLED SLOTS: the interfaces exist,
the bodies are stubs a build fills. No vector DB — SQLite in the same file.
"""
from __future__ import annotations

from db.models import TurnRow
from db.session import create_db_session


# --- Flavour 2: SESSION memory (the one wired flavour) ---
# The user's own prior turns are TRUSTED recall — presented as conversation
# history the agent can rely on. The hostile fence (guardrails.wrap_untrusted)
# is for *external* tool/retrieved content, not the user's own words.

def load_session(conversation_id: str, limit: int = 20) -> str:
    if not conversation_id:
        return ""
    with create_db_session() as s:
        rows = (s.query(TurnRow).filter(TurnRow.conversation_id == conversation_id)
                .order_by(TurnRow.created_at.asc()).limit(limit).all())
        turns = [(r.role, r.content) for r in rows]
    if not turns:
        return ""
    transcript = "\n".join(f"{role}: {content}" for role, content in turns)
    return f"Conversation so far:\n{transcript}"


def append_turn(conversation_id: str, role: str, content: str) -> None:
    if not conversation_id:
        return
    with create_db_session() as s:
        s.add(TurnRow(conversation_id=conversation_id, role=role, content=content))


# --- Flavour 3: EPISODIC (lexical recall) — SLOT (swap _score for embeddings) ---

def recall_episodic(query: str, limit: int = 3) -> list[str]:
    with create_db_session() as s:
        rows = s.query(TurnRow).order_by(TurnRow.created_at.desc()).limit(200).all()
    scored = sorted(((_score(query, r.content), r.content) for r in rows), reverse=True)
    return [c for sc, c in scored[:limit] if sc > 0]


def _score(query: str, text: str) -> int:
    return len(set(query.lower().split()) & set(text.lower().split()))


# --- Flavour 4: SEMANTIC (facts) — SLOT (not on the green path) ---

def upsert_fact(subject: str, key: str, value: str) -> None:
    from db.models import FactRow
    with create_db_session() as s:
        row = s.query(FactRow).filter(FactRow.subject == subject, FactRow.key == key).one_or_none()
        if row:
            row.value = value
        else:
            s.add(FactRow(subject=subject, key=key, value=value))
