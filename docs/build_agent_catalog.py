#!/usr/bin/env python3
"""Builds docs/LaunchKit_Provisioner_Agent_Catalog.xlsx: root agent and sub-agents, tools, BigQuery and Application Integration.

  python docs/build_agent_catalog.py        (needs: pip install openpyxl)
"""
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

OUT = Path(__file__).resolve().parent / "LaunchKit_Provisioner_Agent_Catalog.xlsx"
APP, OWNER = "LaunchKit Provisioner Agent (Product Launch Collateral Planner)", "Dasbalvinder Das"

AGENTS = [
    ("Root Agent", "LaunchKit Provisioner (Orchestrator)",
     "The root agent is the Campaign Procurement Assistant, the front-line coordinator. Underneath it is a purchase order, procurement and approval system, but it handles a whole campaign brief (many items, many vendors) instead of single items. On a greeting it shows what it can do and what it needs. It takes the event brief, registers the request and calls the three specialist "
     "agents in a fixed order: Brief Analyst, Sourcing Planner, then (after sign-off) Fulfilment. It shows the manager, in simple words with tables and icons, the shopping list (Bill of Materials), the vendor comparison and the 3-choices table "
     "and waits for a choice. It holds the human-in-the-loop sign-off gate: only the root can call "
     "authorize_launch. Spend within the autopilot limit is approved by policy; above it an Application Integration approval emails the "
     "VP (or the CMO for the largest tier) and nothing is ordered until they approve. When the user asks for the status it reads the "
     "decision and has the orders placed (Approved) or releases the held depot stock (Rejected). It writes every reply the user sees.",
     "BigQuery (requests, decisions, audit log, readiness board); Application Integration (request_approval); Vertex AI Agent Engine; Gemini Enterprise chat"),
    ("Sub Agent", "Brief Analyst Agent",
     "The brief analyst turns the free-text brief into requirement lines in one call: guest welcome kits (hoodie size, power plug and "
     "engraving from the guest list), venue display stands and executive sales folders, spread over the regions. It returns the shopping list "
     "(Bill of Materials) and business advice (spares, a kind of bundle left out, the rest of a bundle, a date that is too close). It never invents a bundle type.",
     "BigQuery: bundle_templates, guests, regional_split, requirement_lines, audit_log"),
    ("Sub Agent", "Sourcing Planner Agent",
     "The sourcing planner computes three options for the request from BigQuery data: full brand-new production, use our stock first, buy the rest "
     "(reuses surplus stock from our warehouses, nearest first, and picks vendors that keep the safety buffer) and a certified green option. "
     "It also returns the vendor comparison (every vendor checked, who was chosen, why). Each option has cost, delivery date, buffer hours before the in-hand deadline, savings, carbon and risk. It re-plans when a vendor "
     "reports a delay. It never changes a number.",
     "BigQuery: requirement_lines, vendor_offers, vendors, vendor_disruptions, depot_stock / v_depot_available, transit_lanes, planning_rules, scenarios, scenario_lines"),
    ("Sub Agent", "Fulfilment Agent",
     "The fulfilment agent places the orders of the APPROVED option in one batch: a purchase order per vendor line and a depot transfer "
     "per surplus-stock line through Application Integration, in parallel, then the tracking update to the launch team. Code refuses "
     "to order without an approved sign-off or beyond the authorised amount, and calling it twice never orders twice.",
     "BigQuery: scenario_lines, decisions, depot_holds, purchase_orders, depot_transfers, audit_log; Application Integration: create_purchase_order, create_depot_transfer, send_launch_update"),
]

