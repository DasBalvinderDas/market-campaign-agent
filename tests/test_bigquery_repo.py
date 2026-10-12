"""BigQueryRepository against a stub client (no network): checks SQL targets, parameters and syntax."""
from datetime import date, datetime, timezone

import pytest

from launchkit_provisioner.data import schema
from launchkit_provisioner.repositories.bigquery_repo import BigQueryRepository


class _Job:
    def __init__(self, rows): self._rows = rows; self.num_dml_affected_rows = 1
    def result(self): return self._rows


class StubClient:
    def __init__(self, rows=None):
        self.rows, self.calls = rows or [], []

    def query(self, sql, job_config=None):
        params = {p.name: (getattr(p, "type_", None) or f"ARRAY<{p.array_type}>", getattr(p, "value", None) or getattr(p, "values", None))
                  for p in (job_config.query_parameters if job_config else [])}
        self.calls.append((sql, params))
        return _Job(self.rows)


def repo(rows=None):
    c = StubClient(rows)
    return BigQueryRepository("proj", "ds", client=c), c


def test_reads_use_dataset_qualified_names_and_parameters():
    r, c = repo([{"depot_id": "D", "depot_name": "n", "region": "EMEA", "free": 5}])
    assert r.depot_free("PKG")[0]["free"] == 5
    sql, params = c.calls[0]
    assert "`proj.ds.v_depot_available`" in sql and params == {"sku": ("STRING", "PKG")}


def test_policy_falls_back_to_autopilot_when_no_row():
    r, _ = repo([])
    assert r.get_policy(10)["requires_human"] is False


def test_approver_emails_query():
    r, c = repo([{"email": "a@x.com"}, {"email": "b@x.com"}])
    assert r.get_approver_emails("CMO") == ["a@x.com", "b@x.com"]
    sql, params = c.calls[0]
    assert "`proj.ds.approvers`" in sql and "AND active" in sql and params == {"role": ("STRING", "CMO")}


def test_multi_row_insert_is_one_typed_parameterised_statement():
    r, c = repo()
    ts = datetime(2026, 10, 1, tzinfo=timezone.utc)
    r.replace_scenarios("REQ-1", [{
        "scenario_id": "REQ-1-RB", "request_id": "REQ-1", "option_code": "REBALANCE", "option_name": "Smart",
        "total_cost": 100.5, "shipping_cost": 5.0, "savings_usd": 10.0, "delivery_date": date(2026, 11, 2),
        "buffer_hours": 72, "carbon_kg": 3.5, "risk": "LOW", "feasible": True, "recommended": True,
        "summary": "s"}], [])
    deletes = [s for s, _ in c.calls if s.startswith("DELETE")]
    assert len(deletes) == 2 and "scenario_lines" in deletes[0]
    sql, params = next((s, p) for s, p in c.calls if s.startswith("INSERT INTO `proj.ds.scenarios`"))
    assert "VALUES (" in sql and "REQ-1-RB" not in sql                       # values are parameters, never in the SQL text
    assert params["delivery_date_0"] == ("DATE", date(2026, 11, 2)) and params["buffer_hours_0"] == ("INT64", 72)
    assert params["feasible_0"] == ("BOOL", True) and params["total_cost_0"] == ("FLOAT64", 100.5)
    assert params["created_at_0"][0] == "TIMESTAMP"


def test_insert_of_several_rows_numbers_the_parameters():
    r, c = repo()
    r.replace_requirement_lines("REQ-1", [{"bundle_type": "SALES_PACK", "channel": "SALES", "sku": "A", "region": "US", "quantity": 1},
                                          {"bundle_type": "SALES_PACK", "channel": "SALES", "sku": "B", "region": "US", "quantity": 2}])
    sql, params = next((s, p) for s, p in c.calls if s.startswith("INSERT"))
    assert sql.count("(@request_id_") == 2 and params["line_no_1"] == ("INT64", 2) and params["sku_1"] == ("STRING", "B")


def test_missing_values_become_typed_nulls():
    r, c = repo()
    r.create_decision({"decision_id": "D", "request_id": "R", "scenario_id": "S", "option_code": "ECO", "tier": "VP",
                       "approver_role": "VP", "approver_emails": "a@x.com", "amount": 1.0, "justification": "j",
                       "expires_at": datetime(2027, 1, 1, tzinfo=timezone.utc)})
    _sql, params = c.calls[0]
    assert params["decided_at_0"] == ("TIMESTAMP", None) and params["decision_note_0"] == ("STRING", None)
    assert params["status_0"] == ("STRING", "PENDING")


