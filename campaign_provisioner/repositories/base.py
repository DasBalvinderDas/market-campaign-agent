"""Repository contract: the only data-access surface the agents' tools depend on."""
import json
import uuid
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def _tokens(text: str) -> set:
    return {w.rstrip("s") for w in text.lower().replace("-", " ").split() if len(w) > 1}


class Repository:
    """Implemented by MemoryRepository (offline/tests) and BigQueryRepository."""

    # ---- inventory
    def list_catalog(self) -> list[dict]: raise NotImplementedError
    def get_availability(self, sku: str) -> dict | None: raise NotImplementedError
    def reserve(self, request_id: str, sku: str, quantity: int) -> None: raise NotImplementedError
    def release_reservations(self, request_id: str) -> int: raise NotImplementedError

    # ---- procurement
    def get_quotes(self, sku: str) -> list[dict]: raise NotImplementedError
    def get_vendor_price(self, vendor_id: str, sku: str) -> dict | None: raise NotImplementedError

    # ---- budget / policy
    def list_budgets(self) -> list[dict]: raise NotImplementedError
    def get_budget(self, campaign_id: str) -> dict | None: raise NotImplementedError
    def get_policy(self, amount: float) -> dict: raise NotImplementedError
    def commit_budget(self, campaign_id: str, request_id: str, amount: float, approved_by: str) -> None: raise NotImplementedError
    def get_headroom(self, request_id: str) -> dict: raise NotImplementedError

    def get_approver_emails(self, role: str) -> list[str]: raise NotImplementedError

    # ---- requests, POs, audit
    def create_request(self, campaign_id: str, summary: str) -> str: raise NotImplementedError
    def get_request(self, request_id: str) -> dict | None: raise NotImplementedError
    def record_po(self, po: dict) -> None: raise NotImplementedError
    def log_audit(self, request_id: str | None, actor: str, action: str, details: dict) -> None: raise NotImplementedError
    def list_audit(self, request_id: str | None = None) -> list[dict]: raise NotImplementedError

    # ---- shared logic
    def find_items(self, description: str) -> list[dict]:
        wanted = _tokens(description)
        scored = []
        for item in self.list_catalog():
            score = len(wanted & _tokens(f"{item['sku']} {item['name']}"))
            if score:
                scored.append((score, item))
        scored.sort(key=lambda t: -t[0])
        return [i for _, i in scored]

    @staticmethod
    def dumps(details: dict) -> str:
        return json.dumps(details, default=str, sort_keys=True)