TOOLS = [
    # agent, tool, kind, what it does, BQ reads, BQ writes, Application Integration, guardrail
    ("Root Agent", "register_launch_request", "Python tool", "Finds the event by name or id (or creates a new event with the date given, or updates its date), validates the date, and creates the request (REQ-xxxx).", "launches", "launches (new event or new date), launch_requests, audit_log", "-", "Unknown event without a date, or a date that is not in the future, is refused"),
    ("Root Agent", "brief_analyst_agent / sourcing_planner_agent / fulfilment_agent", "Agent as tool (ADK AgentTool)", "The root calls each specialist like a tool with the request id and details; the specialist runs with its own prompt and tools and returns its result.", "(via the specialist)", "(via the specialist)", "(via the specialist)", "Fixed order in the root instruction; specialists only reply to the root"),
    ("Root Agent", "authorize_launch", "Python tool (sign-off gate)", "Authorises ONE computed option. Validates it (meets the deadline, depot stock still free), holds the surplus stock, then approves by policy (autopilot) or starts the executive approval and orders nothing.", "scenarios, scenario_lines, v_depot_available, approval_policy, approvers, launches, planning_rules", "decisions, depot_holds, audit_log", "request_approval (started over REST)", "Only the root has it; the amount comes from the stored scenario, not from the model; infeasible options are refused"),
    ("Root Agent", "get_launch_status", "Python tool", "Reads the sign-off. If the approver decided in Application Integration it records it (first decision wins): Approved unlocks fulfilment, Rejected releases the held stock.", "decisions, scenario_lines, purchase_orders, depot_transfers", "decisions (status), depot_holds (RELEASED), audit_log", "Reads the execution and its approval record (LIFTED = approved, REJECTED = rejected)", "Atomic update: a decision is recorded once"),
    ("Root Agent", "get_launch_overview", "Python tool", "Launch readiness board (GREEN / AMBER / RED, buffer, orders placed) and free surplus stock per depot.", "v_launch_readiness, launches, v_depot_available", "-", "-", "Read only"),
    ("Root Agent", "get_audit_trail", "Python tool", "Ordered audit events for a request.", "audit_log", "-", "-", "Read only"),
    ("Root Agent", "show_capabilities", "Python tool", "The hello card: what the assistant can do and what it needs from the user, with sample prompts.", "-", "-", "-", "Fixed text, no data access"),
    ("Root Agent", "show_checklist", "Python tool", "The interviewer: what we know so far (people, date, place, campaign name, picks) with ticks and the one next question, shown on every question turn. After the date it shows where we can deliver (USA, Canada, London, Singapore) with vendors and warehouses; after the place it shows what we can offer: packs and single items, our stock, the best vendor price for the date, ready-by dates, a faster option and a suggested plan for the headcount.", "venues, vendors, assets, bundle_templates, vendor_offers, vendor_date_pricing, vendor_disruptions, v_depot_available", "-", "-", "Read only"),
    ("Root Agent", "create_campaign", "Python tool", "Creates the campaign as soon as the user has picked one of the name ideas or typed their own (or finds it if it exists) and shows a confirmation card.", "launches", "launches, audit_log", "-", "Needs a future date; never duplicates a campaign"),
    ("Root Agent", "get_approval_rules", "Python tool", "The approval levels as a ladder (up to $5,000 automatic, up to $50,000 VP, above that CMO).", "approval_policy", "-", "-", "Read only"),
    ("Root Agent", "get_vendor_report", "Python tool", "Vendor comparison for a request: every vendor checked per item, price, days to make, late vendors, who was chosen, stock we already own.", "requirement_lines, vendor_offers, vendor_disruptions, scenarios, scenario_lines, v_depot_available", "-", "-", "Read only"),
    ("Brief Analyst Agent", "build_requirements", "Python tool (batch)", "Expands every bundle of the brief into requirement lines per SKU and region; guest welcome kits personalised from the guest list. Returns the shopping list (Bill of Materials).", "bundle_templates, guests, regional_split, launch_requests", "requirement_lines, audit_log", "-", "Unknown bundle type returns the valid types"),
    ("Sourcing Planner Agent", "build_scenarios", "Python tool (batch)", "Computes and stores the three options with cost, delivery date, buffer, savings, carbon, risk; returns the 3-choices table and whether autopilot applies.", "requirement_lines, vendor_offers, vendors, vendor_disruptions, v_depot_available, transit_lanes, assets, planning_rules, approval_policy", "scenarios, scenario_lines, audit_log", "-", "Refuses to re-plan once a sign-off is pending or approved"),
    ("Sourcing Planner Agent", "report_vendor_delay", "Python tool", "Records a vendor delay (by id or name). Before a sign-off: re-plan. After: reports the impact on the buffer.", "vendors, decisions, scenario_lines", "vendor_disruptions, audit_log", "-", "Ambiguous vendor names are refused"),
    ("Fulfilment Agent", "execute_plan", "Python tool (batch)", "Places every line of the approved option: purchase orders, depot transfers (in parallel), then the tracking update; writes the results in bulk.", "decisions, scenario_lines, launches, approvers", "purchase_orders, depot_transfers, scenario_lines (EXECUTED), depot_holds (CONSUMED), audit_log", "create_purchase_order, create_depot_transfer, send_launch_update", "BLOCKED unless APPROVED; never beyond the authorised amount; idempotent"),
]

