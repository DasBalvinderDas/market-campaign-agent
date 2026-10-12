# The LaunchKit Provisioner: solution guide

## 1. The problem

A flagship launch has to equip several channels at once before a hard date: VIP guests (unboxing kits with the right hoodie
size and power plug), venues (display stands) and enterprise sales teams (folders and brochures), in several regions,
**in hand before the in-hand deadline, which sits before the global press embargo**. The people planning it face:

- a long list of personalised items to work out from a guest list;
- surplus packaging and folders sitting in regional depots that nobody checks before new manufacturing is ordered;
- vendor lead times and regional shipping that decide whether the date is made, with a delay at one vendor changing everything;
- finance seeing only "approve this spend?" with no view of the alternatives.

## 2. What the agent does differently

It is a **launch-readiness planner**. The question it answers is "which way do we hit the date, and at what cost?", not "may we spend?".

| Aspect | A spend approval agent | The LaunchKit Provisioner |
|---|---|---|
| Unit of work | A purchase amount | A launch brief: bundles, sizes, plugs, regions |
| What the human sees | Yes / No on a number | A 3-choices table with three computed options: cost, arrival, safety buffer (hours), savings, carbon, risk |
| Stock | Checks a catalog | Reuses surplus depot stock first, nearest depot first, and **holds** it while a sign-off is pending |
| Deadline | Not modelled | Every option is costed against the in-hand date; vendors are chosen to keep a safety buffer |
| Change of plan | Start again | A vendor delay re-plans the options; after sign-off it reports the impact on the buffer |
| Approval | Gate for every purchase | Autopilot below a limit; above it a VP (or the CMO for the largest tier) signs off the **chosen option** |
| Result | An approval status | Purchase orders, depot transfers, a tracking update, a readiness board (GREEN / AMBER / RED) and an audit trail |

## 3. Architecture

```
 PMM brief (Gemini Enterprise chat)
        |
        v
 launchkit_provisioner  (root agent: writes every reply, holds the sign-off gate)
        |  calls the specialists as tools (ADK AgentTool)
        +-- brief_analyst_agent      build_requirements    -> requirement lines per SKU and region
        +-- sourcing_planner_agent   build_scenarios       -> 3 options computed and stored
        |                            report_vendor_delay   -> delay recorded, re-plan or impact
        +-- fulfilment_agent         execute_plan          -> POs, depot transfers, tracking update
        |
        |  root tools: register_launch_request, authorize_launch (the gate), get_launch_status,
        |              get_launch_overview, get_audit_trail
        v
 BigQuery (dataset launchkit)         Application Integration (launchkit-workflows)
   reference data, plan, decisions,     create_purchase_order, create_depot_transfer,
   orders, audit, views                 request_approval (Approve / Reject email), send_launch_update
```

The root agent calls each specialist as a tool and writes every reply. This is deliberate: chat front ends such as Gemini Enterprise
show the root agent's answers, and stopped displaying a run when a specialist took over the chat. Each specialist is still its own LLM
agent with its own prompt, tools and error handling. They use **batch tools** (one call per step), so a request needs a handful of model
calls instead of one per item.

## 4. The scenario engine (`launchkit_provisioner/planner.py`)

Everything the manager sees is computed from BigQuery data by deterministic code; the model never types a number.

1. **Requirement lines.** `bundle_templates` say what is in a guest welcome kit (box, hoodie by size, power adapter by plug, engraved
   plaque), a venue display stand and a sales folder. Guest kits follow the `guests` list (sizes and plugs per region, scaled to the
   quantity with largest-remainder rounding, so totals are exact); other bundles follow `regional_split` or a region the brief names.
2. **Three options.**
   - *Buy everything new*: every line from the cheapest standard vendor offer, ignoring the deadline.
   - *Use our stock first, buy the rest*: surplus depot stock first (nearest depot first, per SKU), the rest from the cheapest standard offer
     that keeps at least `TARGET_BUFFER_HOURS` before the in-hand date, otherwise the fastest offer.
   - *Go green*: eco offers with the same deadline-aware choice, falling back to a standard offer for a line where no eco offer can
     make the date.
3. **Metrics per option.** Cost (product plus lane shipping), delivery date (the slowest line: vendor lead time plus any reported
   delay plus transit, or depot handling plus transit), buffer hours against the in-hand date, savings versus buy everything new, carbon (vendor
   carbon per unit, or transfer carbon for reused stock), and a risk label (LOW / MODERATE / HIGH).
4. **Recommendation.** The cheapest option that keeps `MIN_BUFFER_HOURS`. If none does, the one with the most buffer (then the
   cheapest) is flagged and its risk says why. An option that misses the in-hand date cannot be authorised.
5. **Decision mode.** If the recommended option is within the autopilot limit the root agent runs it by itself; otherwise it shows the
   3-choices table and waits for the manager's choice.

