"""BigQuery repository. Reads use tables and views; every write is a parameterised DML statement, so results are
immediately consistent for the next query (no streaming buffer)."""
from datetime import date, datetime, timedelta

from ..data.schema import TABLES
from .base import Repository, new_id, now


class BigQueryRepository(Repository):
    def __init__(self, project: str, dataset: str, location: str = "US", client=None):
        from google.cloud import bigquery

        self._bq = bigquery
        self.client = client or bigquery.Client(project=project or None, location=location)
        self.ds = f"{project or self.client.project}.{dataset}"

    # ---- plumbing
    def _param(self, name, value, typ=None):
        bq = self._bq
        if typ:
            return bq.ScalarQueryParameter(name, typ, value)
        if isinstance(value, list):
            return bq.ArrayQueryParameter(name, "STRING", value)
        if isinstance(value, bool):
            return bq.ScalarQueryParameter(name, "BOOL", value)
        if isinstance(value, int):
            return bq.ScalarQueryParameter(name, "INT64", value)
        if isinstance(value, float):
            return bq.ScalarQueryParameter(name, "FLOAT64", value)
        if isinstance(value, datetime):
            return bq.ScalarQueryParameter(name, "TIMESTAMP", value)
        if isinstance(value, date):
            return bq.ScalarQueryParameter(name, "DATE", value)
        return bq.ScalarQueryParameter(name, "STRING", value)

    def _job(self, sql: str, params: list):
        return self.client.query(sql.replace("{ds}", self.ds), job_config=self._bq.QueryJobConfig(query_parameters=params))

    def _run(self, sql: str, **params) -> list[dict]:
        return [dict(r) for r in self._job(sql, [self._param(k, v) for k, v in params.items()]).result()]

    def _dml(self, sql: str, **params) -> int:
        job = self._job(sql, [self._param(k, v) for k, v in params.items()])
        job.result()
        return int(getattr(job, "num_dml_affected_rows", 0) or 0)

    def _insert(self, table: str, rows: list[dict]) -> None:
        """One multi-row INSERT with typed parameters, driven by the schema (column order and types)."""
        if not rows:
            return
        cols = [(c, typ) for c, typ, _m, _d in TABLES[table]["columns"]]
        params, values = [], []
        for i, row in enumerate(rows):
            names = []
            for c, typ in cols:
                name = f"{c}_{i}"
                names.append("@" + name)
                params.append(self._param(name, row.get(c), typ))
            values.append("(" + ", ".join(names) + ")")
        sql = f"INSERT INTO `{{ds}}.{table}` ({', '.join(c for c, _ in cols)}) VALUES " + ", ".join(values)
        self._job(sql, params).result()

    # ---- launches and requests
    def list_launches(self):
        return self._run("SELECT launch_id, launch_name, product_name, cost_center, embargo_date, in_hand_by, owner "
                         "FROM `{ds}.launches` ORDER BY launch_id")

    def get_launch(self, launch_id):
        rows = self._run("SELECT launch_id, launch_name, product_name, cost_center, embargo_date, in_hand_by, owner "
                         "FROM `{ds}.launches` WHERE launch_id = @lid", lid=launch_id)
        return rows[0] if rows else None

    def create_launch(self, launch):
        self._insert("launches", [launch])

    def update_launch_dates(self, launch_id, in_hand_by, embargo_date):
        self._dml("UPDATE `{ds}.launches` SET in_hand_by = @d, embargo_date = @e WHERE launch_id = @lid",
                  d=in_hand_by, e=embargo_date, lid=launch_id)

    def create_request(self, launch_id, summary):
        rid = new_id("REQ")
        self._insert("launch_requests", [{"request_id": rid, "launch_id": launch_id, "summary": summary,
                                          "created_at": now()}])
        return rid

    def get_request(self, request_id):
        rows = self._run("SELECT request_id, launch_id, summary FROM `{ds}.launch_requests` WHERE request_id = @rid",
                         rid=request_id)
        return rows[0] if rows else None

    # ---- brief decomposition
    def list_bundle_types(self):
        return [r["bundle_type"] for r in self._run(
            "SELECT DISTINCT bundle_type FROM `{ds}.bundle_templates` ORDER BY bundle_type")]

    def get_bundle_templates(self, bundle_type):
        return self._run("SELECT bundle_type, description, sku_pattern, qty_per_bundle, split_by, suggested_per_person "
                         "FROM `{ds}.bundle_templates` WHERE bundle_type = @bt ORDER BY sku_pattern", bt=bundle_type)

    def guest_mix(self, launch_id):
        return self._run("SELECT size, region, plug_type, COUNT(*) AS n FROM `{ds}.guests` WHERE launch_id = @lid "
                         "GROUP BY size, region, plug_type ORDER BY region, size, plug_type", lid=launch_id)

    def get_regional_split(self, bundle_type):
        return self._run("SELECT region, share_pct FROM `{ds}.regional_split` WHERE bundle_type = @bt ORDER BY region",
                         bt=bundle_type)

    def get_asset(self, sku):
        rows = self._run("SELECT sku, name, component_type, ship_factor FROM `{ds}.assets` WHERE sku = @sku", sku=sku)
        return rows[0] if rows else None

    def list_assets(self):
        return self._run("SELECT sku, name, component_type, ship_factor, suggested_per_person FROM `{ds}.assets` ORDER BY sku")

    def list_venues(self):
        return self._run("SELECT venue_id, venue_name, country, region, served_from FROM `{ds}.venues` ORDER BY venue_id")

    def list_date_pricing(self):
        return self._run("SELECT vendor_id, min_days_ahead, price_factor, label FROM `{ds}.vendor_date_pricing` "
                         "ORDER BY vendor_id, min_days_ahead DESC")

    def replace_requirement_lines(self, request_id, lines):
        self._dml("DELETE FROM `{ds}.requirement_lines` WHERE request_id = @rid", rid=request_id)
        ts = now()
        self._insert("requirement_lines", [{**ln, "request_id": request_id, "line_no": i, "created_at": ts}
                                           for i, ln in enumerate(lines, start=1)])

    def get_requirement_lines(self, request_id):
        return self._run("SELECT request_id, line_no, bundle_type, channel, sku, region, quantity "
                         "FROM `{ds}.requirement_lines` WHERE request_id = @rid ORDER BY line_no", rid=request_id)

    # ---- sourcing data
    def get_planning_rules(self):
        return {r["rule_key"]: float(r["rule_value"]) for r in self._run(
            "SELECT rule_key, rule_value FROM `{ds}.planning_rules`")}

    def get_lanes(self):
        return {(r["from_region"], r["to_region"]): {"days": int(r["days"]), "cost_per_unit": float(r["cost_per_unit"])}
                for r in self._run("SELECT from_region, to_region, days, cost_per_unit FROM `{ds}.transit_lanes`")}

    def list_vendor_offers(self, sku):
        return self._run(
            "SELECT o.vendor_id, v.vendor_name, v.home_region, o.variant, o.unit_price, o.lead_days, o.carbon_kg, "
            "IFNULL(d.delay_days, 0) AS delay_days "
            "FROM `{ds}.vendor_offers` o JOIN `{ds}.vendors` v ON v.vendor_id = o.vendor_id "
            "LEFT JOIN (SELECT vendor_id, SUM(delay_days) AS delay_days FROM `{ds}.vendor_disruptions` "
            "WHERE active GROUP BY vendor_id) d ON d.vendor_id = o.vendor_id "
            "WHERE o.sku = @sku AND v.active", sku=sku)

    def list_vendor_offers_all(self):
        return self._run(
            "SELECT o.sku, o.vendor_id, v.vendor_name, v.home_region, o.variant, o.unit_price, o.lead_days, o.carbon_kg, "
            "IFNULL(d.delay_days, 0) AS delay_days "
            "FROM `{ds}.vendor_offers` o JOIN `{ds}.vendors` v ON v.vendor_id = o.vendor_id "
            "LEFT JOIN (SELECT vendor_id, SUM(delay_days) AS delay_days FROM `{ds}.vendor_disruptions` "
            "WHERE active GROUP BY vendor_id) d ON d.vendor_id = o.vendor_id WHERE v.active")

    def depot_free(self, sku):
        return self._run("SELECT depot_id, depot_name, region, free FROM `{ds}.v_depot_available` "
                         "WHERE sku = @sku ORDER BY depot_id", sku=sku)

    def get_vendor(self, vendor_id):
        rows = self._run("SELECT vendor_id, vendor_name, home_region, active FROM `{ds}.vendors` "
                         "WHERE vendor_id = @vid", vid=vendor_id)
        return rows[0] if rows else None

    def list_vendors(self):
        return self._run("SELECT vendor_id, vendor_name, home_region, active FROM `{ds}.vendors` WHERE active "
                         "ORDER BY vendor_id")

    def list_depot_free(self):
        return self._run("SELECT depot_id, depot_name, region, sku, on_hand, free FROM `{ds}.v_depot_available` "
                         "ORDER BY depot_id, sku")

    def add_disruption(self, vendor_id, delay_days, reason):
        did = new_id("DSR")
        self._insert("vendor_disruptions", [{"disruption_id": did, "vendor_id": vendor_id, "delay_days": int(delay_days),
                                             "reason": reason, "active": True, "created_at": now()}])
        return did

    def list_disruptions(self):
        return self._run("SELECT disruption_id, vendor_id, delay_days, reason FROM `{ds}.vendor_disruptions` "
                         "WHERE active ORDER BY created_at")

    # ---- scenarios
    def replace_scenarios(self, request_id, scenarios, lines):
        self._dml("DELETE FROM `{ds}.scenario_lines` WHERE request_id = @rid", rid=request_id)
        self._dml("DELETE FROM `{ds}.scenarios` WHERE request_id = @rid", rid=request_id)
        ts = now()
        self._insert("scenarios", [{**s, "created_at": ts} for s in scenarios])
        self._insert("scenario_lines", lines)

    _SCENARIO_COLS = ("scenario_id, request_id, option_code, option_name, total_cost, shipping_cost, savings_usd, "
                      "delivery_date, buffer_hours, carbon_kg, risk, feasible, recommended, summary")

    def get_scenarios(self, request_id):
        return self._run(f"SELECT {self._SCENARIO_COLS} FROM `{{ds}}.scenarios` WHERE request_id = @rid ORDER BY "
                         "CASE option_code WHEN 'FULL_NEW' THEN 0 WHEN 'REBALANCE' THEN 1 ELSE 2 END", rid=request_id)

    def get_scenario(self, scenario_id):
        rows = self._run(f"SELECT {self._SCENARIO_COLS} FROM `{{ds}}.scenarios` WHERE scenario_id = @sid",
                         sid=scenario_id)
        return rows[0] if rows else None

    def get_scenario_lines(self, scenario_id):
        return self._run("SELECT line_id, scenario_id, request_id, channel, sku, region, quantity, source_type, "
                         "source_id, variant, unit_price, shipping_cost, line_total, days_to_deliver, carbon_kg, "
                         "execution_status FROM `{ds}.scenario_lines` WHERE scenario_id = @sid ORDER BY line_id",
                         sid=scenario_id)

    def mark_line_executed(self, line_id):
        self.mark_lines_executed([line_id])

    def mark_lines_executed(self, line_ids):
        if line_ids:
            self._dml("UPDATE `{ds}.scenario_lines` SET execution_status = 'EXECUTED' WHERE line_id IN UNNEST(@ids)",
                      ids=list(line_ids))

    # ---- sign-off
    def get_policy(self, amount):
        rows = self._run("SELECT tier, min_amount, max_amount, requires_human, approver_role "
                         "FROM `{ds}.approval_policy` WHERE @amount > min_amount AND @amount <= max_amount "
                         "ORDER BY min_amount LIMIT 1", amount=float(amount))
        if rows:
            return rows[0]
        return {"tier": "AUTOPILOT", "min_amount": 0.0, "max_amount": 0.0, "requires_human": False,
                "approver_role": "launch-autopilot"}

    def list_policies(self):
        return self._run("SELECT tier, min_amount, max_amount, requires_human, approver_role "
                         "FROM `{ds}.approval_policy` ORDER BY min_amount")

    def get_approver_emails(self, role):
        rows = self._run("SELECT email FROM `{ds}.approvers` WHERE approver_role = @role AND active ORDER BY email",
                         role=role)
        return [r["email"] for r in rows]

    _DECISION_COLS = ("decision_id, request_id, scenario_id, option_code, tier, approver_role, approver_emails, amount, "
                      "justification, status, created_at, expires_at, decided_by, decided_at, decision_note")

    def create_decision(self, decision):
        self._insert("decisions", [{"status": "PENDING", "created_at": now(), **decision}])

    def get_decision(self, decision_id):
        rows = self._run(f"SELECT {self._DECISION_COLS} FROM `{{ds}}.decisions` WHERE decision_id = @id", id=decision_id)
        return rows[0] if rows else None

    def get_decision_for_request(self, request_id):
        rows = self._run(f"SELECT {self._DECISION_COLS} FROM `{{ds}}.decisions` WHERE request_id = @rid "
                         "ORDER BY created_at DESC LIMIT 1", rid=request_id)
        return rows[0] if rows else None

    def list_pending_decisions(self):
        return self._run(f"SELECT {self._DECISION_COLS} FROM `{{ds}}.decisions` WHERE status = 'PENDING' "
                         "AND expires_at > CURRENT_TIMESTAMP() ORDER BY created_at")

    def decide(self, decision_id, status, decided_by, note=""):
        """Atomic: only the first decision on a PENDING, unexpired sign-off wins."""
        affected = self._dml("UPDATE `{ds}.decisions` SET status = @status, decided_by = @by, decided_at = @ts, "
                             "decision_note = @note WHERE decision_id = @id AND status = 'PENDING' "
                             "AND expires_at > @ts", status=status, by=decided_by, ts=now(), note=note, id=decision_id)
        return affected > 0

    def set_decision_note(self, decision_id, status, note):
        self._dml("UPDATE `{ds}.decisions` SET status = @status, decision_note = @note WHERE decision_id = @id",
                  status=status, note=note, id=decision_id)

    # ---- surplus stock holds
    def create_holds(self, holds):
        ts = now()
        self._insert("depot_holds", [{"hold_id": new_id("HLD"), "status": "ACTIVE", "created_at": ts, **h}
                                     for h in holds])

    def release_holds(self, request_id):
        rows = self._run("SELECT IFNULL(SUM(quantity), 0) AS n FROM `{ds}.depot_holds` "
                         "WHERE request_id = @rid AND status = 'ACTIVE'", rid=request_id)
        self._dml("UPDATE `{ds}.depot_holds` SET status = 'RELEASED' WHERE request_id = @rid AND status = 'ACTIVE'",
                  rid=request_id)
        return int(rows[0]["n"])

    def consume_hold(self, line_id):
        self.consume_holds([line_id])

    def consume_holds(self, line_ids):
        if line_ids:
            self._dml("UPDATE `{ds}.depot_holds` SET status = 'CONSUMED' WHERE line_id IN UNNEST(@ids) "
                      "AND status = 'ACTIVE'", ids=list(line_ids))

    # ---- execution records
    def record_pos(self, pos):
        ts = now()
        self._insert("purchase_orders", [{**po, "created_at": ts} for po in pos])

    def record_transfers(self, transfers):
        ts = now()
        self._insert("depot_transfers", [{**t, "created_at": ts} for t in transfers])

    def list_pos(self, request_id):
        return self._run("SELECT po_number, line_id, vendor_id, sku, region, quantity, total_amount, status "
                         "FROM `{ds}.purchase_orders` WHERE request_id = @rid ORDER BY created_at, po_number",
                         rid=request_id)

    def list_transfers(self, request_id):
        return self._run("SELECT transfer_number, line_id, depot_id, sku, region, quantity, status "
                         "FROM `{ds}.depot_transfers` WHERE request_id = @rid ORDER BY created_at, transfer_number",
                         rid=request_id)

    def list_readiness(self, launch_id=None):
        return self._run("SELECT request_id, launch_id, launch_name, in_hand_by, embargo_date, chosen_option, "
                         "decision_status, tier, authorised_amount, delivery_date, buffer_hours, readiness, "
                         "lines_executed, lines_total FROM `{ds}.v_launch_readiness` "
                         "WHERE @lid IS NULL OR launch_id = @lid ORDER BY request_id", lid=launch_id)

    # ---- audit
    def log_audit(self, request_id, actor, action, details):
        self._insert("audit_log", [{"event_id": new_id("EVT"), "created_at": now(), "request_id": request_id,
                                    "actor": actor, "action": action, "details": self.dumps(details)}])

    def log_audit_batch(self, request_id, events):
        ts = now()
        self._insert("audit_log", [{"event_id": new_id("EVT"), "created_at": ts + timedelta(microseconds=i),
                                    "request_id": request_id, "actor": a, "action": act, "details": self.dumps(d)}
                                   for i, (a, act, d) in enumerate(events)])

    def list_audit(self, request_id=None):
        return self._run("SELECT FORMAT_TIMESTAMP('%FT%TZ', created_at) AS created_at, request_id, actor, action, "
                         "details FROM `{ds}.audit_log` WHERE @rid IS NULL OR request_id = @rid "
                         "ORDER BY created_at LIMIT 200", rid=request_id)
