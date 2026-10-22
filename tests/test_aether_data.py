"""The Aether Athletics demo data: vendors and the items they hold, no campaign; consistent; plans as the demo expects; the script wipes then loads."""
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
    return aether_data.build()


@pytest.fixture
def aether_repo(data):
    repo = MemoryRepository()
    repo.t.update(data)
    for name in ("launch_requests", "requirement_lines", "scenarios", "scenario_lines", "decisions", "depot_holds",
                 "purchase_orders", "depot_transfers", "audit_log", "vendor_disruptions"):
        repo.t[name] = []
    return repo


def test_there_is_no_campaign_and_every_row_fits_its_table(data):
    assert data["launches"] == []
    for name, rows in data.items():
        cols = {c for c, *_ in TABLES[name]["columns"]}
        required = {c for c, _, mode, _ in TABLES[name]["columns"] if mode == "REQUIRED"}
        if name != "launches":
            assert rows, name
        for r in rows:
            assert set(r) <= cols and required <= set(r), (name, r)


def test_every_reference_exists_and_every_item_has_competing_vendors(data):
    skus = {a["sku"] for a in data["assets"]}
    vendors = {v["vendor_id"] for v in data["vendors"]}
    depots = {d["depot_id"] for d in data["depots"]}
    assert all(o["sku"] in skus and o["vendor_id"] in vendors for o in data["vendor_offers"])
    assert all(s["sku"] in skus and s["depot_id"] in depots for s in data["depot_stock"])
    by_sku = {}
    for o in data["vendor_offers"]:
        by_sku.setdefault(o["sku"], set()).add(o["vendor_id"])
    assert set(by_sku) == skus and all(len(v) >= 2 for v in by_sku.values())


def test_the_standing_athlete_list_has_the_registry_size_curve(data):
    guests = data["guests"]
    assert {g["launch_id"] for g in guests} == {aether_data.GUEST_LIST_ID} == {planner.STANDARD_GUEST_LIST}
    assert len(guests) == 120 and Counter(g["size"] for g in guests) == {"XS": 18, "S": 44, "M": 43, "L": 15}
    assert Counter(g["region"] for g in guests) == {"US": 70, "EMEA": 50}
    named = {g["name"]: (g["handle"], g["size"], g["region"]) for g in guests[:3]}
    assert named["Emily S."] == ("@emily_runs_fast", "S", "US") and named["Marcus T."][1:] == ("M", "EMEA")
    assert named["David K."] == ("@kenya_stride", "S", "EMEA")


def test_the_surplus_stock(data):
    stock = {(s["depot_id"], s["sku"]): s["on_hand"] for s in data["depot_stock"]}
    assert stock == {("DEPOT-BOS-01", "BOX-ACRYL-PREM-LID"): 50, ("DEPOT-PDX-02", "BINDER-CORK-ECO"): 100,
                     ("DEPOT-AMS-03", "DISP-PODIUM-CARB"): 0,
                     ("DEPOT-LON-04", "BANNER-ROLLUP-AETHER"): 40, ("DEPOT-LON-04", "TOTE-ORGANIC-ATHLETE"): 150,
                     ("DEPOT-SIN-05", "BANNER-ROLLUP-AETHER"): 30, ("DEPOT-SIN-05", "TOTE-ORGANIC-ATHLETE"): 200}


def test_every_place_has_a_warehouse_and_local_vendors(data):
    from launchkit_provisioner import presentation
    from launchkit_provisioner.repositories.memory_repo import MemoryRepository
    repo = MemoryRepository()
    repo.t.update(data)
    rows = {r[0]: r for r in presentation.venue_rows(repo)}
    assert "London Marketing Depot" in rows["London"][2] and "Thames Display Works" in rows["London"][1]
    assert "Singapore Asia-Pacific Hub" in rows["Singapore"][2] and "Merlion Signage" in rows["Singapore"][1]
    assert "Boston Distribution Hub" in rows["USA"][2]


def test_the_catalog_prices_and_lead_times_are_the_packs(data):
    best = {}
    for o in data["vendor_offers"]:
        if o["variant"] == "STANDARD":
            cur = best.get(o["sku"])
            if cur is None or o["unit_price"] < cur["unit_price"]:
                best[o["sku"]] = o
    for sku, price, lead in (("BOX-ACRYL-PREM-LID", 65.0, 10), ("SVC-LASER-ETCH", 20.0, 2), ("APP-SINGLET-M", 45.0, 8),
                             ("DISP-PODIUM-CARB", 380.0, 16), ("BINDER-CORK-ECO", 22.0, 7), ("PACK-NUTRITION-FLASK", 27.42, 4)):
        assert (best[sku]["unit_price"], best[sku]["lead_days"]) == (price, lead), sku


