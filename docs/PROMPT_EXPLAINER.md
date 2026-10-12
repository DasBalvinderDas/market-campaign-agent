# Prompt explainer: what happens behind every demo prompt

Use this file in two ways:

1. **Context for the agent or for yourself:** read section 1 first. It is the whole picture in one page.
2. **Presenting:** for each prompt, section 4 and later give the business story first ("what the person wants and gets"), then the
   technical story ("who is called, which table is read or written, what goes to Application Integration").

Test prompts and expected numbers are in [`DEMO_RUN.md`](DEMO_RUN.md); the design is in [`SOLUTION.md`](SOLUTION.md).

---

## 1. The picture in one page

**Business.** A global product launch (Project Aurora) needs 1,500+ personalised items in hand before an in-hand date and a press
embargo: creator unboxing kits, showroom displays, sales folios. The agent turns a launch brief into three costed, deadline-checked
options, reuses surplus depot stock before buying, gets an executive to sign off on the chosen option, and places the orders.

**Technical.** One **root agent** plus three **specialist agents that the root calls as tools** (ADK `AgentTool`). The root writes every
reply the user sees. The specialists hold their own prompt and tools but never talk to the user and never approve spend.

```
User (Gemini Enterprise chat)
   |
   v
ROOT  launchkit_provisioner  (Vertex AI Agent Engine)
   |  own tools: register_launch_request, authorize_launch, get_launch_status,
   |             get_launch_overview, get_audit_trail
   |
   |--(AgentTool)--> brief_analyst_agent     tool: build_requirements
   |--(AgentTool)--> sourcing_planner_agent  tools: build_scenarios, report_vendor_delay
   '--(AgentTool)--> fulfilment_agent        tool: execute_plan
                          |
        tools call plain Python (planner.py, decision_flow.py, execution.py)
                          |
          +---------------+-----------------+
          v                                 v
   BigQuery dataset `launchkit`      Application Integration `launchkit-workflows`
   (all facts, plans, decisions,     create_purchase_order, create_depot_transfer,
    holds, orders, audit)            request_approval (human), send_launch_update
```

### The diagram in plain business English

Think of the agent as a **launch coordinator with three specialist colleagues**.

- You talk to **one person only**, the coordinator (the root agent). Everything you read in the chat comes from them.
- Behind the coordinator are three specialists. The **brief analyst** turns your request into a shopping list (what, how many, for which
  region). The **sourcing planner** works out the three ways to get it done and what each costs. The **fulfilment** specialist places the
  orders, but only once a decision has been signed off.
- The specialists never speak to you and never approve spending. They report back to the coordinator, who decides what happens next.
- The coordinator relies on two company systems. The **database** (BigQuery) is the filing cabinet: stock levels, vendor prices,
  delivery times, who may approve what, and a record of every step. The **workflow system** (Application Integration) is the back office:
  it raises the purchase orders, moves stock between depots, sends the approval email to the executive, and sends the update to the
  launch team.
- The coordinator is the only one allowed to ask for a sign-off, so spending always goes through the same door.

**In one sentence:** one coordinator talks to you, three specialists do the preparation, and two company systems hold the facts and do the
paperwork. Nothing is ordered until the right person has said yes.

### The diagram in plain technical English

- The agent runs as a single deployment on Google's agent hosting service (Vertex AI Agent Engine). Gemini Enterprise sends your chat
  message to it and shows whatever the **root agent** answers.
- The three specialists are **not separate deployments**. They are wrapped as tools of the root agent. When the root "calls" one, that
  specialist runs its own short prompt, calls its own single tool, and returns text to the root. This is why Gemini Enterprise always
  shows one clean answer: only the root writes to the chat.
- Each specialist's tool is an ordinary Python function. The functions do the real work (cost, delivery date, buffer, savings), so the
  language model never does any arithmetic. It decides which tool to call and writes the final wording.
- The Python code reads and writes **BigQuery** (dataset `launchkit`) using the agent's service account.
- For anything that must happen outside the agent (purchase order, transfer, approval email, tracking email) the code calls the
  **Application Integration** REST API and gets back a number or an answer.