BQ = [
    ("launches", "Table", "The launch with its in-hand deadline and press embargo (re-based to today by --reset-demo).", "Planner, tools", "Setup script"),
    ("venues", "Table", "Where a campaign can be held (USA, Canada, London, Singapore) and the region that serves it.", "Interviewer (show_checklist)", "Setup script; refresh with --refresh-reference"),
    ("vendor_date_pricing", "Table", "Price factor by days ahead: early-bird discounts and rush charges, per vendor or for all vendors (*).", "Planner, offer, dates table", "Setup script; refresh with --refresh-reference"),
    ("assets", "Table", "Item catalog (19 items) with ship factor (size / weight): pack items and campaign extras. Feeds the offer shown to the user.", "Planner, offer, BOM", "Setup script; refresh with --refresh-reference"),
    ("bundle_templates", "Table", "What goes into one guest welcome kit, venue display stand or sales folder.", "Brief analyst", "Setup script"),
    ("guests", "Table", "150 guests: hoodie size, region and power plug (personalisation).", "Brief analyst", "Setup script"),
    ("regional_split", "Table", "How venue and sales bundles spread over regions.", "Brief analyst", "Setup script"),
    ("depots", "Table", "Regional marketing depots (London, Dallas, Singapore).", "v_depot_available", "Setup script"),
    ("depot_stock", "Table", "Surplus units on hand per depot and SKU.", "v_depot_available", "Setup script"),
    ("v_depot_available", "View", "Free surplus = on hand minus active and consumed holds.", "Planner, sign-off, overview", "-"),
    ("transit_lanes", "Table", "Shipping days and cost between regions.", "Planner", "Setup script"),
    ("vendors", "Table", "Manufacturers and where they ship from.", "Planner", "Setup script"),
    ("vendor_offers", "Table", "Price, lead time and carbon per vendor, SKU and variant (STANDARD / ECO). 12 vendors, 51 offers, at least two vendors per item.", "Planner, offer, vendor report", "Setup script; refresh with --refresh-reference"),
    ("planning_rules", "Table", "Minimum and target safety buffer, depot handling days, transfer carbon.", "Planner", "Setup script; editable"),
    ("approval_policy", "Table", "Tiers: AUTOPILOT up to $5,000, VP sign-off up to $50,000, CMO above.", "Sign-off", "Setup script; editable"),
    ("approvers", "Table", "Emails per role (VP Product Marketing, CMO, Launch Team).", "Sign-off, fulfilment", "Setup script (--approver-email)"),
    ("launch_requests", "Table", "Every brief registered by the root agent.", "Root", "Root"),
    ("requirement_lines", "Table", "The brief broken down per SKU and destination region.", "Planner", "Brief analyst"),
    ("scenarios", "Table", "The computed options per request (cost, delivery, buffer, carbon, risk, recommended).", "Root, sign-off", "Sourcing planner"),
    ("scenario_lines", "Table", "What each option does per line: reuse a depot or buy from a vendor; execution status.", "Sign-off, fulfilment", "Sourcing planner, fulfilment"),
    ("decisions", "Table", "The sign-off on the chosen option: tier, approver, status, workflow execution id.", "Root, fulfilment", "Root (authorize_launch, get_launch_status)"),
    ("depot_holds", "Table", "Surplus stock held for a pending or approved option (ACTIVE / CONSUMED / RELEASED).", "v_depot_available", "Root, fulfilment"),
    ("vendor_disruptions", "Table", "Reported vendor delays added to lead times.", "Planner", "Sourcing planner"),
    ("purchase_orders", "Table", "Purchase orders issued through Application Integration.", "Root, fulfilment", "Fulfilment"),
    ("depot_transfers", "Table", "Depot-to-region stock transfers.", "Root, fulfilment", "Fulfilment"),
    ("v_launch_readiness", "View", "Per request: chosen option, sign-off status, buffer, readiness colour, lines executed.", "Overview", "-"),
    ("audit_log", "Table", "Every governed action: who, what, when.", "Root (get_audit_trail)", "All agents and flows"),
]

