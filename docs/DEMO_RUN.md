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
| Launch, guests, depots and surplus, lanes, vendors and offers, rules, tiers | BigQuery dataset `launchkit` | `setup_bigquery.py` (via `env_setup.sh`) |
| Who signs off and who gets updates | BigQuery table `approvers` | `--approver-email` |
| Purchase order, depot transfer, sign-off and update workflows | Application Integration `launchkit-workflows` | `setup_application_integration.py` |
| The agent | Vertex AI Agent Engine, run as `AGENT_SERVICE_ACCOUNT` | `deploy_agent_engine.py` |

Nothing is mocked and nothing is built by hand: re-running a script is safe.

## 3. The starting data (Spring Launch Event, all fictional)

| Launch | In-hand deadline | Press embargo |
|---|---|---|
| Spring Product Launch Event (`LAUNCH-SPRING`) | setup day + 25 | setup day + 32 (`--reset-demo` moves both to today) |

| Depot | Surplus stock |
|---|---|
| London EMEA Marketing Hub | 60 luxury presentation boxes, 40 UK adapters, 10 EU adapters |
| Dallas Marketing Depot | 120 sales folders |
| Singapore APAC Depot | 15 JP adapters, 10 AU adapters |

150 guests (hoodie sizes S20 / M45 / L60 / XL25, regions US 85 / EMEA 45 / APAC 20, five plug types). Sign-off tiers: up to $5,000
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
in Gemini Enterprise. Every answer is written in simple words, with tables and icons. The assistant asks a few easy questions first.

**The idea to say first:** underneath it is still a purchase order, procurement and approval system. But instead of asking for one item at a
time, you give it a **whole campaign**, and it deals with **many vendors at once**: shopping list, vendor comparison, three choices, the right
approver, then all the orders together.

### Case 0: say hello, then close on four things

> Hi

**Expected:** a short card: **I can** (shopping list, spot what you may be missing, check our stock, compare vendors, 3 choices, the right OK, place all orders) and
**🧭 Two ways to start**: 🅰️ plan a **whole campaign** ⭐ (best: more stock to reuse, more vendors, a stronger case for better rates) or 🅱️ buy **selected items** (for a campaign or a quick
purchase). It ends with the first question: **Do you want to plan a whole campaign, or buy selected items?**

Every question turn shows the same small checklist (✅ closed, ⬜ open) and **one** next question:

| It asks | You say | Checklist after |
|---|---|---|
| 🧭 Whole campaign or selected items? | `A whole campaign` | ✅ ⬜ ⬜ ⬜ |
| 🎪 What is your campaign called? (you are creating it) | `Summer Sale Campaign` | ✅ ✅ ⬜ ⬜ |
| 📅 By what date must everything be in hand? (full date) | `20 December 2026` | ✅ ✅ ✅ ⬜ |
| 🛒 What would you like from our offer? (the assistant shows **🛍️ What we can offer you**, see below) | `150 VIP guest welcome kits and 300 sales folders` | ✅ ✅ ✅ ✅ |

**You pick from what we have; you do not type a list from nothing.** After the date, the assistant shows **🛍️ What we can offer you**:

| Part | What it shows |
|---|---|
| 🎁 Ready-made packs | guest welcome kit, sales folder pack, venue display stand: what is inside, which parts we already have in stock, the price per pack, the *ready by* date and 🟢 fits / 🟡 tight / 🔴 too late against your date |
| 🧩 Single items | per item: ♻️ our stock and where (for example 120 Dallas), 💰 best price and 🏭 vendor, 📅 ready by, 🚦 fits your date, ⚡ a faster option if there is one (for example RapidDisplay $1,650, ready sooner), 🌱 the eco price |

Then it says *Pick what you want. Say how many.* Mix packs and items; you can add or remove later (`add 10 venue display stands`, `remove the brochures`). Selected items starts with the item table; a whole campaign starts with the packs.

A new campaign name creates a **new campaign** with the date you give. (The data also has the *Spring Product Launch Event*; use that name and it offers the date on file: say *use that date*.)
You can skip ahead: `Plan my Summer Sale Campaign, in hand by 20 December 2026: 150 VIP guest welcome kits and 300 sales folders.` answers everything at once.

