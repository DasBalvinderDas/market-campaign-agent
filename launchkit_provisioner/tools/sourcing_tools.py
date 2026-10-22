"""Tools of the sourcing planner agent."""
from .. import config, planner, presentation
from ..repositories import get_repo
from .audit import audit

_FINAL = ("PENDING", "APPROVED")
DATE_OFFSETS = [-14, -7, 0, 7, 14, 28]       # days earlier or later than the date on file


def _autopilot_limit(repo) -> float:
    humans = [p for p in repo.list_policies() if p["requires_human"]]
    return float(min(p["min_amount"] for p in humans)) if humans else 0.0


def build_scenarios(request_id: str) -> dict:
    """Compute the three sourcing options for a request in one call and store them: full new production, smart depot
    rebalance (reuses surplus stock from regional depots) and certified eco launch. Each option has cost, delivery date,
    safety buffer before the in-hand deadline, savings, carbon and risk, all computed from BigQuery data. Returns the
    formatted decision card and whether the request can run on autopilot.

    Args:
        request_id: Request id (requirement lines must exist).
    """
    repo = get_repo()
    existing = repo.get_decision_for_request(request_id)
    if existing and existing["status"] in _FINAL:
        return {"status": "error", "message": f"A sign-off is already {existing['status']} for this request "
                                             f"({existing['option_code']}); the options cannot be re-planned."}
    try:
        scenarios, lines = planner.plan_scenarios(repo, request_id)
    except planner.PlanError as exc:
        return {"status": "error", "message": str(exc)}
    repo.replace_scenarios(request_id, scenarios, lines)
    stored = repo.get_scenarios(request_id)
    launch = repo.get_launch(repo.get_request(request_id)["launch_id"])
    limit = _autopilot_limit(repo)
    policies = repo.list_policies()
    best = next(s for s in stored if s["recommended"])
    autopilot = bool(best["feasible"] and float(best["total_cost"]) <= limit)
    audit(request_id, "sourcing_planner_agent", "scenarios_built", recommended=best["option_code"],
          totals={s["option_code"]: s["total_cost"] for s in stored}, autopilot=autopilot,
          disruptions=[d["vendor_id"] for d in repo.list_disruptions()])
    return {"status": "ok", "request_id": request_id, "decision_mode": "AUTOPILOT" if autopilot else "CHOOSE",
            "autopilot_limit_usd": limit, "recommended_option": best["option_name"],
            "options": [{"option": i, "name": s["option_name"], "total_usd": s["total_cost"], "savings_usd": s["savings_usd"],
                         "delivery_date": str(s["delivery_date"]), "buffer_hours": s["buffer_hours"],
                         "carbon_kg": s["carbon_kg"], "feasible": s["feasible"], "recommended": s["recommended"]}
                        for i, s in enumerate(stored, start=1)],
            "active_vendor_delays": repo.list_disruptions(),
            "decision_card": planner.decision_card(
                request_id, launch, stored, policies, repo.get_planning_rules().get("MIN_BUFFER_HOURS", 24),
                single_item=all(ln["bundle_type"] == "SINGLE_ITEM" for ln in repo.get_requirement_lines(request_id))),
            "tldr": presentation.tldr(repo, request_id, stored, policies),
            # Show only this to the user, exactly: a two-line summary, then the tables (stock, vendors, the 3 choices, other dates).
            "display_markdown": _plan_text(repo, request_id, launch, stored, policies),
            "carbon_explanation": presentation.carbon_explanation(repo, request_id),
            "date_options": presentation.date_options_markdown(planner.plan_dates(repo, request_id, DATE_OFFSETS), policies),
            "stock_report": presentation.stock_report(repo, request_id),
            "vendor_report": presentation.vendor_report(repo, request_id)}


def _plan_text(repo, request_id, launch, stored, policies) -> str:
    min_buffer = repo.get_planning_rules().get("MIN_BUFFER_HOURS", 24)
    card = planner.decision_card(request_id, launch, stored, policies, min_buffer,
                                 single_item=all(ln["bundle_type"] == "SINGLE_ITEM" for ln in repo.get_requirement_lines(request_id)))
    dates = presentation.date_options_markdown(planner.plan_dates(repo, request_id, DATE_OFFSETS), policies)
    # What we did for the user first (the choices), then the details (stock, vendors), then our pick in short, then other dates,
    # and the question last. The card ends with the question; it is moved to the end.
    marker = "👉 **Does this plan feel good?**"
    table, _, question = card.partition(marker)
    question = marker + question if question else ""
    pick = "### 🎯 Step 4: Our pick, in short\n" + presentation.plan_lead(repo, request_id, stored, policies, min_buffer)
    parts = [table.rstrip(), presentation.stock_report(repo, request_id), presentation.vendor_report(repo, request_id), pick,
             dates, question]
    return "\n\n".join(x for x in parts if x)


def report_vendor_delay(request_id: str, vendor: str, delay_days: int, reason: str = "") -> dict:
    """Record that a vendor is late (by id or name) and see what it changes. If the request has no sign-off yet, call
    build_scenarios again afterwards to re-plan; if it is already approved, this returns the impact on its buffer.

    Args:
        request_id: Request id the user is asking about.
        vendor: Vendor id or name, e.g. "RapidDisplay".
        delay_days: Days of delay.
        reason: Why, if the user said.
    """
    repo = get_repo()
    v = planner.resolve_vendor(repo, vendor)
    if not v:
        return {"status": "error", "message": f"No single vendor matches '{vendor}'.",
                "vendors": [{"vendor_id": x["vendor_id"], "name": x["vendor_name"]} for x in repo.list_vendors()]}
    if int(delay_days) <= 0:
        return {"status": "error", "message": "The delay must be a positive number of days."}
    repo.add_disruption(v["vendor_id"], int(delay_days), reason)
    audit(request_id, "sourcing_planner_agent", "vendor_delay_reported", vendor=v["vendor_id"], delay_days=int(delay_days),
          reason=reason)
    decision = repo.get_decision_for_request(request_id)
    out = {"status": "ok", "vendor": v["vendor_name"], "delay_days": int(delay_days)}
    if decision and decision["status"] in _FINAL:
        scenario = repo.get_scenario(decision["scenario_id"])
        impact = planner.delay_impact(repo, scenario, int(delay_days), v["vendor_id"])
        out.update(impact={**impact, "new_delivery_date": str(impact["new_delivery_date"])},
                   next_step="The plan is already signed off, so it is not re-planned. Report the impact on the buffer.")
    else:
        out["next_step"] = "Now call build_scenarios to re-plan with the delay."
    return out