AI = [
    ("create_purchase_order", "API trigger", "Create one purchase order per vendor for the approved option (all of that vendor's items together).", "request_id, plan_line_id, vendor_id, sku, quantity, total_amount, destination_region", "po_number (PO-<plan_line_id>), execution_id", "Data Mapping task builds the PO number and execution id.", "Fulfilment (execute_plan), one call per vendor line, in parallel", "After the sign-off is approved"),
    ("create_depot_transfer", "API trigger", "Create one stock transfer per warehouse for the approved option (all items together).", "request_id, plan_line_id, depot_id, sku, quantity, destination_region", "transfer_number (TR-<plan_line_id>), execution_id", "Data Mapping task builds the transfer number and execution id.", "Fulfilment (execute_plan), one call per depot line", "After the sign-off is approved"),
    ("request_approval", "API trigger (native approval)", "Executive sign-off: the run pauses until an approver decides.", "request_id, launch_id, approver_role, amount, approval_message", "decision (APPROVED / REJECTED)", "Approval task (suspension): emails the approver(s) Approve / Reject, reminder after 1 day, expires after 3 days; branch isApproved = true -> decision = APPROVED; false -> REJECTED. The click is recorded as an approval record (LIFTED = approved, REJECTED = rejected).", "Root (authorize_launch starts it over REST; get_launch_status reads the result)", "Chosen option above the autopilot limit"),
    ("send_launch_update", "API trigger", "Send the tracking update to one launch-team address.", "request_id, launch_id, recipient_email, email_subject, email_body", "status (SENT)", "Send Email task (one address per call), then Data Mapping sets status.", "Fulfilment, once per address of the role 'Launch Team'", "When every line of the plan is placed"),
]

