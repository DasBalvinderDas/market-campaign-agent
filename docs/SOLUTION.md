# The Campaign Provisioner - Solution Guide

> Autonomous agent that transforms marketing logistics by orchestrating inventory, procurement and budget approval, with human-in-the-loop controls for high-value requests.

## 1. The problem

Running a campaign needs physical and paid materials (swag, banners, brochures, booth displays). Today that work is fragmented:

- Stock is checked manually in an inventory system.
- Vendor quotes are collected by email and compared by hand.
- Budget sign-off happens in a separate finance process, often after the order is already being discussed.
- Nobody has one audit trail that shows who approved what.

Results: launches slip, items get re-bought although stock exists, spend goes above budget, and high-value purchases are approved informally.

## 2. Why this agent was created

The Campaign Provisioner takes a plain-language request ("I need 500 T-shirts and 2 LED displays for CMP-SPRING-LAUNCH") and runs the whole logistics chain in a fixed, governed order. It automates the routine work and keeps people in control of the risky decision (large spend).

| Goal | How it is met |
|---|---|
| Remove manual chasing | Specialist sub-agents call the systems directly |
| Avoid duplicate buying | Inventory is always checked and reserved first |
| Control spend | Budget is validated before any order |
| Keep humans in charge of big money | Approvals above a threshold pause for a person |
| Be auditable | Every governed action is written to an audit trail |

## 3. Architecture

A central **root agent** governs three **sub-agents** (Google ADK multi-agent hierarchy).

```
                  campaign_provisioner  (root / orchestrator)
                  tools: register_campaign_request, get_audit_trail
        ┌─────────────────────┼──────────────────────┐
 inventory_agent       procurement_agent         budget_agent
 check_inventory       get_vendor_quotes         check_budget
 reserve_inventory     place_purchase_order      approve_budget  (HITL gate)
```

The editable PowerPoint version of this diagram is in `docs/Campaign_Provisioner_Management_Deck.pptx` (slide 3).

| Agent | Responsibility | Never does |
|---|---|---|
| Root `campaign_provisioner` | Understands the request, registers it, delegates in order, enforces rules, aggregates results | Specialist work itself |
| `inventory_agent` | Checks stock, reserves available units, reports shortfall | Buy or discuss budget |
| `procurement_agent` | Quotes vendors, recommends one, places POs once approved | Approve budget |
| `budget_agent` | Checks funds, approves spend; high-value spend pauses for a human | Place orders |

## 4. Code layout

```
campaign_provisioner/
  agent.py                  root_agent (ADK entry point) and its instruction
  config.py                 model name, HIGH_VALUE_THRESHOLD_USD (env-overridable)
  data.py                   mock inventory / vendors / budgets (swap for real APIs)
  sub_agents/
    inventory_agent.py
    procurement_agent.py
    budget_agent.py
  tools/
    inventory_tools.py      check_inventory, reserve_inventory
    procurement_tools.py    get_vendor_quotes, place_purchase_order (guarded)
    budget_tools.py         check_budget, approve_budget + HITL wrapper
    orchestration_tools.py  register_campaign_request, get_audit_trail
    audit.py                audit-trail helper
tests/test_tools.py         unit tests for tools and guardrails
docs/                       this guide + management deck
```

## 5. Code flow, step by step

Example: *"500 T-shirts and 2 LED displays for CMP-SPRING-LAUNCH."*

1. **Intake (root).** The root agent confirms campaign id and items, then calls `register_campaign_request` and gets `REQ-001`. The request and an audit event are stored in session state.
2. **Inventory.** The root transfers to `inventory_agent`. It calls `check_inventory` per SKU, then `reserve_inventory` for the free units. T-shirts: 300 in stock, so 300 reserved and 200 short. LED displays: 0 in stock, so 2 short. It transfers back with the shortfall list.
3. **Quotes.** The root transfers to `procurement_agent` (quote step). `get_vendor_quotes` returns offers sorted by total cost, with lead times. The agent recommends vendors and reports the total (for example about $4,540). No order is placed yet.
4. **Budget and approval.** The root transfers to `budget_agent`, which calls `check_budget` and then `approve_budget` with the total and a justification.
   - **At or below the threshold** (default $5,000): approved automatically by policy (`approved_by = auto-policy`).
   - **Above the threshold:** `approve_budget` is wrapped in ADK's `FunctionTool(require_confirmation=...)`. ADK pauses the run and asks a human to confirm or reject, showing the call arguments. Only on confirmation does the function run and record the approval (`approved_by = human`). If rejected, nothing is committed.
   - If the amount exceeds the remaining budget, the tool returns `rejected` and the flow stops.
5. **Ordering.** Back at the root, the budget is now approved, so it transfers to `procurement_agent` (order step). `place_purchase_order` checks session state: an approval for this `request_id` must exist and cover the cumulative PO total. Otherwise it returns `blocked`. This check is in code, so it holds even if the model misbehaves.
6. **Result aggregation.** The root summarises reserved stock, POs (vendor, cost, lead time), remaining budget and who approved. `get_audit_trail` returns every governed action.

### Governance in three layers

| Layer | Mechanism |
|---|---|
| Prompt | The root instruction fixes the order of steps; sub-agents must hand back to the root |
| Platform | ADK tool confirmation pauses high-value approvals for a human |
| Code | `place_purchase_order` hard-blocks without a covering approval; `approve_budget` rejects overspend |

## 6. Human-in-the-loop details

`requires_human(amount)` in `tools/budget_tools.py` is the predicate. When it returns true, ADK emits a confirmation request event instead of running the tool. In `adk web` the approver sees a confirm/reject prompt. In a custom app, your UI answers the `adk_request_confirmation` function call with `confirmed: true/false`. Change the limit with `HIGH_VALUE_THRESHOLD_USD`.

## 7. Running it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # add GOOGLE_API_KEY or Vertex AI settings
adk web                         # run from the repo root, pick campaign_provisioner
pytest                          # offline unit tests (no LLM needed)
```

Try: *"Campaign CMP-LOCAL-POPUP needs 100 tote bags"* (auto-approved), then *"CMP-SPRING-LAUNCH needs 500 T-shirts and 2 LED displays"* (pauses for human approval).

## 8. Production notes

- `data.py` is mock data held in memory. Replace the tool bodies with ERP, vendor and finance API calls (for example through MCP servers) and keep the signatures.
- Session state is in-memory by default; use a persistent session service (Vertex AI Agent Engine / database) so approvals survive restarts and pending confirmations can be resumed.
- The default model is `gemini-2.5-flash`; set `CAMPAIGN_MODEL` to the Gemini version your organisation standardises on.
- Add Cloud Logging for the audit trail, IAM for who may approve, and Model Armor for prompt safety, as shown in the architecture slide.
- The tests cover tools and guardrails only; the LLM routing and the live confirmation flow should be checked with `adk web` against a real model.
