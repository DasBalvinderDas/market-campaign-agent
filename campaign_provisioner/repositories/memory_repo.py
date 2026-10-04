"""In-memory repository seeded from the same data as BigQuery (unit tests only)."""
import copy

from .. import approvers as approvers_cfg
from .. import config
from ..data.seed_data import SEED
from .base import Repository, new_id, now


class MemoryRepository(Repository):
    def __init__(self):
        self.t = copy.deepcopy(SEED)
        roles = [p['approver_role'] for p in self.t['approval_policy'] if p['requires_human']]
        self.t['approvers'] = approvers_cfg.expand(approvers_cfg.parse(config.APPROVER_EMAILS), roles)

    # ---- inventory
    def _reserved(self, sku):
        return sum(r["quantity"] for r in self.t["inventory_reservations"]
                   if r["sku"] == sku and r["status"] == "ACTIVE")

    def list_catalog(self):
        return [{"sku": i["sku"], "name": i["name"], "category": i["category"],
                 "free": i["on_hand"] - self._reserved(i["sku"])} for i in self.t["inventory_items"]]

    def get_availability(self, sku):
        for i in self.t["inventory_items"]:
            if i["sku"] == sku:
                res = self._reserved(sku)
                return {"sku": sku, "name": i["name"], "on_hand": i["on_hand"],
                        "reserved": res, "free": i["on_hand"] - res}
        return None

    def reserve(self, request_id, sku, quantity):
        self.t["inventory_reservations"].append(
            {"reservation_id": new_id("RSV"), "request_id": request_id, "sku": sku,
             "quantity": quantity, "status": "ACTIVE", "created_at": now()})

    def release_reservations(self, request_id):
        n = 0
        for r in self.t["inventory_reservations"]:
            if r["request_id"] == request_id and r["status"] == "ACTIVE":
                r["status"] = "RELEASED"; n += r["quantity"]
        return n

    # ---- procurement
    def get_quotes(self, sku):
        names = {v["vendor_id"]: v["vendor_name"] for v in self.t["vendors"] if v["active"]}
        return sorted(
            [{"vendor_id": c["vendor_id"], "vendor": names[c["vendor_id"]], "unit_price": c["unit_price"],
              "lead_time_days": c["lead_time_days"]}
             for c in self.t["vendor_catalog"] if c["sku"] == sku and c["vendor_id"] in names],
            key=lambda q: q["unit_price"])

    def get_vendor_price(self, vendor_id, sku):
        for q in self.get_quotes(sku):
            if q["vendor_id"] == vendor_id:
                return q
        return None

    # ---- budget
    def _budget_row(self, c):
        led = [l for l in self.t["budget_ledger"] if l["campaign_id"] == c["campaign_id"]]
        spent = sum(l["amount"] for l in led if l["entry_type"] == "SPEND")
        committed = sum(l["amount"] if l["entry_type"] == "COMMIT" else -l["amount"]
                        for l in led if l["entry_type"] in ("COMMIT", "RELEASE"))
        return {"campaign_id": c["campaign_id"], "campaign_name": c["campaign_name"],
                "event_name": c["event_name"], "total_budget": c["total_budget"],
                "spent": spent, "committed": committed,
                "remaining": c["total_budget"] - spent - committed}

    def list_budgets(self):
        return [self._budget_row(c) for c in self.t["campaigns"]]

    def get_budget(self, campaign_id):
        return next((b for b in self.list_budgets() if b["campaign_id"] == campaign_id), None)

    def get_policy(self, amount):
        for p in self.t["approval_policy"]:
            if p["min_amount"] < amount <= p["max_amount"]:
                return dict(p)
        return dict(self.t["approval_policy"][0])

    def commit_budget(self, campaign_id, request_id, amount, approved_by):
        self.t["budget_ledger"].append(
            {"entry_id": new_id("LED"), "campaign_id": campaign_id, "request_id": request_id,
             "entry_type": "COMMIT", "amount": amount, "approved_by": approved_by, "created_at": now()})

    def get_headroom(self, request_id):
        approved = sum(l["amount"] if l["entry_type"] == "COMMIT" else -l["amount"]
                       for l in self.t["budget_ledger"]
                       if l["request_id"] == request_id and l["entry_type"] in ("COMMIT", "RELEASE"))
        ordered = sum(p["total_amount"] for p in self.t["purchase_orders"]
                      if p["request_id"] == request_id and p["status"] == "CREATED")
        return {"approved": approved, "ordered": ordered}

    def get_approver_emails(self, role):
        return [a['email'] for a in self.t['approvers'] if a['approver_role'] == role and a['active']]

    # ---- requests, POs, audit
    def create_request(self, campaign_id, summary):
        rid = f"REQ-{len(self.t['campaign_requests']) + 1:03d}"
        self.t["campaign_requests"].append(
            {"request_id": rid, "campaign_id": campaign_id, "summary": summary, "created_at": now()})
        return rid

    def get_request(self, request_id):
        return next((r for r in self.t["campaign_requests"] if r["request_id"] == request_id), None)

    def record_po(self, po):
        self.t["purchase_orders"].append({**po, "created_at": now()})

    def log_audit(self, request_id, actor, action, details):
        self.t["audit_log"].append({"event_id": new_id("EVT"), "created_at": now(), "request_id": request_id,
                                    "actor": actor, "action": action, "details": self.dumps(details)})

    def list_audit(self, request_id=None):
        rows = [a for a in self.t["audit_log"] if request_id in (None, a["request_id"])]
        return [{**a, "created_at": a["created_at"].isoformat(timespec="seconds")} for a in rows]