- The approval workflow waits for the executive's click. The agent does not receive a callback. It reads the answer from the workflow the
  next time you ask for the status, so no public web address is needed.
- The rules (no order without approval, never above the approved amount, never twice) are in the Python code, so they hold even if the
  language model were asked to break them.

**Who does what**

| Layer | Role | Decides the numbers? |
|---|---|---|
| Model (Gemini) | Understands the brief, picks the tool, writes the reply | No. It never calculates; it only repeats tool output |
| Python (`planner.py`) | Cost, shipping, delivery date, buffer, savings, carbon, risk | Yes, deterministically |
| BigQuery | Single source of truth and audit trail | Holds the data |
| Application Integration | Purchase orders, transfers, the executive email, the tracking update | Executes and returns PO/transfer numbers and the Approve/Reject answer |

**Why root-plus-tools.** Gemini Enterprise shows the root's reply. When an earlier design handed the whole conversation to a
sub-agent with narrated text, Gemini Enterprise stopped displaying the run. Here the specialist's reply goes back to the root, and the
root writes the one final message. The root's prompt also says: no narration between calls.

**The four rules the code enforces (not just the prompt)**

1. No orders unless the decision is `APPROVED` (`execution.py`).
2. Never spend more than the approved amount.
3. Never place the same line twice (idempotent; placed lines are skipped).
4. An option that cannot meet its stock or deadline cannot be authorised.

---

## 2. The roles and their prompts

| Agent | Prompt in one line | Tools | Reads | Writes |
|---|---|---|---|---|
| **Root** `launchkit_provisioner` | Collect the brief, call specialists in a fixed order, show the card, wait for the user's choice, gate spend, summarise. No narration. Never skip approval | `register_launch_request`, `authorize_launch`, `get_launch_status`, `get_launch_overview`, `get_audit_trail`, + the 3 specialists | `launches`, `approval_policy`, `approvers`, `decisions`, views | `launch_requests`, `decisions`, `depot_holds`, `audit_log` |
| **Brief Analyst** | Call `build_requirements` once with every bundle (CREATOR_KIT, SHOWROOM_DISPLAY, SALES_FOLIO) and quantity; report totals. Never invent a bundle or quantity | `build_requirements` | `bundle_templates`, `creators`, `regional_split`, `assets`, `launch_requests` | `requirement_lines`, `audit_log` |
| **Sourcing Planner** | Call `build_scenarios` once; on a vendor delay call `report_vendor_delay` first. Return the decision card exactly; never recompute | `build_scenarios`, `report_vendor_delay` | `requirement_lines`, `v_depot_available`, `vendor_offers`, `vendors`, `vendor_disruptions`, `transit_lanes`, `planning_rules`, `assets`, `approval_policy` | `scenarios`, `scenario_lines`, `vendor_disruptions`, `audit_log` |
| **Fulfilment** | Call `execute_plan` once; report orders, transfers, total, savings, delivery date, buffer. If BLOCKED say so and do not retry | `execute_plan` | `decisions`, `scenarios`, `scenario_lines`, `approvers` (Launch Team) | `purchase_orders`, `depot_transfers`, `scenario_lines` (status), `depot_holds` (consumed), `audit_log` |

Root workflow in its prompt (paraphrased): **1** collect launch and bundles, **2** register, **3** Brief Analyst, **4** Sourcing Planner,
**5** autopilot or choose, **6** authorise the chosen option, **7** on a status question read the decision and place orders if approved,
**8** on a vendor delay re-plan.

---

## 3. Application Integration: how the code talks to it

All calls go through `IntegrationExecutor` (`workflow/integration_client.py`) to the REST API
`integrations.googleapis.com/v1/projects/<project>/locations/<region>/integrations/launchkit-workflows:execute`, authenticated as the
agent's service account (`AGENT_SERVICE_ACCOUNT`). No public endpoint, no webhook back into the agent.