With the demo data (Spring Launch Event, 150 guest welcome kits, 10 displays, 300 folders) the options come out as: Buy everything new $46,075.50 with
0 hours of buffer; **Use our stock first, buy the rest $37,399.50, saves $8,676.00, 72 hours of buffer (recommended)**; Go green $51,905.50 with
48 hours of buffer and 1,822 kg less carbon than buy everything new. Choosing eco crosses $50,000, so the CMO signs off instead of the VP.

## 5. The sign-off (`launchkit_provisioner/decision_flow.py`)

`authorize_launch` is the only way to approve anything and only the root agent has it.

1. The chosen option must exist, meet the in-hand date and its surplus depot stock must still be free.
2. The tier comes from `approval_policy` and the amount is the stored scenario total (not what the model says).
3. **Autopilot** (within the limit): the decision is approved by policy and the surplus stock is held.
4. **Executive sign-off**: the decision is stored as PENDING, the surplus stock is held, and the Application Integration
   `request_approval` workflow starts. Its native Approval task pauses the run and emails the approver(s) an approval request with the
   option, total, savings, arrival and risk, and Approve / Reject. The reply starts with **HUMAN APPROVAL REQUIRED** and names the
   approver and the amount. Nothing is ordered.
5. **After the click** the manager asks for the status. `get_launch_status` reads the workflow's approval record (`LIFTED` = approved,
   `REJECTED` = rejected), records the decision once (atomic update, first decision wins) and tells the root agent to call the
   fulfilment agent. A rejection, a failed workflow or an expired sign-off releases the held stock.

## 6. Fulfilment (`launchkit_provisioner/execution.py`)

`execute_plan` is one deterministic batch. It refuses unless the decision is APPROVED, refuses to go beyond the authorised amount and
skips lines already placed (so calling it twice never orders twice). The workflows for all lines are started **in parallel**
(`create_purchase_order` per vendor line, `create_depot_transfer` per surplus line), the results are written to BigQuery **in bulk**,
and when every line is placed `send_launch_update` emails the launch team. The model never fills an order field: every SKU, vendor,
depot, quantity and amount comes from the stored plan.

## 7. BigQuery data model

Full DDL: [`bigquery/schema.sql`](../bigquery/schema.sql) (generated from `launchkit_provisioner/data/schema.py`).

| Group | Tables and views |
|---|---|
| Reference data | `launches`, `assets`, `bundle_templates`, `guests`, `regional_split`, `depots`, `depot_stock`, `transit_lanes`, `vendors`, `vendor_offers`, `planning_rules`, `approval_policy`, `approvers` |
| Plan and decision | `launch_requests`, `requirement_lines`, `scenarios`, `scenario_lines`, `decisions`, `depot_holds`, `vendor_disruptions` |
| Orders and audit | `purchase_orders`, `depot_transfers`, `audit_log` |
| Views | `v_depot_available` (free surplus = on hand minus active and consumed holds), `v_launch_readiness` (per request: chosen option, sign-off, buffer, GREEN / AMBER / RED, lines executed) |

Stock and orders are append-only records; availability and readiness are computed by the views. The demo launch dates are relative
to the day the data is set up (in-hand +25 days, embargo +32 days), and `--reset-demo` moves them to today.

## 8. Application Integration

Four API triggers in one integration (`launchkit-workflows`), created and published by `scripts/setup_application_integration.py`:
`create_purchase_order`, `create_depot_transfer` (Data Mapping tasks), `request_approval` (native Approval task with Approve and
Reject branches) and `send_launch_update` (Send Email task). Variables and tasks are in [`integration/README.md`](../integration/README.md).
The recipients are data: sign-off approvers and the launch team come from the BigQuery `approvers` table (the approval step's own
recipients are set with `--approver-email` when the integration is published).

## 9. Governance in layers

| Layer | Mechanism |
|---|---|
| Prompt | The root instruction fixes the order; the specialists only return results to the root |
| Data | Tiers, approvers and planning rules are BigQuery tables |
| Computed numbers | The planner computes every figure; the specialists repeat them verbatim |
| Platform | The Application Integration approval pauses the flow until a person decides |
| Code | Only `authorize_launch` approves; an infeasible option cannot be authorised; orders need an APPROVED decision, stay within the authorised amount and are idempotent |
| Stock | Surplus is held while pending, consumed on transfer, released on rejection or failure |
| Audit | Every governed action goes to `audit_log` |

## 10. Choices made to make it better than the first sketch

The first sketch of this solution (a sequential agent pipeline with hard-coded scenarios) had gaps that this build closes:

