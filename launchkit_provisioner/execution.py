"""Placing the orders for an approved scenario, through Application Integration.

execute_plan() is one deterministic batch: for every planned line of the APPROVED scenario it starts the right workflow
(purchase order for vendor lines, depot transfer for surplus stock), records the result and marks the line executed;
when everything is placed it sends the tracking update to the launch team. The model never fills order fields: every
amount, SKU, vendor, depot and quantity comes from the stored plan, and the code refuses to go beyond the authorised
amount. Calling it twice never orders twice (executed lines are skipped).
"""
from concurrent.futures import ThreadPoolExecutor

from . import config, presentation
from .data.seed_data import TEAM_ROLE


MAX_PARALLEL = 8


def _audit(repo, request_id, actor, action, **details):
    repo.log_audit(request_id, actor, action, details)


def _update_email(launch, scenario, pos, transfers, saved, request_id) -> tuple[str, str]:
    """The tracking update for the launch team: a plain subject and a formatted HTML body."""
    p = presentation
    subject = f"Orders placed for the {launch['launch_name']} ({request_id})"
    saving = (f"Saved {p.money(saved)} compared with buying everything new" if saved > 0
              else f"{p.money(-saved)} more than buying everything new" if saved < 0 else "Same as buying everything new")
    rows = [("Choice", scenario["option_name"]), ("Purchase orders placed", str(len(pos))),
            ("Moves between our warehouses", str(len(transfers))), ("Total", p.money(scenario["total_cost"])),
            ("Price compared with buying new", saving),
            ("Everything arrives", f"{p.day(scenario['delivery_date'])} ({scenario['buffer_hours'] // 24} days before the "
                                   f"{p.day(launch['in_hand_by'])} deadline)"),
            ("Pollution (CO2)", f"{scenario['carbon_kg']:,.0f} kg")]
    cells = "".join(
        f'<tr><td style="padding:10px 14px;border-bottom:1px solid #e5e7eb;color:#6b7280;width:45%">{k}</td>'
        f'<td style="padding:10px 14px;border-bottom:1px solid #e5e7eb;font-weight:600;color:#111827">{v}</td></tr>'
        for k, v in rows)
    body = (
        '<div style="font-family:Arial,Helvetica,sans-serif;max-width:600px;margin:0 auto;border:1px solid #e5e7eb;'
        'border-radius:12px;overflow:hidden">'
        f'<div style="background:#0f766e;color:#ffffff;padding:20px 24px"><div style="font-size:13px;opacity:.85">'
        f'ORDERS PLACED</div><div style="font-size:22px;font-weight:700">{launch["launch_name"]}</div></div>'
        '<div style="padding:20px 24px;color:#111827;font-size:15px;line-height:1.5">'
        f'<p style="margin-top:0">Good news! All orders for this campaign have been placed. Here is the summary.</p>'
        f'<table style="width:100%;border-collapse:collapse;font-size:14px">{cells}</table>'
        f'<p style="margin-bottom:0;color:#6b7280;font-size:13px">Request {request_id}. To see the full list of vendors and '
        f'orders, ask the assistant: <em>What is the status of {request_id}?</em></p></div></div>')
    return subject, body


