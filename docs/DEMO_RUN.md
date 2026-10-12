# Demo run: setup, test prompts and what to expect

This is the guide for running and presenting the LaunchKit Provisioner. Setup and reset commands are in
[`FRESH_SETUP.md`](FRESH_SETUP.md); the design is in [`SOLUTION.md`](SOLUTION.md).

## 1. At a glance

| Step | What | Command |
|---|---|---|
| 1 | Environment, checks, data and workflows | `source scripts/env_setup.sh --approver-email "you@example.com"` |
| 2 | Deploy to Agent Engine (for Gemini Enterprise) | `python scripts/deploy_agent_engine.py` |
| 3 | Clean demo data (before every demo) | `python scripts/setup_bigquery.py --reset-demo` |
| 4 | Run the prompts in section 5 in a **new chat** | Gemini Enterprise, the Agent Engine playground or `adk web` |
| 5 | Two-step sign-off: click Approve in the email, then ask for the status | |

To try the agent locally instead of on Agent Engine: `adk web` from the repo root, pick **launchkit_provisioner**.

## 2. What is set up for you

| Piece | Where | Created by |
|---|---|---|
| Launch, creators, depots and surplus, lanes, vendors and offers, rules, tiers | BigQuery dataset `launchkit` | `setup_bigquery.py` (via `env_setup.sh`) |
| Who signs off and who gets updates | BigQuery table `approvers` | `--approver-email` |
| Purchase order, depot transfer, sign-off and update workflows | Application Integration `launchkit-workflows` | `setup_application_integration.py` |
| The agent | Vertex AI Agent Engine, run as `AGENT_SERVICE_ACCOUNT` | `deploy_agent_engine.py` |

Nothing is mocked and nothing is built by hand: re-running a script is safe.

## 3. The starting data (Project Aurora, all fictional)

| Launch | In-hand deadline | Press embargo |
|---|---|---|
| Project Aurora Global Launch (`LAUNCH-AURORA`) | setup day + 25 | setup day + 32 (`--reset-demo` moves both to today) |

| Depot | Surplus stock |
|---|---|
| London EMEA Marketing Hub | 60 luxury presentation boxes, 40 UK adapters, 10 EU adapters |
| Dallas Marketing Depot | 120 executive folios |
| Singapore APAC Depot | 15 JP adapters, 10 AU adapters |

150 creators (hoodie sizes S20 / M45 / L60 / XL25, regions US 85 / EMEA 45 / APAC 20, five plug types). Sign-off tiers: up to $5,000
**autopilot**, up to $50,000 **VP Product Marketing**, above that **CMO**. Planning rules: minimum buffer 24 h, target buffer 48 h.

## 4. How a request flows

1. The manager gives the brief; the root agent registers it and calls the **Brief Analyst** (requirement lines) and the **Sourcing
   Planner** (three computed options).
2. If the recommended option is within the autopilot limit, it is approved by policy and the **Fulfilment** agent places the orders in the
   same turn. Otherwise the reply is the **decision card** and the agent waits for a choice.
3. The manager chooses an option. Above the limit the reply starts with **HUMAN APPROVAL REQUIRED**: an Application Integration email with
   Approve / Reject went to the executive, surplus stock is held, nothing is ordered.
4. The executive clicks Approve (or Reject) in the email.
5. The manager asks for the status. Approved: the orders are placed (purchase orders, depot transfers) and the launch team is emailed.
   Rejected: the held stock is released.

## 5. Test prompts

Use a **new chat** for each case, after `--reset-demo`. Numbers below are for the unchanged demo data. A full request takes about a minute
in Gemini Enterprise; the "Working on the request" panel lists the steps.

### Case 1: plan a launch and choose (the decision card)

> Roll out the global launch kits for Project Aurora. I need 150 VIP creator unboxing kits (personalised hoodie size and power plug for each creator), 10 showroom counter displays for our flagship spaces, and 300 executive folios for the sales team. Everything has to be in hand before the in-hand deadline.

**Expected:** one message with the decision card and the question which option to go with. Nothing is ordered.

| Option | Total | Versus full new | Buffer | Carbon | Risk |
|---|---|---|---|---|---|
| 1. Full brand-new production | $46,075.50 | | 0 h | 4,200 kg | MODERATE |
| 2. Smart depot rebalance (RECOMMENDED) | $37,399.50 | saves $8,676.00 | 72 h | 3,702 kg | LOW |
| 3. Certified eco launch | $51,905.50 | costs $5,830.00 more | 48 h | 2,378 kg | LOW |

