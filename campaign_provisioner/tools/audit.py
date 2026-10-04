"""Audit helper: writes to the audit_log table (BigQuery)."""
from ..repositories import get_repo


def audit(request_id, actor: str, action: str, **details) -> None:
    get_repo().log_audit(request_id, actor, action, details)
