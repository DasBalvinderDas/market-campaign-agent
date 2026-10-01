"""Append-only audit trail kept in session state (maps to Cloud Logging in prod)."""
from datetime import datetime, timezone


def audit(state, actor: str, action: str, **details) -> None:
    trail = list(state.get("audit_trail", []))
    trail.append({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "actor": actor, "action": action, **details})
    state["audit_trail"] = trail