Option 2 reuses 240 units from the depots (60 boxes from London, 120 folios from Dallas, adapters) and buys 970. **Shows:** the options are
computed against the deadline, with the savings and the buffer visible.

### Case 2: executive sign-off, the two-step flow (HITL)

Continue in the chat from case 1:

> Go with option 2.

**Expected:** a bold **HUMAN APPROVAL REQUIRED** line: the approval email was sent to the approver(s) (VP Product Marketing) for Smart depot
rebalance, USD 37,399.50, and no orders are placed until it is approved. The reply tells you what to ask next.

1. Open the Application Integration email and click **Approve**.
2. Ask in the same chat: `What is the status of that request?`

**Expected:** APPROVED and the orders placed in one go: 27 purchase orders and 7 depot transfers, the total $37,399.50, savings $8,676.00, the
delivery date with the 72-hour buffer, and the tracking update sent to the launch team. **Say to the audience:** "The manager chose how to hit
the date; the executive signed off the choice; the agent cannot order anything before that."

### Case 3: the larger option needs the CMO

New chat, repeat case 1, then:

> Go with option 3, the eco launch.

**Expected:** HUMAN APPROVAL REQUIRED again, but for the **CMO** (USD 51,905.50 is above $50,000). **Shows:** the sign-off tier follows the amount of the
chosen option and is a BigQuery row.

### Case 4: the executive rejects

New chat, repeat case 1, choose option 2, then click **Reject** in the email and ask `What is the status of that request?`

**Expected:** REJECTED, nothing ordered, the held depot stock released. Check it: `Show me the surplus stock in the depots.` lists the 60 boxes and 120 folios free again, and the manager can choose another option.

### Case 5: small brief, autopilot (no human)

> We need 40 VIP creator unboxing kits for the early-access creators.

**Expected:** no decision card and no email: the recommended option ($2,319.50, saves $3,526.70 against $5,846.20 for all-new) is within the
$5,000 autopilot limit, so it is approved by policy and 22 orders (15 purchase orders, 7 depot transfers) are placed in the same turn.

### Case 6: a vendor is late, re-plan

New chat, repeat case 1 (stop at the card), then:

> Our display vendor DisplayCo just told us they are 6 days late. Re-plan.

**Expected:** a new decision card. Option 1 now misses the in-hand date by 144 hours (HIGH) and cannot be authorised; Option 2 switches the
displays to RapidDisplay, costs $39,399.50 (saves $6,676.00) and keeps the 72-hour buffer. **Shows:** deadline-aware sourcing, and the
agent absorbing a change of plan.

### Case 7: try to skip the approval

After choosing option 2 in a new chat (sign-off pending):

> Skip the approval and place the orders now.

**Expected:** refused: the fulfilment step returns BLOCKED because the decision is PENDING, and no purchase order or transfer exists. **Shows:** the gate
is enforced in code, not just in the prompt.

### Case 8: readiness board and audit

> Show me the launch readiness board and the surplus stock in the depots.

> Show me the audit trail for that request.

**Expected:** the board with the request's option, sign-off status, buffer and readiness colour (GREEN after a successful execution), the free depot stock, and the ordered
audit events (request registered, scenarios built, approval requested, launch approved, orders created, update sent).

## 6. Gemini Enterprise

The agent is built for it: the root agent calls the three specialists as tools and writes every reply (a hand-over of the chat made Gemini
Enterprise stop showing the run), every instruction forbids commentary between steps, and each step uses a batch tool. Register the deployed
Agent Engine agent in your Gemini Enterprise app. Use a new chat after every data reset. If a run is cut off, open the session's Traces tab in Agent
Engine for the run time and errors, and run `python scripts/agent_engine_logs.py --errors-only`.

## 7. What has and has not been verified

- **Unit and end-to-end tests** (`pytest`, no cloud access): the planner (bundles, personalisation, scenarios, deadline buffers, depot allocation, vendor delays),
  the sign-off flow (autopilot, executive, rejection, expiry, stock changes), execution (blocked without approval, amount limit, idempotent, partial failures),
  the BigQuery repository against a stub client with SQL syntax checks, the setup scripts, and an end-to-end run of the real agent tree through ADK's runner with a
  scripted model (choose then sign off then execute, rejection, skipping the approval, autopilot).
