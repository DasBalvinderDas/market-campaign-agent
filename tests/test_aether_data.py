"""The Aether Athletics demo data: consistent, plans into the three options the demo talks about, and the script wipes then loads."""
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import pytest

from launchkit_provisioner import planner
from launchkit_provisioner.data import aether_data
from launchkit_provisioner.data.schema import TABLES
from launchkit_provisioner.repositories.memory_repo import MemoryRepository

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import setup_demo_aether as demo  # noqa: E402

TODAY = date(2026, 10, 15)


@pytest.fixture
def data():
    return aether_data.build(TODAY)


@pytest.fixture
def aether_repo(data):
    repo = MemoryRepository()
    repo.t.update(data)
    for name in ("launch_requests", "requirement_lines", "scenarios", "scenario_lines", "decisions", "depot_holds",
                 "purchase_orders", "depot_transfers", "audit_log", "vendor_disruptions"):
        repo.t[name] = []
    return repo


def test_every_row_fits_its_table_and_every_reference_exists(data):
    for name, rows in data.items():
        cols = {c for c, *_ in TABLES[name]["columns"]}
        required = {c for c, _, mode, _ in TABLES[name]["columns"] if mode == "REQUIRED"}
        assert rows, name
        for r in rows:
            assert set(r) <= cols and required <= set(r), (name, r)
    skus = {a["sku"] for a in data["assets"]}
    vendors = {v["vendor_id"] for v in data["vendors"]}
    depots = {d["depot_id"] for d in data["depots"]}
    assert all(o["sku"] in skus and o["vendor_id"] in vendors for o in data["vendor_offers"])
    assert all(s["sku"] in skus and s["depot_id"] in depots for s in data["depot_stock"])
    by_sku = {}
    for o in data["vendor_offers"]:
        by_sku.setdefault(o["sku"], set()).add(o["vendor_id"])
    assert set(by_sku) == skus and all(len(v) >= 2 for v in by_sku.values())


def test_120_athletes_with_the_registry_size_curve(data):
    guests = data["guests"]
    assert len(guests) == 120 and Counter(g["size"] for g in guests) == {"XS": 18, "S": 44, "M": 43, "L": 15}
    assert Counter(g["region"] for g in guests) == {"US": 70, "EMEA": 50}
    named = {g["name"]: (g["handle"], g["size"], g["region"]) for g in guests[:3]}
    assert named["Emily S."] == ("@emily_runs_fast", "S", "US") and named["Marcus T."][1:] == ("M", "EMEA")
    assert named["David K."] == ("@kenya_stride", "S", "EMEA")


def test_the_campaign_and_the_surplus_stock(data):
    by_id = {x["launch_id"]: x for x in data["launches"]}
    a = by_id[aether_data.LAUNCH_ID]
    assert a["launch_name"] == "Aether Strider Pro Global Marathon Launch" and a["cost_center"] == "CC-GLOBAL-BRAND-4410"
    assert a["in_hand_by"] == TODAY + timedelta(days=20) and a["embargo_date"] == TODAY + timedelta(days=28)
    assert {"LAUNCH-LONDON", "LAUNCH-USA", "LAUNCH-SINGAPORE"} <= set(by_id) and "LAUNCH-SPRING" not in by_id
    stock = {(s["depot_id"], s["sku"]): s["on_hand"] for s in data["depot_stock"]}
    assert stock == {("DEPOT-BOS-01", "BOX-ACRYL-PREM-LID"): 50, ("DEPOT-PDX-02", "BINDER-CORK-ECO"): 100,
                     ("DEPOT-AMS-03", "DISP-PODIUM-CARB"): 0}
    exact = aether_data.build(TODAY, exact_dates=True)["launches"][0]
    assert exact["in_hand_by"] == date(2026, 10, 24) and exact["embargo_date"] == date(2026, 11, 1)


def test_the_catalog_prices_and_lead_times_are_the_packs(data):
    best = {}
    for o in data["vendor_offers"]:
        if o["variant"] == "STANDARD":
            cur = best.get(o["sku"])
            if cur is None or o["unit_price"] < cur["unit_price"]:
                best[o["sku"]] = o
    assert (best["BOX-ACRYL-PREM-LID"]["unit_price"], best["BOX-ACRYL-PREM-LID"]["lead_days"]) == (65.0, 10)
    assert (best["SVC-LASER-ETCH"]["unit_price"], best["SVC-LASER-ETCH"]["lead_days"]) == (20.0, 2)
    assert (best["APP-SINGLET-M"]["unit_price"], best["APP-SINGLET-M"]["lead_days"]) == (45.0, 8)
    assert (best["DISP-PODIUM-CARB"]["unit_price"], best["DISP-PODIUM-CARB"]["lead_days"]) == (380.0, 16)
    assert (best["BINDER-CORK-ECO"]["unit_price"], best["BINDER-CORK-ECO"]["lead_days"]) == (22.0, 7)
    assert (best["PACK-NUTRITION-FLASK"]["unit_price"], best["PACK-NUTRITION-FLASK"]["lead_days"]) == (27.42, 4)