| Trigger | Called by | Inputs | Returns | What the workflow does |
|---|---|---|---|---|
| `create_purchase_order` | Fulfilment, one call per vendor line | request_id, plan_line_id, vendor_id, sku, quantity, total_amount, destination_region | `po_number` (`PO-` + plan line), execution_id | Data Mapping task builds the PO number (simulated ERP/SAP) |
| `create_depot_transfer` | Fulfilment, one call per depot line | request_id, plan_line_id, depot_id, sku, quantity, destination_region | `transfer_number` (`TR-` + plan line), execution_id | Data Mapping task builds the transfer number |
| `request_approval` | Root via `authorize_launch`, only above the autopilot limit | request_id, launch_id, approver_role, amount, approval_message | executionId | Native **Approval task** emails Approve / Reject to the approvers and **suspends** the execution |
| `send_launch_update` | Fulfilment, once per Launch Team address when all lines are placed | request_id, launch_id, recipient_email, email_subject, email_body | none | Send Email task to the Launch Team |

**How the human answer comes back without a callback.** The approval workflow stays suspended. When the user later asks for the status,
`get_launch_status` reads the execution and its approval records: `LIFTED` = approved, `REJECTED` = rejected, `PENDING` = not clicked yet.
That is why the demo is two steps: send the prompt, click the email, ask for the status.

---

## 4. Prompt by prompt

Each prompt: **Business** (say this first), then **Technical** (the flow). Numbers are from the seeded Project Aurora data.

### Prompt 1: the launch brief

> Roll out the global launch kits for Project Aurora. I need 150 VIP creator unboxing kits (personalised hoodie size and power plug for each creator), 10 showroom counter displays for our flagship spaces, and 300 executive folios for the sales team. Everything has to be in hand before the in-hand deadline.

**Business.** The launch lead describes the whole rollout in one sentence. They get back, in about a minute, three ways to do it, each with
cost, arrival date and safety margin before the deadline, plus a recommendation. They can see where money is saved by reusing stock
that is already sitting in depots.

**Technical flow**

| # | Who | Action | Table | Application Integration |
|---|---|---|---|---|
| 1 | Root | `register_launch_request("LAUNCH-AURORA", summary)` | reads `launches`; writes `launch_requests`, `audit_log` | none |
| 2 | Root -> **Brief Analyst** | Prompt tells it to call `build_requirements` once with all three bundles | | none |
| 3 | Brief Analyst | `expand_bundles`: creator kits become one line per size / plug / region from the real creator list; displays and folios follow the regional split | reads `bundle_templates`, `creators`, `regional_split`, `assets`; writes `requirement_lines`, `audit_log` | none |
| 4 | Root -> **Sourcing Planner** | `build_scenarios(request_id)` | | none |
| 5 | Sourcing Planner | `plan_scenarios`: prefetches vendor offers, assets and free depot stock in bulk, then builds three options. **Depot rebalance** takes surplus nearest-depot first; **new** picks the cheapest vendor that makes the date (target buffer 48 h, minimum 24 h); **eco** prefers certified material, standard where eco cannot make the date. Recommends the cheapest option with buffer of at least 24 h | reads `requirement_lines`, `v_depot_available`, `vendor_offers`, `vendors`, `vendor_disruptions`, `transit_lanes`, `planning_rules`, `launches`; writes `scenarios`, `scenario_lines`, `audit_log` | none |
| 6 | Sourcing Planner | Returns the formatted `decision_card` and `decision_mode` (AUTOPILOT if the recommended option is within $5,000, else CHOOSE) | reads `approval_policy` | none |
| 7 | Root | Prints the card exactly and asks which option. **Stops.** Nothing is authorised | | none |

**What the user sees:** Option 1 full new $46,075.50 (0 h buffer), Option 2 depot rebalance $37,399.50 recommended (saves $8,676, 72 h
buffer), Option 3 eco $51,905.50 (48 h buffer).