def test_a_new_campaign_gets_the_kits_sizes_from_the_standing_list_and_plans_into_three_options(aether_repo):
    aether_repo.create_launch({"launch_id": "EVT-NEW", "launch_name": aether_data.CAMPAIGN_NAME, "product_name": "x",
                               "cost_center": aether_data.COST_CENTER, "owner": "m", "in_hand_by": TODAY + timedelta(days=20),
                               "embargo_date": TODAY + timedelta(days=28)})
    rid = aether_repo.create_request("EVT-NEW", "demo")
    lines = planner.expand_bundles(aether_repo, "EVT-NEW", [
        {"bundle_type": "GUEST_KIT", "quantity": 120, "region": "US"}, {"bundle_type": "VENUE_DISPLAY", "quantity": 12, "region": "US"},
        {"bundle_type": "SALES_PACK", "quantity": 250, "region": "US"}])
    totals = Counter()
    for ln in lines:
        totals["APP-SINGLET" if ln["sku"].startswith("APP-SINGLET") else ln["sku"]] += ln["quantity"]
    assert totals == {"APP-SINGLET": 120, "BOX-ACRYL-PREM-LID": 120, "SVC-LASER-ETCH": 120, "PACK-NUTRITION-FLASK": 120,
                      "DISP-PODIUM-CARB": 12, "BINDER-CORK-ECO": 250, "FOAM-CUSHION-SAMPLE": 250}
    aether_repo.replace_requirement_lines(rid, lines)
    scenarios, scenario_lines = planner.plan_scenarios(aether_repo, rid, today=TODAY)
    by = {s["option_code"]: s for s in scenarios}
    best = next(s for s in scenarios if s["recommended"])
    assert best["option_code"] == "REBALANCE" and by["REBALANCE"]["total_cost"] <= by["FULL_NEW"]["total_cost"]
    assert 5000 < best["total_cost"] < 50000                                  # the VP signs off
    assert all(s["feasible"] and s["buffer_hours"] >= 24 for s in scenarios)
    taken = {(x["source_id"], x["sku"]): x["quantity"] for x in scenario_lines
             if x["scenario_id"] == best["scenario_id"] and x["source_type"] == "DEPOT"}
    assert taken == {("DEPOT-BOS-01", "BOX-ACRYL-PREM-LID"): 50, ("DEPOT-PDX-02", "BINDER-CORK-ECO"): 100}


def test_with_no_campaigns_the_assistant_says_so_and_asks_for_the_first_one():
    from launchkit_provisioner import presentation
    assert "no campaigns yet" in presentation.campaigns_markdown([])
    assert "name, the date, the city and the country" in presentation.capabilities_card([])


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


def _args(**kw):
    return demo.argparse.Namespace(**{"project": "p", "dataset": "d", "location": "US", "preview": False, "yes": False,
                                      "skip_preflight": True, **kw})


def _run(monkeypatch, *, answer="YES", yes=False):
    from google.cloud import bigquery
    client = _Client()
    monkeypatch.setattr(bigquery, "Client", lambda **k: client)
    monkeypatch.setattr("builtins.input", lambda *_: answer)
    demo.run(_args(yes=yes), project="p")
    return client


def test_the_script_empties_every_table_but_the_approvers_then_loads_the_data(monkeypatch):
    client = _run(monkeypatch)
    truncated = {q.split("`")[1].split(".")[-1] for q in client.queries if q.startswith("TRUNCATE")}
    assert truncated == set(TABLES) - {"approvers"}
    loaded = {n for n, _, _ in client.loads}
    assert loaded == {n for n, rows in aether_data.build().items() if rows} and "approvers" not in loaded and "launches" not in loaded
    assert all(w == "WRITE_TRUNCATE" for _, _, w in client.loads) and dict((n, c) for n, c, _ in client.loads)["guests"] == 120


def test_without_a_yes_nothing_is_changed(monkeypatch):
    with pytest.raises(SystemExit):
        _run(monkeypatch, answer="no")


def test_preview_changes_nothing_and_needs_no_project(capsys):
    demo.run(_args(project=None, preview=True), project="(preview)")
    out = capsys.readouterr().out
    assert "Use our stock first, buy the rest" in out and "<- recommended" in out and "not stored" in out


@pytest.mark.parametrize("today", [date(2026, 10, 8), date(2026, 10, 15), date(2026, 10, 17)])
def test_the_exact_brief_works_for_24_oct_from_a_week_or_more_before(aether_repo, today):
    """In hand 24 Oct and embargo 1 Nov, ordered on 8, 15 or 17 Oct: buying everything new at the standard lead times misses the date, the
    stock-first option is safe and recommended (express vendors keep it possible) and the VP approves it."""
    aether_repo.create_launch({"launch_id": "EVT-X", "launch_name": "x", "product_name": "x", "cost_center": "CC-GLOBAL-BRAND-4410",
                               "owner": "m", "in_hand_by": date(2026, 10, 24), "embargo_date": date(2026, 11, 1)})
    rid = aether_repo.create_request("EVT-X", "x")
    aether_repo.replace_requirement_lines(rid, planner.expand_bundles(aether_repo, "EVT-X", [
        {"bundle_type": "GUEST_KIT", "quantity": 120, "region": "US"}, {"bundle_type": "VENUE_DISPLAY", "quantity": 12, "region": "US"},
        {"bundle_type": "SALES_PACK", "quantity": 250, "region": "US"}]))
    scenarios, lines = planner.plan_scenarios(aether_repo, rid, today=today)
    by = {s["option_code"]: s for s in scenarios}
    best = next(s for s in scenarios if s["recommended"])
    assert by["FULL_NEW"]["buffer_hours"] < 0 or today == date(2026, 10, 8)        # on 8 Oct even the standard lead times are tight
    assert best["option_code"] == "REBALANCE" and best["buffer_hours"] >= 24 and best["feasible"]
    assert 5000 < best["total_cost"] < 50000
    depot = {(x["sku"]): x["quantity"] for x in lines if x["scenario_id"] == best["scenario_id"] and x["source_type"] == "DEPOT"}
    assert depot == {"BOX-ACRYL-PREM-LID": 50, "BINDER-CORK-ECO": 100}
