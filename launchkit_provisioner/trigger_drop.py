"""Drop one small file in a Cloud Storage bucket for every request that waits for approval.

A Gemini Enterprise workflow can start on that new file (an event trigger), so the approver's Inbox item appears when the request
is created, with nothing to start by hand. Off unless APPROVAL_TRIGGER_BUCKET is set. It never fails the order flow: a problem is
logged and the request still waits for approval in the chat and by email.

The file holds no email addresses and no names: only what the approver needs to decide.
"""
import json
import logging
from datetime import datetime, timezone

from . import config, presentation

log = logging.getLogger(__name__)


def object_name(request_id: str) -> str:
    return f"{config.APPROVAL_TRIGGER_PREFIX}{request_id}.json"


def build_payload(request_id: str, launch: dict, scenario: dict, amount: float, approver_role: str, now: datetime | None = None) -> dict:
    p = presentation
    return {"request_id": request_id, "event": "approval_waiting", "campaign": launch["launch_name"], "option": scenario["option_name"],
            "amount_usd": round(float(amount), 2), "arrives": str(scenario["delivery_date"]), "approver_role": approver_role,
            "summary": f"Approve request {request_id}: {scenario['option_name']}, {p.money(amount)}, arrives {p.day(scenario['delivery_date'])}",
            "created_at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")}


def _client():
    from google.cloud import storage
    return storage.Client()


def drop(payload: dict, client=None) -> str:
    """Write the file once. Returns the object name, or "" when it is off, already there, or failed."""
    if not config.APPROVAL_TRIGGER_BUCKET:
        return ""
    name = object_name(payload["request_id"])
    try:
        blob = (client or _client()).bucket(config.APPROVAL_TRIGGER_BUCKET).blob(name)
        # if_generation_match=0: only create. A second sign-off for the same request must not start the workflow again.
        blob.upload_from_string(json.dumps(payload, indent=2), content_type="application/json", if_generation_match=0)
        return name
    except Exception as exc:  # noqa: BLE001 - an existing file (412) or any storage problem must not stop the sign-off
        log.warning("approval trigger file %s not written: %s", name, str(exc)[:200])
        return ""
