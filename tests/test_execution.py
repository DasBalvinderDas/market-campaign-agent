from launchkit_provisioner import config, decision_flow, execution

from conftest import FakeExecutor


def approve(repo, rid, option="2"):
    repo.t["approvers"] += [{"approver_role": "Launch Team", "email": "team@example.com", "active": True},
                            {"approver_role": "Launch Team", "email": "team2@example.com", "active": True}]
    ex = FakeExecutor()
    decision_flow.authorize(repo, ex, rid, option, "")
    ex.execution = {"executionDetails": {"state": "SUCCEEDED"}}
    ex.suspensions = [{"state": "LIFTED"}]
    decision_flow.status(repo, rid, ex)
    ex.calls.clear()
    return ex


def test_nothing_is_ordered_without_an_approved_sign_off(repo, aurora):
    ex = FakeExecutor()
    assert execution.execute_plan(repo, ex, aurora)["status"] == "error"          # no decision at all
    decision_flow.authorize(repo, ex, aurora, "2", "")
    out = execution.execute_plan(repo, ex, aurora)                                # pending
    assert out["status"] == "BLOCKED" and not repo.list_pos(aurora) and not repo.list_transfers(aurora)
    assert [c for c in ex.calls if c[0] in (config.PO_TRIGGER, config.TRANSFER_TRIGGER)] == []
    assert "execution_blocked" in [a["action"] for a in repo.list_audit(aurora)]


def test_approved_plan_places_every_line_and_tells_the_team(repo, aurora):
    ex = approve(repo, aurora)
    out = execution.execute_plan(repo, ex, aurora)
    lines = repo.get_scenario_lines(repo.get_decision_for_request(aurora)["scenario_id"])
    vendor, depot = [x for x in lines if x["source_type"] == "VENDOR"], [x for x in lines if x["source_type"] == "DEPOT"]
    n_vendors, n_depots = len({x["source_id"] for x in vendor}), len({x["source_id"] for x in depot})
    assert out["status"] == "executed" and out["lines_placed_now"] == len(lines) and out["orders_placed_now"] == n_vendors + n_depots
    assert len(out["purchase_orders"]) == n_vendors and len(out["depot_transfers"]) == n_depots       # one per vendor, one per warehouse
    assert all(x["execution_status"] == "EXECUTED" for x in repo.get_scenario_lines(lines[0]["scenario_id"]))
    triggers = [c[0] for c in ex.calls]
    assert triggers.count(config.PO_TRIGGER) == n_vendors and triggers.count(config.TRANSFER_TRIGGER) == n_depots
    assert triggers.count(config.UPDATE_TRIGGER) == 2 and sorted(out["update_sent_to"]) == ["team2@example.com", "team@example.com"]
    po_inputs = next(i for t, i in ex.calls if t == config.PO_TRIGGER)
    assert po_inputs["plan_line_id"].startswith("REQ-001-V-") and " x" in po_inputs["sku"]
    assert set(po_inputs["destination_region"].split(",")) <= {"US", "EMEA", "APAC"}
    assert not [h for h in repo.t["depot_holds"] if h["status"] == "ACTIVE"]       # held stock became consumed
    assert sum(1 for h in repo.t["depot_holds"] if h["status"] == "CONSUMED") == len(depot)       # every held line is used
    total = sum(p["total_amount"] for p in repo.list_pos(aurora))
    assert total <= out["total_usd"] and out["savings_usd"] > 0


def test_executing_twice_never_orders_twice(repo, aurora):
    ex = approve(repo, aurora)
    first = execution.execute_plan(repo, ex, aurora)
    n = len(ex.calls)
    again = execution.execute_plan(repo, ex, aurora)
    assert again["orders_placed_now"] == 0 and again["lines_placed_now"] == 0 and len(ex.calls) == n
    assert len(repo.list_pos(aurora)) == len(first["purchase_orders"])


def test_a_failing_line_is_reported_and_retried_later(repo, aurora):
    ex = approve(repo, aurora)
    ex.fail_on = lambda t, i: t == config.PO_TRIGGER and "Venue display stand" in i["sku"]
    out = execution.execute_plan(repo, ex, aurora)
    assert out["status"] == "partial" and out["failed"] and out["update_sent_to"] == []        # no update until all is placed
    ex.fail_on = None
    ok = execution.execute_plan(repo, ex, aurora)
    assert ok["status"] == "executed" and len(ok["update_sent_to"]) == 2 and not ok["failed"]


def test_orders_never_exceed_the_authorised_amount(repo, aurora):
    ex = approve(repo, aurora)
    repo.t["decisions"][-1]["amount"] = 1000.0                    # authorised far less than the plan costs
    out = execution.execute_plan(repo, ex, aurora)
    assert out["failed"] and all(f["error"] == "beyond the authorised amount" for f in out["failed"])
    assert sum(p["total_amount"] for p in repo.list_pos(aurora)) <= 1000.0