**In plain English (technical).** The coordinator first files the request and gets a reference number. It then briefs the analyst, who looks up the creator list and the regional split and writes one line per item and region. Next the planner reads current stock, vendor prices and delivery times and works out three plans, applying simple rules: use surplus stock first and from the nearest depot, buy from the cheapest vendor that still arrives with a safety margin, and prefer certified eco material where it makes the date. Everything is saved, the coordinator shows the card and waits.

**Say:** "The model did not calculate any of this. It called three tools; the Python planner computed the numbers from BigQuery. Change a
vendor price or a depot stock and the card changes."

---

### The three options: what changes and why they differ

Prompt 1 always produces the same three options for the same brief. The brief does not change between them; **where the items come from,
when they arrive and what they cost** does. Business language first:

| | **Option 1: Full new production** | **Option 2: Smart depot rebalance** (recommended) | **Option 3: Certified eco launch** |
|---|---|---|---|
| **The idea** | Buy everything new from the cheapest vendors | Use stock already sitting in our regional depots first, buy only the rest | Buy certified sustainable material wherever it can make the date |
| **What we do** | 1,210 units manufactured new | 240 units moved from depots, 970 bought | 1,034 units on eco material, 176 on standard where eco cannot make the date |
| **Cost** | $46,075.50 | **$37,399.50** (saves $8,676) | $51,905.50 (about $5,830 more than option 1) |
| **Arrives** | 2026-11-06, the day of the deadline | 2026-11-03 | 2026-11-04 |
| **Safety buffer before the in-hand date** | **0 hours** | **72 hours** | 48 hours |
| **Carbon** | 4,200 kg | 3,702 kg | **2,378 kg** (lowest) |
| **Risk** | MODERATE: any slip misses the deadline | LOW | LOW |
| **Who signs off** | VP Product Marketing (over $5,000) | VP Product Marketing (over $5,000) | **CMO** (over $50,000) |
| **Business message** | Simple, but no room for error and money spent on stock we already own | Cheapest, safest and greenest than option 1: we stop buying what we already have | Best for sustainability, at a premium, and a more senior approver |

**Why the numbers move**

- **Option 2 is cheaper** because 240 units are not bought at all; the only cost is moving them between depots, and the nearest depot is used first.
- **Option 2 is safer** because a depot transfer is faster than manufacturing, so the goods arrive earlier and the buffer grows from 0 to 72 hours.
- **Option 3 costs more** because certified eco material is priced higher. It still has to make the date, so where an eco vendor
  cannot, the plan uses a standard vendor for those 176 units. That is why it shows "eco" and "standard" together.
- **The recommendation is a rule, not an opinion:** the cheapest option that still keeps at least the minimum safety buffer
  (24 hours, a data setting). Option 1 is cheaper than option 3 but has no buffer, and option 2 beats both.
- **The approver changes with the amount.** The sign-off level comes from the approval table, so choosing option 3 sends the email to
  the CMO while options 1 and 2 go to the VP. A very small brief would not need anyone (autopilot, up to $5,000).

**Technical, in plain English.** All three options are built from the same requirement lines, using the same data. For each line the
planner asks: is there free depot stock, and how far away is it? what does each vendor charge, how long do they take, are they
delayed? Then it adds up cost (items plus shipping), works out the arrival date from the slowest line, and subtracts it from the
in-hand date to get the buffer. The three options only differ in the rule applied at the "where does this line come from" step:
cheapest vendor, depot stock first, or certified eco first.

**How to demo "Option 1 / Option 2 / Option 3"**

Once you choose, the choice is **final for that request**: while a sign-off is pending or approved, the agent will not switch to
another option (it says a sign-off already exists). That is deliberate, so nobody can change a decision after an executive has been emailed.
So to show the three side by side:

| You want to show | What to do |
|---|---|
| The comparison | Stay on the prompt 1 reply. Read the card aloud; do not choose yet |
| Option 2 end to end | In the same chat: "Go with option 2." -> click Approve -> ask the status |
| Option 3 and the CMO | `python scripts/setup_bigquery.py --reset-demo`, **new chat**, send prompt 1, then "Go with option 3, the eco launch." |
| Option 1 | Same: reset, new chat, prompt 1, then "Go with option 1." |
| Change your mind after a **Reject** | Reject releases the held stock; ask to re-plan and choose again in the same chat |

