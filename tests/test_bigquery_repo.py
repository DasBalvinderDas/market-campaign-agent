"""BigQueryRepository against a stub client (no network): checks SQL targets and parameters."""
from campaign_provisioner.data import schema
from campaign_provisioner.repositories.bigquery_repo import BigQueryRepository


class _Job:
    def __init__(self, rows): self._rows = rows
    def result(self): return self._rows


class StubClient:
    def __init__(self, rows=None):
        self.rows, self.calls = rows or [], []

    def query(self, sql, job_config=None):
        params = {p.name: p.value for p in (job_config.query_parameters if job_config else [])}
        self.calls.append((sql, params))
        return _Job(self.rows)


def repo(rows=None):
    c = StubClient(rows)
    return BigQueryRepository("proj", "ds", client=c), c


def test_reads_use_views_and_dataset_qualified_names():
    r, c = repo([{"sku": "X", "name": "n", "on_hand": 1, "reserved": 0, "free": 1}])
    assert r.get_availability("X")["free"] == 1
    sql, params = c.calls[0]
    assert "`proj.ds.v_inventory_available`" in sql and params == {"sku": "X"}


def test_commit_budget_is_parameterised_insert():
    r, c = repo()
    r.commit_budget("NEXT27-MAIN", "REQ-1", 18000, "human:Marketing Director")
    sql, params = c.calls[0]
    assert sql.startswith("INSERT INTO `proj.ds.budget_ledger`") and "'COMMIT'" in sql
    assert params["amount"] == 18000.0 and params["cid"] == "NEXT27-MAIN"
    assert "NEXT27-MAIN" not in sql  # values never concatenated into SQL


def test_policy_falls_back_to_auto_when_no_row():
    r, _ = repo([])
    assert r.get_policy(10)["requires_human"] is False


def test_headroom_defaults_to_zero():
    r, _ = repo([])
    assert r.get_headroom("REQ-X") == {"approved": 0.0, "ordered": 0.0}


def test_schema_views_reference_only_defined_tables():
    for sql in schema.VIEWS.values():
        assert "{ds}" in sql
    assert {"budget_ledger", "purchase_orders"} <= set(schema.TABLES)


def test_approver_emails_query():
    r, c = repo([{"email": "a@x.com"}, {"email": "b@x.com"}])
    assert r.get_approver_emails("Marketing Director") == ["a@x.com", "b@x.com"]
    sql, params = c.calls[0]
    assert "`proj.ds.approvers`" in sql and "AND active" in sql and params == {"role": "Marketing Director"}