def test_without_team_addresses_the_update_is_skipped_not_invented(repo, aurora):
    ex = FakeExecutor()
    decision_flow.authorize(repo, ex, aurora, "2", "")
    ex.execution = {"executionDetails": {"state": "SUCCEEDED"}}
    ex.suspensions = [{"state": "LIFTED"}]
    decision_flow.status(repo, aurora, ex)
    out = execution.execute_plan(repo, ex, aurora)
    assert out["status"] == "executed" and out["update_sent_to"] == []
    assert not [i for t, i in ex.calls if t == config.UPDATE_TRIGGER and "Orders placed" in i["email_subject"]]


def test_a_rejected_decision_blocks_execution(repo, aurora):
    ex = FakeExecutor()
    decision_flow.authorize(repo, ex, aurora, "2", "")
    ex.suspensions = [{"state": "REJECTED"}]
    decision_flow.status(repo, aurora, ex)
    assert execution.execute_plan(repo, ex, aurora)["status"] == "BLOCKED"


def test_one_purchase_order_per_vendor_carries_all_of_its_lines(repo, aurora):
    ex = approve(repo, aurora)
    execution.execute_plan(repo, ex, aurora)
    lines = repo.get_scenario_lines(repo.get_decision_for_request(aurora)["scenario_id"])
    pos = repo.list_pos(aurora)
    by_vendor = {}
    for ln in lines:
        if ln["source_type"] == "VENDOR":
            by_vendor.setdefault(ln["source_id"], []).append(ln)
    assert sorted(p["vendor_id"] for p in pos) == sorted(by_vendor) and len({p["po_number"] for p in pos}) == len(pos)
    for p in pos:
        mine = by_vendor[p["vendor_id"]]
        assert p["quantity"] == sum(x["quantity"] for x in mine) and abs(p["total_amount"] - sum(x["line_total"] for x in mine)) < 0.01
        assert set(p["line_id"].split(",")) == {x["line_id"] for x in mine} and p["po_number"] == f"PO-{aurora}-{p['vendor_id']}"
    assert len(pos) < sum(len(v) for v in by_vendor.values())                  # fewer orders than lines


def test_one_transfer_per_warehouse(repo, aurora):
    ex = approve(repo, aurora)
    execution.execute_plan(repo, ex, aurora)
    transfers = repo.list_transfers(aurora)
    assert sorted(t["depot_id"] for t in transfers) == sorted({t["depot_id"] for t in transfers})
    assert {t["depot_id"] for t in transfers} == {"DEPOT-LON-01", "DEPOT-DAL-02", "DEPOT-SIN-03"}


def test_a_retry_after_a_failed_order_keeps_the_numbers_unique(repo, aurora):
    ex = approve(repo, aurora)
    ex.fail_on = lambda t, i: t == config.PO_TRIGGER and i["vendor_id"] == "V-DISPLAYCO"
    execution.execute_plan(repo, ex, aurora)
    ex.fail_on = None
    out = execution.execute_plan(repo, ex, aurora)
    numbers = out["purchase_orders"] + out["depot_transfers"]
    assert out["status"] == "executed" and len(numbers) == len(set(numbers)) and f"PO-{aurora}-V-DISPLAYCO" in numbers


def test_order_pack_pdf_is_built_from_the_plan(repo, aurora):
    from launchkit_provisioner import order_pack
    from tests.test_presentation import _approved
    _approved(repo, aurora)
    pdf = order_pack.build_pdf(repo, aurora)
    assert pdf[:5] == b"%PDF-" and len(pdf) > 2000


def test_the_pack_is_attached_to_the_update_email_and_the_email_still_goes_without_it(repo, aurora, monkeypatch):
    from launchkit_provisioner import config, storage
    from tests.conftest import FakeExecutor
    from tests.test_presentation import _approved
    monkeypatch.setattr(storage, "upload_pack", lambda rid, pdf: f"gs://b/{rid}/order-pack.pdf")
    monkeypatch.setattr(storage, "bucket_name", lambda: "b")
    _approved(repo, aurora)
    ex = FakeExecutor()
    execution.execute_plan(repo, ex, aurora)
    sent = [i for t, i in ex.calls if t == config.UPDATE_TRIGGER]
    assert sent and all(i["attachment_path"] == f"gs://b/{aurora}/order-pack.pdf" for i in sent)
    # a workflow that refuses the attachment: the email is sent again without it
    refuse = FakeExecutor(fail_on=lambda t, i: t == config.UPDATE_TRIGGER and "attachment_path" in i)
    from launchkit_provisioner import emails
    emails.send_update(refuse, {"request_id": "r"}, "gs://b/x.pdf")
    assert [("attachment_path" in i) for t, i in refuse.calls] == [True, True, False]