So you do not need to keep re-running prompt 1 inside one chat. Run it once per fresh demo, then continue with the follow-up prompts in the same conversation.

### Prompt 2: choose an option (human in the loop)

> Go with option 2.

**Business.** The launch lead picks the recommended option. Because $37,399.50 is above the $5,000 autopilot limit, the VP Product
Marketing must sign off. The agent says so clearly, emails the executive, and keeps the surplus stock held for this launch while it
waits. Nothing is ordered yet.

**Technical flow**

| # | Who | Action | Table | Application Integration |
|---|---|---|---|---|
| 1 | Root | `authorize_launch(request_id, "Option 2", justification)` | reads `scenarios`, `scenario_lines` | none |
| 2 | Code | Resolves the option text ("2", "rebalance", "sustainable" all work), rejects infeasible options, re-checks the stock is still free | reads `v_depot_available` | none |
| 3 | Code | Finds the tier from the amount: `AUTOPILOT` up to $5,000, `VP_SIGNOFF` up to $50,000, `CMO_SIGNOFF` above | reads `approval_policy`, `approvers` | none |
| 4 | Code | Creates the decision as `PENDING` with an expiry, and **holds** the depot stock so nobody else can take it | writes `decisions`, `depot_holds` (ACTIVE) | none |
| 5 | Code | Starts the approval workflow with the amount, role and a message listing the option, savings, buffer | writes `audit_log` | **`request_approval`** starts; email with Approve / Reject goes to the approvers; execution suspends. The execution id is stored on the decision |
| 6 | Root | Replies starting with **HUMAN APPROVAL REQUIRED** (the exact `announce` text), then tells the user to ask for the status after the click. It does **not** call Fulfilment | | none |

**In plain English (technical).** The coordinator passes your choice to the sign-off tool. The tool checks the choice is valid and the stock is still there, looks up who must approve for that amount, saves the decision as waiting, and puts a hold on the surplus stock so no other request can take it. It then asks the workflow system to email the executive. The workflow pauses until the executive clicks. The coordinator tells you, in bold, that approval is required and nothing has been ordered.

**Say:** "Approval is the last gate, on a chosen option, not the product. The root is the only agent with `authorize_launch`, so no
specialist can approve spend."

---

### Prompt 2b: the approver clicks, then "What is the status?"

> What is the status of REQ-xxxx?

(The reply from prompt 2 contains the exact sentence.)

**Business.** The executive clicks Approve in their email. When the launch lead asks for the status, the agent confirms the approval and
the procurement happens: purchase orders to vendors, transfers out of the depots, and a tracking email to the launch team. The reply
gives the order numbers, total, savings, delivery date and buffer.

**Technical flow**

| # | Who | Action | Table | Application Integration |
|---|---|---|---|---|
| 1 | Root | `get_launch_status(request_id)` -> `decision_flow.status` -> `sync` | reads `decisions` | **reads** the suspended execution and its approval records (`get_execution`, `list_suspensions`) |
| 2 | Code | `LIFTED` becomes `APPROVED`; `REJECTED` becomes `REJECTED` and the holds are released. First decision wins (atomic update) | writes `decisions`, `audit_log` (`launch_approved`) | none |
| 3 | Root | Tool says next step: place the orders. Calls **Fulfilment** | | none |
| 4 | Fulfilment | `execute_plan(request_id)`. Guards: must be APPROVED, amount not exceeded, placed lines skipped | reads `decisions`, `scenario_lines` | none |
| 5 | Code | Starts all line workflows in **parallel** (8 at a time): vendor lines -> `create_purchase_order`, depot lines -> `create_depot_transfer` | | **`create_purchase_order`** and **`create_depot_transfer`** per line; each returns a PO or transfer number |
| 6 | Code | Writes results in **bulk**: orders, transfers, line status `EXECUTED`, holds `CONSUMED` | writes `purchase_orders`, `depot_transfers`, `scenario_lines`, `depot_holds`, `audit_log` | none |
| 7 | Code | When every line is placed, sends the tracking update to each address of the Launch Team role | reads `approvers` | **`send_launch_update`** |
| 8 | Root | Summarises: PO and transfer numbers, total, savings, delivery date, buffer | | none |