| Gap in the sketch | What this build does |
|---|---|
| Scenario costs, dates and savings were typed constants | Computed from BigQuery data by the planner and stored; the card repeats stored numbers |
| A fixed `SequentialAgent` runs every stage whatever the request | The root calls specialists as tools in the order the situation needs (skip the card on autopilot, re-plan on a delay) and works in Gemini Enterprise |
| The 3-choices table needed a public callback to resume the run | The choice is made in the chat; the executive signs off through Application Integration's own approval email (no public endpoint) |
| An "approve" resumed with a made-up PO number and fixed depot transfers | Orders and transfers come from the approved plan lines, each with an id, and are recorded in BigQuery |
| Stock was only audited | Surplus is **held** while a sign-off is pending, consumed on transfer, released on rejection |
| Mock data switched by an environment variable | Real tables, set up and re-set by scripts; no mock mode |
| One order call per item through the model | Batch tools and a parallel execution step keep a request to a handful of model calls |
| No guard against ordering without approval, twice, or beyond the amount | Code refuses all three |
| Deadline risk was text | Buffer hours are computed per option; an option that misses the date cannot be authorised; vendor delays re-plan |

## 10a. How the answers are written (`launchkit_provisioner/presentation.py`)

Every answer is built by code from stored data and shown by the root exactly as returned. This keeps the wording simple and the numbers
identical to BigQuery.

| What the user reads | Built by | Data used |
|---|---|---|
| "Hi" card: what I can do, what I need | `capabilities_card` (tool `show_capabilities`) | none |
| **Step 1** shopping list (Bill of Materials) | `bom_markdown` (Brief Analyst) | `requirement_lines`, `bundle_templates`, `assets` |
| **Step 2** vendors we compared, stock we already own | `vendor_report` (Sourcing Planner, tool `get_vendor_report`) | `vendor_offers`, `vendor_disruptions`, depot stock, the saved plan |
| **Step 3** three choices in one table with friendly names | `decision_card` | `scenarios`, `approval_policy` |
| **Step 4** getting the OK (approval ladder, tracker) | `sign_off_markdown`, `approval_ladder` (tool `get_approval_rules`) | `approval_policy`, `approvers` |
| After the orders: the story, vendors and why, why so many orders | `order_summary` (Fulfilment) | `scenario_lines`, `vendor_offers`, `decisions` |
| Status, board, audit as tables | `status_markdown`, `board_markdown`, `audit_markdown` | views and tables |
| Launch-team tracking email | `_update_email` (HTML, sent by `send_launch_update`) | the plan |

**Guided questions and advice:** the first question is *whole campaign or selected items?* (both work, the whole campaign is encouraged); the second is the campaign name, because the user is creating the campaign. Every question turn shows a ✅/⬜ checklist (`show_checklist`). Before planning, `advisor.py` checks the shopping list with plain rules (spares from `SPARE_PERCENT`, a kind of bundle that is missing, the rest of a bundle for a single item, a date the vendors cannot meet) and the user adds something or says *Looks good*. The plan opens with a 📌 *In short* box.

**Guided questions:** the root asks one question at a time (whole campaign or selected items, campaign name, date, what is needed), looks up stock and vendors itself, and shows stock, vendor *ready-by* dates and the three choices before anything is approved. The user can change the plan until they choose. A single item is a shorter run of the same steps (`ItemRequest`), and an unknown event name is created with the date given (`EVT-...`; `--reset-demo` removes such events).

The root prompt sets the style (short words a 10-year-old can follow, tables, icons) and the order of the one message after prompt 1:
shopping list, vendors, three choices, then the question. The multi-level approval (automatic, VP, CMO) is the `approval_policy`
table, shown as a ladder with the current order marked.

**Approve / Reject in the email:** the two links come from Application Integration's approval step, whose email layout cannot be styled from
our side. A real button needs our own small approval page (a new Cloud Run service), which is not built because it adds a service.

## 11. Assumptions and limitations

- **Demo data** is fictional (Spring Launch Event, vendors, prices, depots, guests). Currency is USD; no tax, duties or partial deliveries.
- **SAP S/4HANA, Slack and Teams** are not connected. The purchase order and depot transfer are Application Integration workflows that
  create a number (`PO-<line id>`, `TR-<line id>`); tracking updates go by email. Connecting a real ERP or chat tool is the next step
  and only changes the workflows, not the agents.
- Option inputs are simplified: delivery uses calendar days, one lane per region pair, no vendor capacity limits, no partial shipments.
- The choice among the three options is made in the chat. A one-click choice inside the executive's email would need a public
  callback endpoint, which Application Integration's approval (Approve / Reject only) does not provide.
- The decision is carried out when the user asks for the status (a second message), not at the click, because the workflow has no
  public callback into the agent.
- The approval step's recipients are fixed in the published integration version (re-run the setup script with `--republish` to change
  them); the addresses the agent names come from the BigQuery `approvers` table, so keep both in step.
- The `request_approval` workflow follows Google's published approval-task pattern and was verified on a real project for the earlier
  version of this agent. The four workflows of this version have not been run on a real project yet (see `docs/DEMO_RUN.md`, section 7).
- Two users planning in parallel can compete for the same surplus stock; the hold is taken at sign-off time and stock is re-checked
  before it, but there is no locking beyond that.
