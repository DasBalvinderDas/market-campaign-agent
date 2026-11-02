"""Step 1 of the Inbox notification work: a harmless test the Gemini Enterprise workflow can call."""
from datetime import datetime, timezone

from .. import config
from ..repositories import get_repo

_ROLES = ("VP Product Marketing", "CMO")


def inbox_test(tool_context=None) -> dict:
    """The Inbox test. Call it when the user says "run the inbox test" (a Gemini Enterprise workflow sends this). It changes
    nothing. Show `display_markdown` exactly.
    """
    me = str(getattr(tool_context, "user_id", "") or "").strip().lower()
    known = False
    try:
        repo = get_repo()
        known = bool(me) and any(me in [e.lower() for e in repo.get_approver_emails(r)] for r in _ROLES)
    except Exception:  # noqa: BLE001 - the test must answer even if the data cannot be read
        pass
    when = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    shape = "an email address" if "@" in me else ("something else" if me else "nothing")
    first = f"📬 **Inbox test OK.** The agent ran at {when}."
    second = f"🔐 Sign-in seen by the agent: **{shape}** · on the approver list: **{'yes' if known else 'no'}** · approvals: **{config.APPROVAL_CHANNEL}**"
    return {"status": "ok", "ran_at": when, "signed_in_as": shape, "is_approver": known, "channel": config.APPROVAL_CHANNEL,
            "display_markdown": f"{first}  \n{second}"}