def test_the_brief_plans_into_the_three_options(aether_repo):
    rid = aether_repo.create_request(aether_data.LAUNCH_ID, "demo")
    lines = planner.expand_bundles(aether_repo, aether_data.LAUNCH_ID, [
        {"bundle_type": "GUEST_KIT", "quantity": 120, "region": "US"}, {"bundle_type": "VENUE_DISPLAY", "quantity": 12, "region": "US"},
        {"bundle_type": "SALES_PACK", "quantity": 250, "region": "US"}])
    totals = Counter()
    for ln in lines:
        totals[ln["sku"].rsplit("-", 1)[0] if ln["sku"].startswith("APP-SINGLET") else ln["sku"]] += ln["quantity"]
    assert totals == {"APP-SINGLET": 120, "BOX-ACRYL-PREM-LID": 120, "SVC-LASER-ETCH": 120, "PACK-NUTRITION-FLASK": 120,
                      "DISP-PODIUM-CARB": 12, "BINDER-CORK-ECO": 250}
    aether_repo.replace_requirement_lines(rid, lines)
    scenarios, scenario_lines = planner.plan_scenarios(aether_repo, rid, today=TODAY)
    by = {s["option_code"]: s for s in scenarios}
    best = next(s for s in scenarios if s["recommended"])
    assert best["option_code"] == "REBALANCE" and by["REBALANCE"]["total_cost"] < by["FULL_NEW"]["total_cost"]
    assert 5000 < best["total_cost"] < 50000                                  # the VP signs off
    assert all(s["feasible"] and s["buffer_hours"] >= 24 for s in scenarios)
    taken = {(x["source_id"], x["sku"]): x["quantity"] for x in scenario_lines
             if x["scenario_id"] == best["scenario_id"] and x["source_type"] == "DEPOT"}
    assert taken == {("DEPOT-BOS-01", "BOX-ACRYL-PREM-LID"): 50, ("DEPOT-PDX-02", "BINDER-CORK-ECO"): 100}


class _Job:
    def result(self):
        return [{"n": 2}]


class _Client:
    def __init__(self):
        self.queries, self.loads = [], []

    def create_dataset(self, *a, **k):
        return None

    def query(self, sql):
        self.queries.append(sql)
        return _Job()

    def load_table_from_json(self, rows, table, job_config=None):
        self.loads.append((table.split(".")[-1], len(rows), job_config.write_disposition))
        return _Job()


def _run(monkeypatch, *, answer="YES", yes=False):
    from google.cloud import bigquery
    client = _Client()
    monkeypatch.setattr(bigquery, "Client", lambda **k: client)
    monkeypatch.setattr("builtins.input", lambda *_: answer)
    args = demo.argparse.Namespace(project="p", dataset="d", location="US", in_hand_days=20, exact_dates=False, preview=False,
                                   yes=yes, skip_preflight=True)
    demo.run(args, project="p")
    return client


def test_the_script_empties_every_table_but_the_approvers_then_loads_the_demo(monkeypatch):
    client = _run(monkeypatch)
    truncated = {q.split("`")[1].split(".")[-1] for q in client.queries if q.startswith("TRUNCATE")}
    assert truncated == set(TABLES) - {"approvers"}
    assert {name for name, _, _ in client.loads} == set(aether_data.build(TODAY)) and "approvers" not in {n for n, _, _ in client.loads}
    assert all(w == "WRITE_TRUNCATE" for _, _, w in client.loads) and dict((n, c) for n, c, _ in client.loads)["guests"] == 120


def test_without_a_yes_nothing_is_changed(monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, answer="no")


def test_preview_changes_nothing_and_needs_no_project(capsys):
    demo.run(demo.argparse.Namespace(project=None, dataset="d", location="US", in_hand_days=20, exact_dates=False, preview=True,
                                     yes=False, skip_preflight=True), project="(preview)")
    out = capsys.readouterr().out
    assert "Use our stock first, buy the rest" in out and "<- recommended" in out
