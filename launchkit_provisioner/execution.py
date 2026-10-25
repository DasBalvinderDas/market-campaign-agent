"""Placing the orders for an approved scenario, through Application Integration.

execute_plan() is one deterministic batch: the planned lines of the APPROVED scenario are grouped into **one purchase order
per vendor** and **one transfer per warehouse**; each group starts the right workflow once, the result is recorded and every
line of the group is marked executed;
when everything is placed it sends the tracking update to the launch team. The model never fills order fields: every
amount, SKU, vendor, depot and quantity comes from the stored plan, and the code refuses to go beyond the authorised
amount. Calling it twice never orders twice (executed lines are skipped).
"""
from concurrent.futures import ThreadPoolExecutor

from . import config, emails, presentation
from .data.seed_data import TEAM_ROLE


MAX_PARALLEL = 8


def _audit(repo, request_id, actor, action, **details):
    repo.log_audit(request_id, actor, action, details)


def _update_email(repo, launch, scenario, pos, transfers, saved, request_id) -> tuple[str, str]:
    """The tracking update for the launch team: a plain subject and a formatted HTML body (see emails.py)."""
    return emails.orders_placed_email(repo, launch, scenario, pos, transfers, saved, request_id)


def _place_group(executor, request_id, kind, source_id, lns, key, names):
    """One purchase order per vendor (or one transfer per warehouse) for all its plan lines.
    Returns (kind, number, execution id)."""
    qty = sum(int(x["quantity"]) for x in lns)
    per_sku: dict = {}
    for x in lns:
        per_sku[x["sku"]] = per_sku.get(x["sku"], 0) + int(x["quantity"])
    items = "; ".join(f"{names.get(k, k)} x{v}" for k, v in per_sku.items())[:500]
    region = ",".join(sorted({x["region"] for x in lns}))
    if kind == "PO":
        out = executor.execute(config.PO_TRIGGER, {
            "request_id": request_id, "plan_line_id": key, "vendor_id": source_id, "sku": items, "quantity": qty,
            "total_amount": round(sum(float(x["line_total"]) for x in lns), 2), "destination_region": region})
        if not out.get("po_number"):
            raise RuntimeError("the workflow returned no po_number")
        return "PO", str(out["po_number"]), out.get("execution_id")
    out = executor.execute(config.TRANSFER_TRIGGER, {
        "request_id": request_id, "plan_line_id": key, "depot_id": source_id, "sku": items, "quantity": qty,
        "destination_region": region})
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
    # One purchase order per vendor and one transfer per warehouse (all their lines together). The workflows are
    # independent: start them in parallel, then write the results to BigQuery in bulk.
    names = {a["sku"]: a["name"] for a in repo.list_assets()}
    taken = {p["po_number"] for p in repo.list_pos(request_id)} | {t["transfer_number"] for t in repo.list_transfers(request_id)}
    groups: dict = {}
    for ln in todo:
        groups.setdefault(("PO" if ln["source_type"] == "VENDOR" else "TR", ln["source_id"]), []).append(ln)
    keys = {}
    for (kind, source), lns in groups.items():       # a retry after a partial run gets -2, -3 ... so numbers stay unique
        key = f"{request_id}-{source}"
        n = 1
        while f"{kind}-{key}" in taken:
            n += 1
            key = f"{request_id}-{source}-{n}"
        keys[(kind, source)] = key
    results = {}
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
        futures = {g: pool.submit(_place_group, executor, request_id, g[0] if g[0] == "PO" else "TRANSFER", g[1], lns,
                                  keys[g], names) for g, lns in groups.items()}
        for g, fut in futures.items():
            try:
                results[g] = fut.result()
            except Exception as exc:  # noqa: BLE001 - one failing order must not stop the others
                results[g] = exc
    pos, transfers, done_ids, depot_ids = [], [], [], []
    for g, lns in groups.items():
        res = results[g]
        if isinstance(res, Exception):
            for ln in lns:
                failed.append({"line": ln["line_id"], "error": str(res)[:200]})
            events.append(("fulfilment_agent", "order_failed", {"source": g[1], "lines": len(lns), "error": str(res)[:300]}))
            continue
        kind, number, exec_id = res
        done_ids += [ln["line_id"] for ln in lns]
        total = round(sum(float(x["line_total"]) for x in lns), 2)
        qty = sum(int(x["quantity"]) for x in lns)
        per_sku: dict = {}
        for x in lns:
            per_sku[x["sku"]] = per_sku.get(x["sku"], 0) + int(x["quantity"])
        items = "; ".join(f"{names.get(k, k)} x{v}" for k, v in per_sku.items())[:500]
        region = ",".join(sorted({x["region"] for x in lns}))
        line_ids = ",".join(x["line_id"] for x in lns)
        if kind == "PO":
            pos.append({"po_number": number, "request_id": request_id, "line_id": line_ids, "vendor_id": g[1], "sku": items,
                        "region": region, "quantity": qty, "total_amount": total, "status": "CREATED",
                        "integration_execution_id": exec_id})
            events.append(("fulfilment_agent", "po_created", {"po_number": number, "vendor": g[1], "lines": len(lns),
                                                              "total": total}))
        else:
            depot_ids += [ln["line_id"] for ln in lns]
            transfers.append({"transfer_number": number, "request_id": request_id, "line_id": line_ids, "depot_id": g[1],
                              "sku": items, "region": region, "quantity": qty, "status": "CREATED",
                              "integration_execution_id": exec_id})
            events.append(("fulfilment_agent", "transfer_created", {"transfer": number, "depot": g[1], "lines": len(lns),
                                                                    "quantity": qty}))
    repo.record_pos(pos)
    repo.record_transfers(transfers)
    repo.mark_lines_executed(done_ids)
    repo.consume_holds(depot_ids)
    placed_now = len(done_ids)
    remaining = [x for x in repo.get_scenario_lines(decision["scenario_id"]) if x["execution_status"] != "EXECUTED"]
    update = {"sent_to": [], "failed": []}
    if placed_now and not remaining:
        all_pos, all_tr = repo.list_pos(request_id), repo.list_transfers(request_id)
        subject, body = _update_email(repo, launch, scenario, all_pos, all_tr, scenario["savings_usd"], request_id)
        # In "gemini" and "workflow" mode the confirmation is the chat reply (or the workflow result) and the order pack PDF: no
        # launch-team email, unless APPROVAL_NOTIFY_EMAIL is true.
        quiet = config.APPROVAL_CHANNEL in ("gemini", "workflow") and not config.APPROVAL_NOTIFY_EMAIL
        for email in ([] if quiet else repo.get_approver_emails(TEAM_ROLE)):
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
            "orders_placed_now": len(pos) + len(transfers), "lines_placed_now": placed_now, "purchase_orders": [p["po_number"] for p in all_pos],
            "depot_transfers": [t["transfer_number"] for t in all_tr], "failed": failed,
            "total_usd": float(scenario["total_cost"]), "savings_usd": float(scenario["savings_usd"]),
            "delivery_date": str(scenario["delivery_date"]), "buffer_hours": int(scenario["buffer_hours"]),
            "update_sent": len(update["sent_to"]), "update_failed": len(update["failed"])}