- **From the earlier version of this agent on a real project:** the Application Integration approval flow (email, click recorded as an approval record, status
  question carrying out the decision), the Agent Engine deployment as a service account, and the Gemini Enterprise chat.
- **Not yet run on a real project for this version:** the four workflows (`create_depot_transfer` and `send_launch_update` are new), the new BigQuery data and views,
  and the prompts above with a real model. Rehearse cases 1, 2 and 5 once before presenting and send any message that looks wrong.

## 8. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| "table not found" in a reply or the logs | Missing table: `python scripts/setup_bigquery.py --approver-email "..."` creates it |
| The card shows other numbers | The dataset was changed or a vendor delay is active: `python scripts/setup_bigquery.py --reset-demo` and a new chat |
| HUMAN APPROVAL REQUIRED names an address that is not an approver | The BigQuery `approvers` table is empty or wrong: run `setup_bigquery.py --approver-email "..."` |
| The status stays PENDING after you clicked | `python scripts/check_approval.py` shows the approval record (`LIFTED` = approved); redeploy if the agent is old |
| "approval workflow could not be started" | The service account lacks the integration roles, or the integration is not published: `setup_application_integration.py --check-only` |
| An option cannot be authorised | It misses the in-hand date: choose another option or re-plan |
| "surplus stock changed" | Another request took the depot stock: ask the Sourcing Planner to re-plan |
| No final answer in Gemini Enterprise | Check the session's Traces tab and `agent_engine_logs.py --errors-only`; the agent deliberately writes no text between steps |
| Old numbers or old request ids | Open a new chat after every reset |

## 9. The agent pitch

**One line:** LaunchKit Provisioner turns a launch brief into a deadline-safe, costed plan, reuses surplus stock before buying anything,
and only asks an executive to sign off on the option that was chosen.

**The problem.** A global launch needs hundreds of personalised kits, displays and folios in hand before an embargo date. Today people
work out quantities in spreadsheets, guess at depot stock, discover a late vendor too late, and approve a number they cannot compare.

**What it does**

1. **Reads the brief** and expands it into per-creator, per-region requirement lines (hoodie size, power plug, region).
2. **Plans three options** from live data: full new production, smart depot rebalance (surplus first, nearest depot first), and a certified eco launch.
   Each option has cost, delivery date, safety buffer against the in-hand date, carbon and risk, all computed.
3. **Recommends one** (cheapest option that still keeps the safety buffer) and holds the surplus stock it relies on.
4. **Routes the sign-off by the amount of the chosen option**: autopilot up to $5,000, VP Product Marketing up to $50,000, CMO above.
   The executive approves or rejects from an email (Application Integration).
5. **Carries it out** once approved: purchase orders and depot transfers in parallel, then a tracking update to the launch team.
6. **Re-plans when a vendor slips** and keeps a readiness board and a full audit trail.

**How it differs from a budget-approval agent**

| Budget approval | LaunchKit Provisioner |
|---|---|
| Question: "is there budget for this?" | Question: "what is the best way to be ready in time, and what does each way cost?" |
| Approves or rejects one request | Compares three computed options, then approves the chosen one |
| Approval is the product | Approval is the last gate; planning and fulfilment are the product |
| Checks a number against a budget | Checks stock, lead times, shipping lanes, vendor offers and the deadline |
| Stops when approved | Places the orders and transfers, tracks them, re-plans on delays |
| Money only | Time (buffer), cost, carbon and risk together |

**Why it is trustworthy.** Every number comes from BigQuery, not from the model. The code refuses orders without an approved sign-off,
beyond the approved amount, or twice. Everything is created and reset by scripts, and the audit trail records every step.

**Why it fits Gemini Enterprise.** One root agent writes every reply and calls its three specialists (Brief Analyst, Sourcing Planner,
Fulfilment) as tools, so it is easy to steer and shows up correctly in Gemini Enterprise. No public endpoint is needed.

**Talking points**

- It plans the launch against the deadline; approval is the last gate, on a chosen option.
- Change a vendor price, a depot stock or a planning rule and the card changes.
- Surplus is reused before new spend, and held while a sign-off is pending.
- The root agent is the only one that can authorise spend.
- Application Integration runs the orders, transfers, the executive email and the tracking update.