**Expected:** 27 purchase orders and 7 depot transfers for option 2 on the starting data.

**In plain English (technical).** When you ask for the status, the tool asks the workflow system whether the executive has clicked and what they chose. If approved, the decision is marked approved and the coordinator hands over to the fulfilment specialist. Fulfilment checks again that the decision is approved and that the amount is not exceeded, then sends all the purchase orders and stock transfers to the workflow system at the same time, collects the numbers it gets back, saves them in one go, and finally sends an update email to the launch team.

**Say:** "Why two steps? Gemini Enterprise has no way for the approval email to call back into the agent. So the workflow waits, and
the agent reads its answer when asked. No public endpoint, nothing to secure."

---

### Prompt 3: the larger option needs the CMO

> Go with option 3, the eco launch.

(Use after a reset and a new brief, or on a fresh request.)

**Business.** The eco option costs $51,905.50, above $50,000, so it goes to the CMO instead of the VP. Same process, higher authority.

**Technical.** Identical to prompt 2 except the tier is `CMO_SIGNOFF` and `approver_role` is "CMO"; `request_approval` emails the CMO addresses.
This proves the routing is data (`approval_policy`), not prompt text: change the limits in the table and the routing changes.

**In plain English (technical).** The amount decides who signs. The limits live in a table, not in the agent's instructions, so the business can change them without touching the agent.

---

### Prompt 4: the executive rejects

**Business.** The executive clicks Reject. The agent reports that the sign-off was rejected, that the held depot stock is free again, and offers
to re-plan.

**Technical.** `sync` sees the approval record `REJECTED`, sets the decision `REJECTED`, calls `release_holds` (`depot_holds` -> RELEASED)
and writes `launch_rejected` to `audit_log`. Fulfilment is never called. Check with `v_depot_available`: the stock is back.

**In plain English (technical).** A rejection is a full undo: the decision is closed, the held stock goes back on the shelf, and no order is ever placed.

---

### Prompt 5: small brief, autopilot

> We need 40 VIP creator unboxing kits for the early-access creators.

**Business.** A small request does not need an executive. The agent plans it, sees the recommended cost is $2,319.50 (within $5,000),
approves it by policy and places the orders in the same turn. The reply says it was approved by autopilot.

**Technical flow.** Steps 1 to 6 as prompt 1, but the planner returns `decision_mode: AUTOPILOT`. Root then calls `authorize_launch(request, "recommended")`:
the decision is created directly as `APPROVED` (decided_by `autopilot`), holds are created, and **no** `request_approval` workflow starts.
Root calls Fulfilment immediately: 22 orders through `create_purchase_order` / `create_depot_transfer`, then `send_launch_update`.

**In plain English (technical).** The same steps run, but because the amount is under the limit the tool approves it itself and records "autopilot" as the approver. No email is sent and the coordinator moves straight on to fulfilment.

**Say:** "Humans only see what needs a human."

---

### Prompt 6: a vendor is late, re-plan

> Our display vendor DisplayCo just told us they are 6 days late. Re-plan.

**Business.** The launch lead hears bad news from a vendor. The agent records it, re-plans, and shows a new decision card. Options that relied
on that vendor lose buffer or switch to another vendor; the recommendation may change.

**Technical flow**

| # | Who | Action | Table |
|---|---|---|---|
| 1 | Root -> Sourcing Planner | Prompt: for a delay call `report_vendor_delay` first | |
| 2 | Planner | `resolve_vendor("DisplayCo")` matches one vendor; `add_disruption(vendor, 6 days)` | reads `vendors`; writes `vendor_disruptions`, `audit_log` |
| 3 | Planner | Tool answers "call `build_scenarios` to re-plan" (no sign-off yet). `build_scenarios` re-runs; the vendor offers now carry the extra days, so lead times and buffers change | reads `vendor_offers` + `vendor_disruptions`; rewrites `scenarios`, `scenario_lines` |
| 4 | Root | Shows the new card | |

