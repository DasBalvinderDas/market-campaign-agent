"""Signed, expiring links for the approval email.

A link carries a token: base64url(JSON payload) + "." + HMAC-SHA256 signature. The payload names the approval, the
person who may use it, the action (approve / reject) and an expiry. Nobody needs to sign in: possession of the link
(sent to that person's mailbox) plus a valid signature is the credential. The service additionally checks that the
approval is still PENDING, so a link works once.
"""
import base64
import hashlib
import hmac
import json
import time
import uuid


class ApprovalLinkError(Exception):
    """The link is invalid, tampered with, or expired."""


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(secret: str, body: str) -> str:
    return _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())


def make_token(secret: str, approval_id: str, email: str, action: str, expires_at: float) -> str:
    if not secret:
        raise ApprovalLinkError("APPROVAL_LINK_SECRET is not set")
    if action not in ("approve", "reject"):
        raise ValueError("action must be approve or reject")
    payload = {"a": approval_id, "e": email.lower(), "x": action, "t": int(expires_at), "n": uuid.uuid4().hex[:8]}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    return f"{body}.{_sign(secret, body)}"


def verify_token(secret: str, token: str, now: float | None = None) -> dict:
    """Returns {"approval_id", "email", "action", "expires_at"} or raises ApprovalLinkError."""
    if not secret:
        raise ApprovalLinkError("the service has no APPROVAL_LINK_SECRET")
    try:
        body, signature = token.split(".", 1)
    except (ValueError, AttributeError):
        raise ApprovalLinkError("malformed link") from None
    if not hmac.compare_digest(_sign(secret, body), signature):
        raise ApprovalLinkError("invalid signature")
    try:
        p = json.loads(_unb64(body))
        result = {"approval_id": p["a"], "email": p["e"], "action": p["x"], "expires_at": int(p["t"])}
    except (ValueError, KeyError, TypeError):
        raise ApprovalLinkError("malformed link") from None
    if result["action"] not in ("approve", "reject"):
        raise ApprovalLinkError("malformed link")
    if (now if now is not None else time.time()) > result["expires_at"]:
        raise ApprovalLinkError("this link has expired")
    return result