FLOW = [
    (1, "PMM", "Sends the brief in Gemini Enterprise: 150 guest welcome kits, 10 venue display stands, 300 sales folders.", "-", "-", "-"),
    (2, "Root Agent", "register_launch_request", "Reads launches; writes launch_requests, audit_log", "-", "Request id REQ-xxxx"),
    (3, "Brief Analyst", "build_requirements (one call)", "Reads bundle_templates, guests, regional_split; writes requirement_lines", "-", "31 requirement lines, 1,210 units; hoodie sizes 20/45/60/25; plugs by region"),
    (4, "Sourcing Planner", "build_scenarios (one call)", "Reads offers, depot stock, lanes, rules; writes scenarios, scenario_lines", "-", "Option 1 $46,075.50 | Option 2 $37,399.50 (saves $8,676, 72 h buffer, recommended) | Option 3 $51,905.50 (eco)"),
    (5, "Root Agent", "Shows the 3-choices table and asks which option", "-", "-", "Waits for the manager"),
    (6, "PMM", "Replies: go with option 2", "-", "-", "-"),
    (7, "Root Agent", "authorize_launch", "Writes decisions (PENDING), depot_holds (ACTIVE), audit_log", "Starts request_approval; VP is emailed", "Reply opens with HUMAN APPROVAL REQUIRED; nothing ordered"),
    (8, "VP", "Clicks Approve (or Reject) in the Application Integration email", "-", "Approval record becomes LIFTED / REJECTED", "-"),
    (9, "PMM", "Asks: what is the status of that request?", "-", "-", "-"),
    (10, "Root Agent", "get_launch_status", "Reads decisions; Approved: decision APPROVED", "Reads the execution and approval record", "Approved: next step is fulfilment"),
    (11, "Fulfilment", "execute_plan (one call)", "Writes purchase_orders, depot_transfers, scenario_lines EXECUTED, depot_holds CONSUMED, audit_log", "create_purchase_order x27, create_depot_transfer x7, send_launch_update to the team", "34 orders placed, delivery date and buffer reported"),
    (12, "Rejected path", "get_launch_status releases the held depot stock", "depot_holds RELEASED, decisions REJECTED", "-", "Nothing ordered; the manager can choose another option"),
    (13, "Small brief", "Recommended option within the autopilot limit: authorize_launch approves by policy and fulfilment runs in the same turn", "decisions APPROVED by autopilot, then as step 11", "No approval workflow", "No human step"),
]

GOV = [
    ("Prompt", "The root instruction fixes the order of the steps; the specialists only return results to the root.", "launchkit_provisioner/agent.py, sub_agents/"),
    ("Data (policy)", "Sign-off tiers, approver emails, planning rules and all option inputs are BigQuery tables, changed without a release.", "approval_policy, approvers, planning_rules"),
    ("Computed numbers", "Costs, dates, buffers, savings and carbon come from the planner, never from the model; the specialists repeat them verbatim.", "planner.py, scenarios"),
    ("Platform", "The Application Integration approval pauses the flow until a person decides.", "request_approval trigger"),
    ("Code guard", "Nothing is ordered unless the sign-off is APPROVED, never beyond the authorised amount, and never twice; an option that misses the deadline cannot be authorised.", "execution.py, decision_flow.py"),
    ("Stock holds", "Surplus stock is held while a sign-off is pending, consumed on transfer, released on rejection or failure.", "depot_holds, v_depot_available"),
    ("Audit", "Every governed action is written to the BigQuery audit log.", "audit_log"),
    ("Output", "No commentary between steps: some chat front ends treat the first text as the end of the answer.", "Root and specialist instructions"),
]

HEAD_FILL = PatternFill("solid", fgColor="1F3A8A")
BAND = PatternFill("solid", fgColor="EEF3FF")
THIN = Side(style="thin", color="C9D3EA")


def sheet(wb, title, headers, rows, widths):
    ws = wb.create_sheet(title)
    ws.append(headers)
    for r in rows:
        ws.append(list(r))
    for c in range(1, len(headers) + 1):
        h = ws.cell(row=1, column=c)
        h.font, h.fill = Font(bold=True, color="FFFFFF"), HEAD_FILL
        h.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(c)].width = widths[c - 1]
    for r in range(2, ws.max_row + 1):
        for c in range(1, len(headers) + 1):
            cell = ws.cell(row=r, column=c)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            cell.border = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)
            if r % 2 == 1:
                cell.fill = BAND
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 30
    return ws


