"""Approval-link service: the page behind the Approve / Reject links in the approval email.

Public on the internet but not open: every link carries a signed, expiring token (campaign_provisioner/approval_links.py),
the approval must still be PENDING, and the person must be one of the configured approvers. Opening a link only shows
a confirmation page (email scanners open links automatically); the decision is taken by the button on that page (POST).
"""
import html
import os
from datetime import datetime, timezone

from flask import Flask, make_response, request

from campaign_provisioner import approval_flow, config
from campaign_provisioner.approval_links import ApprovalLinkError, verify_token
from campaign_provisioner.repositories import get_repo
from campaign_provisioner.workflow.integration_client import IntegrationExecutor

app = Flask(__name__)
_STYLE = ("body{font-family:system-ui,sans-serif;max-width:560px;margin:40px auto;padding:0 16px;color:#1f2937}"
          "h1{font-size:22px}.box{border:1px solid #d1d5db;border-radius:10px;padding:16px;margin:16px 0}"
          "button{font-size:16px;padding:10px 22px;border:0;border-radius:8px;color:#fff;cursor:pointer}"
          ".approve{background:#15803d}.reject{background:#b91c1c}.muted{color:#6b7280;font-size:14px}")


def _page(title: str, body: str, status: int = 200):
    resp = make_response(f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,"
                         f"initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style>"
                         f"<h1>{html.escape(title)}</h1>{body}", status)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


def _executor():
    return IntegrationExecutor()


def _load(token: str):
    """Returns (claims, approval) or raises ApprovalLinkError."""
    claims = verify_token(config.APPROVAL_LINK_SECRET, token)
    approval = get_repo().get_approval(claims["approval_id"])
    if not approval:
        raise ApprovalLinkError("this approval does not exist")
    if claims["email"] not in [e.strip().lower() for e in approval["approver_emails"].split(",")]:
        raise ApprovalLinkError("this link is not for an approver of this request")
    return claims, approval


def _summary_box(approval: dict) -> str:
    import json
    plan = json.loads(approval.get("plan") or "{}")
    items = "".join(f"<li>{int(l['quantity'])} x {html.escape(l['sku'])} from {html.escape(l['vendor'])}: "
                    f"USD {l['total']:,.2f}</li>" for l in plan.get("lines", []))
    return (f"<div class=box><b>{html.escape(approval['campaign_id'])}</b> &middot; request "
            f"{html.escape(approval['request_id'])}<ul>{items}</ul><b>Total: USD {float(approval['amount']):,.2f}</b>"
            f"<p class=muted>{html.escape(approval.get('justification') or '')}</p></div>")


@app.get("/healthz")
def healthz():
    return "ok"


@app.get("/decide")
def confirm_page():
    token = request.args.get("t", "")
    try:
        claims, approval = _load(token)
    except ApprovalLinkError as exc:
        return _page("Link not valid", f"<p>{html.escape(str(exc))}.</p>", 400)
    if approval["status"] != "PENDING":
        return _page("Already decided", f"<p>This request was already {html.escape(approval['status'].lower())}"
                                        f"{' by ' + html.escape(approval['decided_by']) if approval.get('decided_by') else ''}.</p>", 409)
    if approval["expires_at"] <= datetime.now(timezone.utc):
        return _page("Link expired", "<p>This approval request has expired. Ask for a new one.</p>", 410)
    action = claims["action"]
    label = "Approve" if action == "approve" else "Reject"
    return _page(f"{label} this request?", _summary_box(approval) +
                 f"<form method=post action=/decide><input type=hidden name=t value='{html.escape(token, quote=True)}'>"
                 f"<button class={action}>{label}</button></form><p class=muted>Signed in as nobody: this link "
                 f"identifies you as {html.escape(claims['email'])}.</p>")


@app.post("/decide")
def decide():
    token = request.form.get("t", "")
    try:
        claims, approval = _load(token)
    except ApprovalLinkError as exc:
        return _page("Link not valid", f"<p>{html.escape(str(exc))}.</p>", 400)
    repo = get_repo()
    status = "APPROVED" if claims["action"] == "approve" else "REJECTED"
    if not repo.decide_approval(approval["approval_id"], status, claims["email"]):
        current = repo.get_approval(approval["approval_id"]) or approval
        if current["status"] == "PENDING":
            return _page("Link expired", "<p>This approval request has expired. Ask for a new one.</p>", 410)
        return _page("Already decided", f"<p>This request was already {html.escape(current['status'].lower())}.</p>", 409)
    try:
        result = approval_flow.finalize(repo, _executor(), approval, claims["action"], claims["email"])
    except Exception as exc:  # noqa: BLE001 - the decision is stored; tell the person the follow-up needs attention
        repo.log_audit(approval["request_id"], "approval_service", "finalize_error", {"error": str(exc)[:300]})
        return _page("Decision recorded", "<p>Your decision was recorded, but the follow-up steps hit a problem. "
                                          "The team has been notified in the audit log.</p>", 500)
    if result["status"] == "rejected":
        return _page("Rejected", f"<p>Thank you. Nothing will be ordered; {result['released']} reserved units were released.</p>")
    if result["status"] == "failed":
        return _page("Could not approve", f"<p>{html.escape(result['message'])}</p>", 409)
    pos = "".join(f"<li>{html.escape(p['po_number'])}: {html.escape(p['sku'])}, USD {p['total']:,.2f}</li>" for p in result["pos"])
    problems = "".join(f"<li>{html.escape(f['sku'])}: {html.escape(f['error'])}</li>" for f in result["failed"])
    return _page("Approved", f"<p>Thank you. USD {result['amount']:,.2f} was approved.</p>"
                             f"{'<p>Purchase orders created:</p><ul>' + pos + '</ul>' if pos else ''}"
                             f"{'<p>These need attention:</p><ul>' + problems + '</ul>' if problems else ''}")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
