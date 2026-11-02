"""Step 1 of the Inbox notification work: a harmless test the Gemini Enterprise workflow can call."""
from datetime import datetime, timezone

from .. import config
from ..repositories import get_repo

_ROLES = ("VP Product Marketing", "CMO")


def _mask(address: str) -> str:
    """da***@hcltech.com: enough to compare two addresses by eye, never the whole address."""
    name, _, domain = address.partition("@")
    return (name[:2] + "***" + ("@" + domain if domain else "")) if name else "(empty)"


def inbox_test(tool_context=None) -> dict:
    """The Inbox test. Call it when the user says "run the inbox test" (a Gemini Enterprise workflow sends this). It changes
    nothing. Show `display_markdown` exactly.
    """
    me = str(getattr(tool_context, "user_id", "") or "").strip().lower()
    known, listed = False, []
    try:
        repo = get_repo()
        for r in _ROLES:
            listed += [e.lower() for e in repo.get_approver_signins(r)]
        known = bool(me) and me in listed
    except Exception:  # noqa: BLE001 - the test must answer even if the data cannot be read
        pass
    when = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    shape = "an email address" if "@" in me else ("something else" if me else "nothing")
    first = f"📬 **Inbox test OK.** The agent ran at {when}."
    second = (f"🔐 Sign-in seen by the agent: **{shape}** ({_mask(me)}) · on the approver list: **{'yes' if known else 'no'}** · "
              f"approvals: **{config.APPROVAL_CHANNEL}**")
    third = ("🧾 Sign-ins allowed to approve (VP and CMO), masked: " + (", ".join(sorted({_mask(e) for e in listed})) or "empty")
             + f" · the sign-in is {len(me)} characters long")
    return {"status": "ok", "ran_at": when, "signed_in_as": shape, "is_approver": known, "channel": config.APPROVAL_CHANNEL,
            "display_markdown": f"{first}  \n{second}\n\n{third}"}