SUMMARY = [
    ("Root Agent", "LaunchKit Provisioner Agent (Orchestrator)",
     "The root agent acts as a front-line coordinator by taking the launch brief, registering the request and delegating to the brief "
     "analyst, sourcing planner and fulfilment agents in a fixed order. It shows the manager a 3-choices table with three computed "
     "options and incorporates a critical human-in-the-loop sign-off gate: above the autopilot limit it starts an Application "
     "Integration approval, tells the user that an approval email was sent, and holds every order until the executive approves. Once "
     "approved it has the orders placed; if rejected it releases the held depot stock.",
     "BigQuery, Application Integration", 150),
    ("Sub Agent", "Brief Analyst Agent",
     "The brief analyst agent turns the free-text brief into requirement lines in one call: guest welcome kits personalised by hoodie size and "
     "power plug from the BigQuery guest list, venue display stands and sales folders spread over the regions.",
     "BigQuery", 95),
    ("Sub Agent", "Sourcing Planner Agent",
     "The sourcing planner agent audits regional depot surplus and vendor lead times and computes three options (buy everything new, use our stock first, "
     "green option) with cost, delivery date, safety buffer before the in-hand deadline, savings and carbon. It re-plans when a "
     "vendor reports a delay.",
     "BigQuery", 110),
    ("Sub Agent", "Fulfilment Agent",
     "The fulfilment agent places the orders of the approved option in one batch through Application Integration: a purchase order per "
     "vendor line, a depot transfer per surplus line and a tracking update to the launch team. It refuses to order without an approved "
     "sign-off or beyond the authorised amount.",
     "BigQuery, Application Integration", 95),
]


def summary_sheet(wb):
    """The one-table summary in the same layout as the container agent reference: no header row, application and owner
    merged over all rows, then agent type, agent name, description, data sources."""
    ws = wb.create_sheet("Agent Summary", 0)
    grey = Side(style="thin", color="BFBFBF")
    box = Border(top=grey, bottom=grey, left=grey, right=grey)
    for i, (kind, name, desc, src, height) in enumerate(SUMMARY, start=1):
        for col, val in enumerate(("LaunchKit Provisioner Agent (Product Launch Collateral Planner)", OWNER, kind, name, desc, src), start=1):
            if i == 1 or col > 2:
                ws.cell(row=i, column=col, value=val)
        ws.row_dimensions[i].height = height
    n = len(SUMMARY)
    ws.merge_cells(start_row=1, start_column=1, end_row=n, end_column=1)
    ws.merge_cells(start_row=1, start_column=2, end_row=n, end_column=2)
    for r in range(1, n + 1):
        for c in range(1, 7):
            cell = ws.cell(row=r, column=c)
            cell.border = box
            cell.font = Font(name="Calibri", size=11)
            cell.alignment = Alignment(wrap_text=True, vertical="center" if c < 5 else "top",
                                       horizontal="center" if c in (3,) else "left")
    for c, w in enumerate([24, 14, 10, 20, 78, 22], start=1):
        ws.column_dimensions[get_column_letter(c)].width = w


def main():
    wb = Workbook()
    wb.remove(wb.active)
    summary_sheet(wb)
    sheet(wb, "Agents", ["Application", "Owner", "Agent Type", "Agent Name", "Description", "Data sources and integrations"],
          [(APP, OWNER, t, n, d, s) for t, n, d, s in AGENTS], [34, 18, 13, 26, 90, 46])
    sheet(wb, "Tools", ["Agent", "Tool", "Kind", "What it does", "BigQuery reads", "BigQuery writes", "Application Integration", "Guardrail"],
          TOOLS, [18, 30, 26, 60, 38, 42, 34, 44])
    sheet(wb, "BigQuery", ["Table / view", "Type", "Purpose", "Read by", "Written by"], BQ, [26, 8, 62, 34, 40])
    sheet(wb, "Application Integration", ["Trigger", "Type", "Purpose", "Inputs", "Outputs", "Tasks", "Called by", "When"],
          AI, [24, 18, 34, 44, 34, 70, 44, 26])
    sheet(wb, "Flow (HITL example)", ["Step", "Who", "Action", "BigQuery", "Application Integration", "Result"],
          FLOW, [6, 26, 46, 52, 40, 52])
    sheet(wb, "Governance", ["Layer", "Rule", "Where"], GOV, [16, 90, 46])
    wb.save(OUT)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
