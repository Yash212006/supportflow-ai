from dataclasses import dataclass, field


@dataclass
class SessionMemory:
    session_id: str
    current_customer: str | None = None
    current_order: str | None = None
    current_ticket: str | None = None
    current_issue: str | None = None
    policy_refs: list[str] = field(default_factory=list)


SESSION_STORE: dict[str, SessionMemory] = {}


def get_session_memory(session_id: str) -> SessionMemory:
    if session_id not in SESSION_STORE:
        SESSION_STORE[session_id] = SessionMemory(session_id=session_id)
    return SESSION_STORE[session_id]


def clear_session_memory(session_id: str) -> None:
    SESSION_STORE.pop(session_id, None)