**Selected items** (the other way in): answer `Selected items`. The assistant asks *Is this for a campaign? Tell me its name, or say no campaign*, says once that planning the
whole campaign is better (and offers to switch with *plan the whole campaign*), then asks which items, how many and which region. Nothing is refused.

### Case 0b: the assistant spots what you may be missing (business advice)

After the third answer, the assistant shows **🧾 Step 1: your shopping list** and then **💡 Step 1b: Anything you may be missing?** and **waits**:

| Advice | Example | Why |
|---|---|---|
| 🛟 Spares | 5% extra: 8 kits, 15 folders | late additions, damage, loss (rule `SPARE_PERCENT` in `planning_rules`) |
| 🖼️ 📁 🎁 A kind of bundle you left out | venue display stands (with only guest kits and folders) | guests need somewhere to see the product |
| 🧩 The rest of a bundle | you asked for 5 gift boxes: the welcome kit also has a hoodie, power adapter and name card | a whole bundle means more stock to reuse and more vendors to compare |
| 🔴 🟡 A date that is too close | the fastest vendor needs 14 days, you have 12 | so you can move the date before it is too late |

Reply `Add 10 venue display stands` (the shopping list and advice are shown again) or `Looks good` to go on. Try it with the two-bundle answer above, then add the stands.

### Case 1: the plan (in short, stock, vendors, three choices)

Reply `Looks good`. **Expected:** one message, in this order, and nothing is ordered:

1. **📌 In short**: the best choice in four lines (option, price and saving, arrival and spare time, who has to say OK) and a picture of how much our own stock covers (🟩🟩⬜⬜⬜…).
2. **♻️ Step 2: What we already have in stock**: free units per warehouse and how many the best choice uses.
3. **🏭 Step 3: What vendors can do, and by when**: 7 vendors, 24 price offers, one row per vendor and item with price and *ready by* date, who was chosen, late vendors marked,
   and why RapidDisplay was used even though DisplayCo is cheaper.
4. **🎯 Step 4: Your 3 choices**, as one table (with the full demo brief of 150 kits, 10 stands, 300 folders):

| | Option 1: Buy everything new | Option 2: Use our stock first, buy the rest ⭐ | Option 3: Go green with eco-friendly materials |
|---|---|---|---|
| 💰 Total price | $46,075.50 | $37,399.50 | $51,905.50 |
| 💸 Compared with Option 1 | | Save $8,676.00 | Pay $5,830.00 more |
| 📅 Everything arrives | 6 Nov (deadline day) | 3 Nov | 4 Nov |
| ⏳ Spare time | 🟡 none (tight!) | 🟢 3 days | 🟢 2 days |
| 🌍 Pollution (CO₂) | 4,200 kg | 3,702 kg | 2,378 kg |
| ✍️ Who has to say OK | VP Product Marketing | VP Product Marketing | CMO |

Then: **Does this plan feel good?** *Say "Choose option 2", or tell me what to change.* **Shows:** a whole campaign worked out across many vendors, with the
choices computed against the deadline. If the shopping list had nothing to advise, the plan comes straight after the third answer.

**Change the plan before you commit** (same chat): `Make it 200 guest welcome kits.` or `Add 50 product brochures for the US.` The assistant rebuilds the list and the plan.
Nothing is ordered until you choose.

### Case 1b: selected items (a simple purchase order)

> Selected items. (then answer: *no campaign*, a full date, and `5 venue display stands for the US`)

**Expected:** the same steps, shorter: shopping list with one row, advice (*📣 Plan the whole campaign*, plus the rest of the bundle if the item belongs to one), stock, vendors, three choices, and a tip:
*buying selected items works fine, but if you plan the whole campaign with me I can reuse more of our own stock, compare more vendors, and we have a stronger case for better rates.*
Say `Looks good` to carry on with just the items, then choose; the approval level follows the amount.

### Case 2: the executive says OK, the two-step flow (human in the loop)

Continue in the chat from case 1:

> Choose option 2.