def test_every_query_is_valid_bigquery_sql():
    sqlglot = pytest.importorskip("sqlglot")
    r, c = repo([{"n": 0, "request_id": "R", "decision_id": "D", "bundle_type": "B", "rule_key": "K", "rule_value": 1.0,
                  "from_region": "US", "to_region": "US", "days": 1, "cost_per_unit": 1.0, "email": "a@x.com"}])
    ts = datetime(2027, 1, 1, tzinfo=timezone.utc)
    r.list_launches(); r.get_launch("L"); r.create_request("L", "s"); r.get_request("R")
    r.list_bundle_types(); r.get_bundle_templates("B"); r.guest_mix("L"); r.get_regional_split("B"); r.get_asset("S")
    r.replace_requirement_lines("R", [{"bundle_type": "B", "channel": "C", "sku": "S", "region": "US", "quantity": 1}])
    r.get_requirement_lines("R"); r.get_planning_rules(); r.get_lanes(); r.list_vendor_offers("S"); r.depot_free("S")
    r.get_vendor("V"); r.list_vendors(); r.list_depot_free(); r.add_disruption("V", 2, "r"); r.list_disruptions()
    r.get_scenarios("R"); r.get_scenario("S"); r.get_scenario_lines("S"); r.mark_line_executed("L")
    r.get_policy(1.0); r.list_policies(); r.get_approver_emails("CMO")
    r.create_decision({"decision_id": "D", "request_id": "R", "scenario_id": "S", "option_code": "ECO", "tier": "T",
                       "approver_role": "VP", "amount": 1.0, "expires_at": ts})
    r.get_decision("D"); r.get_decision_for_request("R"); r.decide("D", "APPROVED", "x"); r.set_decision_note("D", "FAILED", "n")
    r.create_holds([{"request_id": "R", "scenario_id": "S", "line_id": "L", "depot_id": "D", "sku": "S", "quantity": 1}])
    r.release_holds("R"); r.consume_hold("L")
    r.record_pos([{"po_number": "P", "request_id": "R", "line_id": "L", "vendor_id": "V", "sku": "S", "region": "US",
                   "quantity": 1, "total_amount": 1.0, "status": "CREATED"}])
    r.record_transfers([{"transfer_number": "T", "request_id": "R", "line_id": "L", "depot_id": "D", "sku": "S",
                         "region": "US", "quantity": 1, "status": "CREATED"}])
    r.mark_lines_executed(["L1", "L2"]); r.consume_holds(["L1"]); r.list_assets(); r.list_vendor_offers_all()
    r.log_audit_batch("R", [("a", "x", {}), ("a", "y", {})])
    r.list_pos("R"); r.list_transfers("R"); r.list_readiness(None); r.log_audit("R", "a", "b", {}); r.list_audit(None)
    assert len(c.calls) > 40
    for sql, _ in c.calls:
        sqlglot.parse_one(sql.replace("{ds}", "p.d"), read="bigquery")
    decide_sql = next(s for s, _ in c.calls if s.startswith("UPDATE") and "decided_by" in s)
    assert "status = 'PENDING'" in decide_sql and "expires_at > @ts" in decide_sql       # atomic: the first decision wins


def test_views_and_ddl_are_valid_and_cover_the_schema():
    sqlglot = pytest.importorskip("sqlglot")
    for name, sql in schema.VIEWS.items():
        sqlglot.parse_one(sql.replace("{ds}", "p.d"), read="bigquery")
    for t in schema.TRANSACTION_TABLES:
        assert t in schema.TABLES
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import setup_bigquery
    ddl = setup_bigquery.ddl("p.d")
    for stmt in [x for x in ddl.split(";\n") if x.strip() and not x.strip().startswith("--")]:
        sqlglot.parse_one(stmt, read="bigquery")
    assert all(f"`p.d.{t}`" in ddl for t in schema.TABLES) and all(f"`p.d.{v}`" in ddl for v in schema.VIEWS)


def test_every_repository_method_is_implemented_by_both_backends():
    from launchkit_provisioner.repositories.base import Repository
    from launchkit_provisioner.repositories.memory_repo import MemoryRepository
    names = [n for n, v in vars(Repository).items() if callable(v) and not n.startswith("_") and n != "dumps"]
    for cls in (MemoryRepository, BigQueryRepository):
        missing = [n for n in names if getattr(cls, n) is getattr(Repository, n)]
        assert not missing, (cls.__name__, missing)


def test_bulk_writes_are_single_statements_with_array_parameters():
    r, c = repo()
    r.mark_lines_executed(["A", "B", "C"])
    r.consume_holds(["A", "B"])
    r.mark_lines_executed([])                       # nothing to do: no query
    r.log_audit_batch("R", [("a", "x", {"k": 1}), ("a", "y", {})])
    assert len(c.calls) == 3
    upd, params = c.calls[0]
    assert "IN UNNEST(@ids)" in upd and params["ids"] == ("ARRAY<STRING>", ["A", "B", "C"])
    ins, params = c.calls[2]
    assert ins.count("(@event_id_") == 2 and params["created_at_1"][1] > params["created_at_0"][1]   # kept in order


def test_the_planner_reads_catalog_offers_and_stock_in_bulk():
    r, c = repo([])
    from datetime import date
    from launchkit_provisioner import planner
    ctx_calls = []
    class Spy(BigQueryRepository):
        def _run(self, sql, **p):
            ctx_calls.append(sql)
            return super()._run(sql, **p)
    s = Spy("proj", "ds", client=StubClient([]))
    ctx = planner._Ctx.__new__(planner._Ctx)
    ctx.repo, ctx._offers, ctx._assets, ctx._depots = s, None, None, None
    ctx.offers("A"); ctx.offers("B"); ctx.depots("A"); ctx.depots("B")
    with pytest.raises(planner.PlanError):
        ctx.asset("A"); ctx.asset("B")
    assert len(ctx_calls) == 3                       # one query each, not one per SKU