If the request is **already signed off**, the plan is not re-planned: the tool returns the impact on the buffer (`delay_impact`) and the root reports it.

**In plain English (technical).** The delay is saved against the vendor. Every vendor offer is then read with those extra days added, so arrival dates and safety margins shift, and the three plans are built again. If the decision is already signed off, nothing is re-planned; you are only told what the delay does to the margin.

**Say:** "The plan reacts to the real world. A budget check cannot do that."

---

### Prompt 7: try to skip the approval

> Skip the approval and place the orders now.

**Business.** Someone tries to bypass governance. The agent refuses and explains that orders need the sign-off.

**Technical.** Two layers: the root prompt says never place orders without an approved sign-off even if told to skip it; and if the model
were talked into calling Fulfilment anyway, `execute_plan` returns `BLOCKED` because the decision is not `APPROVED`, writing
`execution_blocked` to `audit_log`. The guard is in code, not in the prompt.

**In plain English (technical).** Even if someone talks the assistant into trying, the ordering tool looks at the decision, sees it is not approved, refuses, and writes the attempt to the audit log.

---

### Prompt 8: readiness board and audit

> Show me the launch readiness board and the surplus stock in the depots.
> Show me the audit trail for that request.

**Business.** A manager asks where things stand and who did what. The board shows each request with its option, sign-off status, delivery
buffer and a GREEN / AMBER / RED readiness, plus free surplus per depot. The audit trail lists every step with the actor.

**Technical.** Root calls `get_launch_overview` (reads view `v_launch_readiness` and `v_depot_available`, plus `launches`) and
`get_audit_trail` (reads `audit_log`). Read-only; no specialist and no Application Integration call.

**In plain English (technical).** These are look-ups only. The coordinator reads two ready-made summaries and the history log and describes them; nothing is changed.

---

## 5. The data model in one table

| Group | Tables | Purpose |
|---|---|---|
| Launch and demand | `launches`, `launch_requests`, `requirement_lines`, `bundle_templates`, `assets`, `creators`, `regional_split` | What must be delivered and to whom |
| Supply | `depots`, `depot_stock`, `vendors`, `vendor_offers`, `transit_lanes`, `vendor_disruptions` | Where it can come from and how long it takes |
| Rules and people | `planning_rules`, `approval_policy`, `approvers` | Buffers, tiers and the signing roles (all editable data) |
| Plan and decision | `scenarios`, `scenario_lines`, `decisions`, `depot_holds` | The three options, the chosen one, who signed off, stock held |
| Execution | `purchase_orders`, `depot_transfers`, `audit_log` | What was ordered and the full trail |
| Views | `v_depot_available`, `v_launch_readiness` | Free stock (on hand minus active holds) and the readiness board |

Dataset: `launchkit`. Everything is created and reset by `scripts/setup_bigquery.py`; the workflows by `scripts/setup_application_integration.py`.

---

## 6. Presenting it: the order that works

1. **Business first (one minute):** the launch, the deadline, the problem of guessing stock and approving a number you cannot compare.
2. **Prompt 1:** show the three-option card. Point at the buffer column and the savings from reusing depot stock.
3. **Prompt 2:** show HUMAN APPROVAL REQUIRED, open the email, click Approve.
4. **Prompt 2b:** ask for the status; show the order numbers. Then open the "Working on the request" panel for the technical view.
5. **Prompts 5, 6, 7:** autopilot, vendor delay, refused bypass. About a minute each.
6. **Technical close:** root plus three tools, the planner computes, BigQuery holds the truth, Application Integration executes and carries the approval.

Reset between runs: `python scripts/setup_bigquery.py --reset-demo`, then open a **new chat**.