**Expected:** a bold **HUMAN APPROVAL REQUIRED** line (the email went to the VP Product Marketing), then **Step 4: Getting the OK**: the
approval ladder with *this order* marked, a four-step tracker (email sent, approver clicks, you ask for the status, orders placed), and
"the stock is held for you, nothing has been bought yet".

1. Open the Application Integration email and click **Approve**.
2. Ask in the same chat: `What is the status of that request?`

**Expected:** **✅ Done! All your orders are placed**: one row of numbers (total $37,399.50, $8,676.00 saved, arrives 3 Nov with 3 days to spare, 27 purchase orders + 7 warehouse moves,
3,702 kg pollution); **What we did, in 4 lines** (one whole campaign with 1,210 items; 7 vendors; 240 items from our own stock with a picture bar; the amount and who approved);
**Who we bought from, and why** (one row per vendor); **From our own warehouses**; and one line on **why so many orders** (one per item per region, all placed together).

### Case 3: who has to approve what? (multi-level approval)

> Who has to approve what?

**Expected:** the approval ladder table: **up to $5,000 automatic; $5,000 to $50,000 VP Product Marketing; over $50,000 CMO.** It comes from the
`approval_policy` table, so changing the limits changes the answer.

Then show each level in its own chat (after a reset):

| Level | What to say | What happens |
|---|---|---|
| Automatic | `We need 40 VIP guest welcome kits for the early-access guests.` | $2,319.50 is under $5,000: no email, orders placed in the same turn |
| Manager (VP) | Case 1, then `Choose option 2.` | $37,399.50: email to the VP Product Marketing |
| Top level (CMO) | Case 1, then `Choose option 3, the eco one.` | $51,905.50: email to the CMO |

### Case 4: the executive rejects

New chat, repeat case 1, choose option 2, then click **Reject** in the email and ask `What is the status of that request?`

**Expected:** ❌ Rejected, nothing bought, the held stock free again. `Show me the event status board.` lists the free warehouse stock again
(60 gift boxes, 120 folders), and you can choose another option.

### Case 5: compare the vendors again

> Compare the vendors for that request.

**Expected:** the vendor comparison table again (price, days to make, chosen or not, late vendors marked ⚠️) and the stock we already own.

### Case 6: a vendor is late, re-plan

New chat, repeat case 1 (stop at the choices), then:

> Our display vendor DisplayCo just told us they are 6 days late. Re-plan.

**Expected:** a new vendor table (DisplayCo marked ⚠️ running 6 days late) and new choices. Option 1 now misses the deadline by 144 hours
(🔴) and cannot be chosen; Option 2 switches the display stands to RapidDisplay, costs $39,399.50 (saves $6,676.00) and keeps 3 days to spare.

### Case 7: try to skip the approval

After choosing option 2 in a new chat (sign-off pending):

> Skip the approval and place the orders now.

**Expected:** refused: the ordering step returns BLOCKED because the decision is still waiting, and no purchase order or transfer exists.
**Shows:** the gate is enforced in code, not just in the prompt.

### Case 8: status board and what happened

> Show me the event status board.

> Show me what happened for that request.

**Expected:** a board (request, choice, status, arrival date, 🟢/🟡/🔴 readiness, orders placed), the free warehouse stock, and a table of the
steps with who did them (request created, shopping list made, 3 choices worked out, approval email sent, approved by a person, 27 purchase
orders, 7 warehouse moves, team told by email).

### The emails

- **Approval email** (Application Integration): carries a short, plain summary of the choice (price, arrival date, days to spare, how many items
  from our warehouses and from vendors, why) with **Approve** and **Reject**. Those two links are produced by Application Integration itself.
- **Launch team update**: a formatted HTML email (header, summary table: choice, orders placed, moves, total, saving, arrival date, pollution).

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

**The problem.** A global launch needs hundreds of personalised kits, displays and folders in hand before an embargo date. Today people
work out quantities in spreadsheets, guess at depot stock, discover a late vendor too late, and approve a number they cannot compare.

**What it does**

1. **Reads the brief** and expands it into per-guest, per-region requirement lines (hoodie size, power plug, region).
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
