"""Placing the orders for an approved scenario, through Application Integration.

execute_plan() is one deterministic batch: for every planned line of the APPROVED scenario it starts the right workflow
(purchase order for vendor lines, depot transfer for surplus stock), records the result and marks the line executed;
when everything is placed it sends the tracking update to the launch team. The model never fills order fields: every
amount, SKU, vendor, depot and quantity comes from the stored plan, and the code refuses to go beyond the authorised
amount. Calling it twice never orders twice (executed lines are skipped).
"""
from . import config
from .data.seed_data import TEAM_ROLE


def _audit(repo, request_id, actor, action, **details):
    repo.log_audit(request_id, actor, action, details)


def _update_email(launch, scenario, pos, transfers, saved, request_id) -> tuple[str, str]:
    subject = f"Launch collateral confirmed: {launch['launch_name']} ({request_id})"
    body = (f"{launch['launch_name']}: the sourcing plan '{scenario['option_name']}' was approved and placed.\n\n"
            f"- Purchase orders issued: {len(pos)}\n- Depot transfers created: {len(transfers)}\n"
            f"- Total: USD {scenario['total_cost']:,.2f} ({scenario['savings_usd']:+,.2f} versus full new production)\n"
            f"- Estimated delivery: {scenario['delivery_date']} ({scenario['buffer_hours']} hours before the in-hand "
            f"date {launch['in_hand_by']}; press embargo {launch['embargo_date']})\n"
            f"- Carbon: {scenario['carbon_kg']:,.0f} kg CO2e\n\nTracking: ask the Launch Provisioner for "
            f"the status of {request_id}.")
    return subject, body


def execute_plan(repo, executor, request_id: str) -> dict:
    decision = repo.get_decision_for_request(request_id)
    if not decision:
        return {"status": "error", "message": "No sign-off exists for this request: nothing can be ordered."}
    if decision["status"] != "APPROVED":
        _audit(repo, request_id, "fulfilment_agent", "execution_blocked", decision_status=decision["status"])
        return {"status": "BLOCKED", "message": f"The sign-off is {decision['status']}, not APPROVED: nothing was ordered."}
    scenario = repo.get_scenario(decision["scenario_id"])
    req = repo.get_request(request_id)
    launch = repo.get_launch(req["launch_id"])
    lines = repo.get_scenario_lines(decision["scenario_id"])
    authorised = float(decision["amount"])
    spent = sum(float(x["line_total"]) for x in lines if x["execution_status"] == "EXECUTED")
    placed_now, failed = 0, []
    for ln in lines:
        if ln["execution_status"] == "EXECUTED":
            continue
        if spent + float(ln["line_total"]) > authorised + 0.01:
            failed.append({"line": ln["line_id"], "error": "beyond the authorised amount"})
            _audit(repo, request_id, "fulfilment_agent", "order_blocked", line=ln["line_id"], reason="over authorised amount")
            continue
        try:
            if ln["source_type"] == "VENDOR":
                out = executor.execute(config.PO_TRIGGER, {
                    "request_id": request_id, "plan_line_id": ln["line_id"], "vendor_id": ln["source_id"],
                    "sku": ln["sku"], "quantity": int(ln["quantity"]), "total_amount": float(ln["line_total"]),
                    "destination_region": ln["region"]})
                number = out.get("po_number")
                if not number:
                    raise RuntimeError("the workflow returned no po_number")
                repo.record_po({"po_number": str(number), "request_id": request_id, "line_id": ln["line_id"],
                                "vendor_id": ln["source_id"], "sku": ln["sku"], "region": ln["region"],
                                "quantity": int(ln["quantity"]), "total_amount": float(ln["line_total"]),
                                "status": "CREATED", "integration_execution_id": out.get("execution_id")})
                _audit(repo, request_id, "fulfilment_agent", "po_created", po_number=str(number), line=ln["line_id"],
                       vendor=ln["source_id"], total=float(ln["line_total"]))
            else:
                out = executor.execute(config.TRANSFER_TRIGGER, {
                    "request_id": request_id, "plan_line_id": ln["line_id"], "depot_id": ln["source_id"],
                    "sku": ln["sku"], "quantity": int(ln["quantity"]), "destination_region": ln["region"]})
                number = out.get("transfer_number")
                if not number:
                    raise RuntimeError("the workflow returned no transfer_number")
                repo.record_transfer({"transfer_number": str(number), "request_id": request_id, "line_id": ln["line_id"],
                                      "depot_id": ln["source_id"], "sku": ln["sku"], "region": ln["region"],
                                      "quantity": int(ln["quantity"]), "status": "CREATED",
                                      "integration_execution_id": out.get("execution_id")})
                repo.consume_hold(ln["line_id"])
                _audit(repo, request_id, "fulfilment_agent", "transfer_created", transfer=str(number), line=ln["line_id"],
                       depot=ln["source_id"], quantity=int(ln["quantity"]))
            repo.mark_line_executed(ln["line_id"])
            spent += float(ln["line_total"])
            placed_now += 1
        except Exception as exc:  # noqa: BLE001 - one failing line must not stop the others
            failed.append({"line": ln["line_id"], "error": str(exc)[:200]})
            _audit(repo, request_id, "fulfilment_agent", "order_failed", line=ln["line_id"], error=str(exc)[:300])
    pos, transfers = repo.list_pos(request_id), repo.list_transfers(request_id)
    remaining = [x for x in repo.get_scenario_lines(decision["scenario_id"]) if x["execution_status"] != "EXECUTED"]
    update = {"sent_to": [], "failed": []}
    if placed_now and not remaining:
        subject, body = _update_email(launch, scenario, pos, transfers, scenario["savings_usd"], request_id)
        for email in repo.get_approver_emails(TEAM_ROLE):
            try:
                executor.execute(config.UPDATE_TRIGGER, {
                    "request_id": request_id, "launch_id": launch["launch_id"], "recipient_email": email,
                    "email_subject": subject, "email_body": body})
                update["sent_to"].append(email)
            except Exception as exc:  # noqa: BLE001
                update["failed"].append({"email": email, "error": str(exc)[:200]})
        _audit(repo, request_id, "fulfilment_agent", "launch_update_sent", sent_to=update["sent_to"],
               failed=update["failed"])
    return {"status": "executed" if not remaining else "partial", "option": scenario["option_name"],
            "orders_placed_now": placed_now, "purchase_orders": [p["po_number"] for p in pos],
            "depot_transfers": [t["transfer_number"] for t in transfers], "failed": failed,
            "total_usd": float(scenario["total_cost"]), "savings_usd": float(scenario["savings_usd"]),
            "delivery_date": str(scenario["delivery_date"]), "buffer_hours": int(scenario["buffer_hours"]),
            "update_sent_to": update["sent_to"], "update_failed": update["failed"]}