def _place(executor, request_id, ln):
    """Start the workflow for one planned line. Returns ("PO" | "TRANSFER", number, execution id)."""
    if ln["source_type"] == "VENDOR":
        out = executor.execute(config.PO_TRIGGER, {
            "request_id": request_id, "plan_line_id": ln["line_id"], "vendor_id": ln["source_id"], "sku": ln["sku"],
            "quantity": int(ln["quantity"]), "total_amount": float(ln["line_total"]), "destination_region": ln["region"]})
        if not out.get("po_number"):
            raise RuntimeError("the workflow returned no po_number")
        return "PO", str(out["po_number"]), out.get("execution_id")
    out = executor.execute(config.TRANSFER_TRIGGER, {
        "request_id": request_id, "plan_line_id": ln["line_id"], "depot_id": ln["source_id"], "sku": ln["sku"],
        "quantity": int(ln["quantity"]), "destination_region": ln["region"]})
    if not out.get("transfer_number"):
        raise RuntimeError("the workflow returned no transfer_number")
    return "TRANSFER", str(out["transfer_number"]), out.get("execution_id")


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
    events, failed, todo = [], [], []
    for ln in lines:                                   # the amount guard runs before anything is started
        if ln["execution_status"] == "EXECUTED":
            continue
        if spent + float(ln["line_total"]) > authorised + 0.01:
            failed.append({"line": ln["line_id"], "error": "beyond the authorised amount"})
            events.append(("fulfilment_agent", "order_blocked", {"line": ln["line_id"], "reason": "over authorised amount"}))
            continue
        spent += float(ln["line_total"])
        todo.append(ln)
    # The workflows are independent: start them in parallel, then write the results to BigQuery in bulk.
    results = {}
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
        futures = {ln["line_id"]: pool.submit(_place, executor, request_id, ln) for ln in todo}
        for lid, fut in futures.items():
            try:
                results[lid] = fut.result()
            except Exception as exc:  # noqa: BLE001 - one failing line must not stop the others
                results[lid] = exc
    pos, transfers, done_ids, depot_ids = [], [], [], []
    for ln in todo:
        res = results[ln["line_id"]]
        if isinstance(res, Exception):
            failed.append({"line": ln["line_id"], "error": str(res)[:200]})
            events.append(("fulfilment_agent", "order_failed", {"line": ln["line_id"], "error": str(res)[:300]}))
            continue
        kind, number, exec_id = res
        done_ids.append(ln["line_id"])
        if kind == "PO":
            pos.append({"po_number": number, "request_id": request_id, "line_id": ln["line_id"], "vendor_id": ln["source_id"],
                        "sku": ln["sku"], "region": ln["region"], "quantity": int(ln["quantity"]),
                        "total_amount": float(ln["line_total"]), "status": "CREATED", "integration_execution_id": exec_id})
            events.append(("fulfilment_agent", "po_created", {"po_number": number, "line": ln["line_id"],
                                                              "vendor": ln["source_id"], "total": float(ln["line_total"])}))
        else:
            depot_ids.append(ln["line_id"])
            transfers.append({"transfer_number": number, "request_id": request_id, "line_id": ln["line_id"],
                              "depot_id": ln["source_id"], "sku": ln["sku"], "region": ln["region"],
                              "quantity": int(ln["quantity"]), "status": "CREATED", "integration_execution_id": exec_id})
            events.append(("fulfilment_agent", "transfer_created", {"transfer": number, "line": ln["line_id"],
                                                                    "depot": ln["source_id"], "quantity": int(ln["quantity"])}))
    repo.record_pos(pos)
    repo.record_transfers(transfers)
    repo.mark_lines_executed(done_ids)
    repo.consume_holds(depot_ids)
    placed_now = len(done_ids)
    remaining = [x for x in repo.get_scenario_lines(decision["scenario_id"]) if x["execution_status"] != "EXECUTED"]
    update = {"sent_to": [], "failed": []}
    if placed_now and not remaining:
        all_pos, all_tr = repo.list_pos(request_id), repo.list_transfers(request_id)
        subject, body = _update_email(launch, scenario, all_pos, all_tr, scenario["savings_usd"], request_id)
        for email in repo.get_approver_emails(TEAM_ROLE):
            try:
                executor.execute(config.UPDATE_TRIGGER, {
                    "request_id": request_id, "launch_id": launch["launch_id"], "recipient_email": email,
                    "email_subject": subject, "email_body": body})
                update["sent_to"].append(email)
            except Exception as exc:  # noqa: BLE001
                update["failed"].append({"email": email, "error": str(exc)[:200]})
        events.append(("fulfilment_agent", "launch_update_sent", {"sent_to": update["sent_to"], "failed": update["failed"]}))
    repo.log_audit_batch(request_id, events)
    all_pos, all_tr = repo.list_pos(request_id), repo.list_transfers(request_id)
    summary = presentation.order_summary(repo, request_id, scenario, repo.get_decision_for_request(request_id),
                                         update["sent_to"], failed)
    return {"status": "executed" if not remaining else "partial", "option": scenario["option_name"],
            "display_markdown": summary,
            "orders_placed_now": placed_now, "purchase_orders": [p["po_number"] for p in all_pos],
            "depot_transfers": [t["transfer_number"] for t in all_tr], "failed": failed,
            "total_usd": float(scenario["total_cost"]), "savings_usd": float(scenario["savings_usd"]),
            "delivery_date": str(scenario["delivery_date"]), "buffer_hours": int(scenario["buffer_hours"]),
            "update_sent_to": update["sent_to"], "update_failed": update["failed"]}
