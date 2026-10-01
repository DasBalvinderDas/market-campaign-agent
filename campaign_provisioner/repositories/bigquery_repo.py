"""BigQuery repository. Reads use views; every write is a parameterised DML INSERT
(or a status UPDATE) so results are immediately consistent for the next query."""
from datetime import datetime

from .base import Repository, new_id, now


class BigQueryRepository(Repository):
    def __init__(self, project: str, dataset: str, location: str = "US", client=None):
        from google.cloud import bigquery

        self._bq = bigquery
        self.client = client or bigquery.Client(project=project, location=location)
        self.ds = f"{project}.{dataset}"

    # ---- plumbing
    def _param(self, name, value):
        bq = self._bq
        if isinstance(value, bool):
            return bq.ScalarQueryParameter(name, "BOOL", value)
        if isinstance(value, int):
            return bq.ScalarQueryParameter(name, "INT64", value)
        if isinstance(value, float):
            return bq.ScalarQueryParameter(name, "FLOAT64", value)
        if isinstance(value, datetime):
            return bq.ScalarQueryParameter(name, "TIMESTAMP", value)
        return bq.ScalarQueryParameter(name, "STRING", value)

    def _run(self, sql: str, **params) -> list[dict]:
        sql = sql.replace("{ds}", self.ds)
        cfg = self._bq.QueryJobConfig(query_parameters=[self._param(k, v) for k, v in params.items()])
        return [dict(r) for r in self.client.query(sql, job_config=cfg).result()]

    # ---- inventory
    def list_catalog(self):
        return self._run("SELECT sku, name, category, free FROM `{ds}.v_inventory_available` ORDER BY sku")

    def get_availability(self, sku):
        rows = self._run("SELECT sku, name, on_hand, reserved, free FROM `{ds}.v_inventory_available` "
                         "WHERE sku = @sku", sku=sku)
        return rows[0] if rows else None

    def reserve(self, request_id, sku, quantity):
        self._run("INSERT INTO `{ds}.inventory_reservations` "
                  "(reservation_id, request_id, sku, quantity, status, created_at) "
                  "VALUES (@id, @request_id, @sku, @quantity, 'ACTIVE', @ts)",
                  id=new_id("RSV"), request_id=request_id, sku=sku, quantity=quantity, ts=now())

    def release_reservations(self, request_id):
        rows = self._run("SELECT IFNULL(SUM(quantity), 0) AS n FROM `{ds}.inventory_reservations` "
                         "WHERE request_id = @request_id AND status = 'ACTIVE'", request_id=request_id)
        self._run("UPDATE `{ds}.inventory_reservations` SET status = 'RELEASED' "
                  "WHERE request_id = @request_id AND status = 'ACTIVE'", request_id=request_id)
        return int(rows[0]["n"])

    # ---- procurement
    def get_quotes(self, sku):
        return self._run(
            "SELECT c.vendor_id, v.vendor_name AS vendor, c.unit_price, c.lead_time_days "
            "FROM `{ds}.vendor_catalog` c JOIN `{ds}.vendors` v USING (vendor_id) "
            "WHERE c.sku = @sku AND v.active ORDER BY c.unit_price", sku=sku)

    def get_vendor_price(self, vendor_id, sku):
        return next((q for q in self.get_quotes(sku) if q["vendor_id"] == vendor_id), None)

    # ---- budget / policy
    def list_budgets(self):
        return self._run("SELECT campaign_id, campaign_name, event_name, total_budget, spent, committed, remaining "
                         "FROM `{ds}.v_campaign_budget` ORDER BY campaign_id")

    def get_budget(self, campaign_id):
        rows = self._run("SELECT campaign_id, campaign_name, event_name, total_budget, spent, committed, remaining "
                         "FROM `{ds}.v_campaign_budget` WHERE campaign_id = @cid", cid=campaign_id)
        return rows[0] if rows else None

    def get_policy(self, amount):
        rows = self._run("SELECT tier, min_amount, max_amount, requires_human, approver_role "
                         "FROM `{ds}.approval_policy` WHERE @amount > min_amount AND @amount <= max_amount "
                         "ORDER BY min_amount LIMIT 1", amount=float(amount))
        if rows:
            return rows[0]
        return {"tier": "AUTO", "min_amount": 0.0, "max_amount": 0.0, "requires_human": False,
                "approver_role": "auto-policy"}

    def commit_budget(self, campaign_id, request_id, amount, approved_by):
        self._run("INSERT INTO `{ds}.budget_ledger` "
                  "(entry_id, campaign_id, request_id, entry_type, amount, approved_by, created_at) "
                  "VALUES (@id, @cid, @rid, 'COMMIT', @amount, @by, @ts)",
                  id=new_id("LED"), cid=campaign_id, rid=request_id, amount=float(amount), by=approved_by, ts=now())

    def get_headroom(self, request_id):
        rows = self._run("SELECT approved, ordered FROM `{ds}.v_request_headroom` WHERE request_id = @rid",
                         rid=request_id)
        return {"approved": float(rows[0]["approved"]), "ordered": float(rows[0]["ordered"])} if rows \
            else {"approved": 0.0, "ordered": 0.0}

    # ---- requests, POs, audit
    def create_request(self, campaign_id, summary):
        rid = new_id("REQ")
        self._run("INSERT INTO `{ds}.campaign_requests` (request_id, campaign_id, summary, created_at) "
                  "VALUES (@rid, @cid, @summary, @ts)", rid=rid, cid=campaign_id, summary=summary, ts=now())
        return rid

    def get_request(self, request_id):
        rows = self._run("SELECT request_id, campaign_id, summary FROM `{ds}.campaign_requests` "
                         "WHERE request_id = @rid", rid=request_id)
        return rows[0] if rows else None

    def record_po(self, po):
        self._run("INSERT INTO `{ds}.purchase_orders` (po_number, request_id, campaign_id, vendor_id, sku, quantity, "
                  "total_amount, status, integration_execution_id, created_at) "
                  "VALUES (@po, @rid, @cid, @vid, @sku, @qty, @total, @status, @exec, @ts)",
                  po=po["po_number"], rid=po["request_id"], cid=po["campaign_id"], vid=po["vendor_id"],
                  sku=po["sku"], qty=int(po["quantity"]), total=float(po["total_amount"]),
                  status=po["status"], exec=po.get("integration_execution_id"), ts=now())

    def log_audit(self, request_id, actor, action, details):
        self._run("INSERT INTO `{ds}.audit_log` (event_id, created_at, request_id, actor, action, details) "
                  "VALUES (@id, @ts, @rid, @actor, @action, @details)",
                  id=new_id("EVT"), ts=now(), rid=request_id, actor=actor, action=action,
                  details=self.dumps(details))

    def list_audit(self, request_id=None):
        rows = self._run("SELECT FORMAT_TIMESTAMP('%FT%TZ', created_at) AS created_at, request_id, actor, action, "
                         "details FROM `{ds}.audit_log` WHERE @rid IS NULL OR request_id = @rid "
                         "ORDER BY created_at LIMIT 200", rid=request_id)
        return rows
