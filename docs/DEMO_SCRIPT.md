# Demo script: the full cycle in two stories

Copy the prompts as they are. Each story shows the whole cycle: **ask → offer → shopping list → stock and vendors → approval → orders**.
Numbers are from the demo data (see "Before you start"); the dates move with today's date, the dollar amounts do not.

| Story | Who | What it proves |
|---|---|---|
| **1. One item** (three runs) | A buyer who needs one thing | Within the limit: ordered at once. Above the limit: approval first, then ordered (or declined) |
| **2. A campaign** | A marketer creating a campaign | Picks from the offer, vendors compared, stock reused, approval by amount, then all orders together |

---

## Before you start

```bash
cd ~/market-campaign-agent && source scripts/env_setup.sh
python scripts/setup_bigquery.py --refresh-reference      # latest items, vendors, prices, stock; also clears old demo plans
date -d "+25 days" "+%-d %B %Y"                           # prints the date to use below; call it <DATE>
```

Use **exactly 25 days from today** for `<DATE>`. The amounts below depend on it (a later date lets a cheaper, slower vendor win and changes some totals).
Open a **new chat** for every run. The approval email goes to the approver addresses you set up (`FRESH_SETUP.md`, section E).

The approval levels used in both stories: **up to $5,000 automatic · $5,000 to $50,000 VP Product Marketing · above $50,000 CMO.**

---

## Story 1: one item

> *"I only need one thing. Can I just buy it?"* Yes. Same steps, shorter. The amount decides who has to say OK.

### Run 1A: inside the limit, ordered at once (no approval)

**Fast version** (one message):

> Selected items, no campaign, in hand by `<DATE>`: 30 name badges with lanyards for the US.

**Step by step** (one answer per question; it skips what you already said):

| The assistant asks | You say |
|---|---|
| 🧭 Whole campaign or selected items? | `Selected items` |
| Is this for a campaign? | `No campaign` |
| 📅 By what date? | `<DATE>` |
| 🛍️ What would you like from our offer? (it shows packs, items, stock, best prices, ready-by dates) | `30 name badges with lanyards for the US` |

**What you see**
1. 🧾 Shopping list: one row, 30 name badges. 💡 One tip: *Plan the whole campaign* (the nudge).
2. Say `Looks good`.
3. 📌 **In short** → ♻️ stock (none for this item) → 🏭 vendors (Inkwell Print vs EngraveWorks, ready-by dates) → 🎯 three choices, all **$67.50**.
4. **No approval email.** $67.50 is under $5,000, so it is approved automatically and **1 purchase order** is placed in the same turn. The summary says *no approval was needed*.

**Say:** *"Small things do not wait for anybody. The rule is a table, not a person."*

### Run 1B: above the limit, approved, then ordered

**Fast version:**

> Selected items, no campaign, in hand by `<DATE>`: 6 venue display stands for the US.

1. Shopping list and the tip, then `Looks good`.
2. 🏭 Vendors compared: DisplayCo (cheapest), RapidDisplay (faster, dearer), StagePro Displays. 🎯 Choices: **$8,490.00** (new or our stock first, the same because we own none) and $9,450.00 (eco).
3. `Choose option 1`
4. **HUMAN APPROVAL REQUIRED**: *$8,490.00 is $5,000 to $50,000, so the **VP Product Marketing** has to say OK*, with the approval ladder and the 👈 *this order* marker. Nothing is bought yet.
5. Open the email and click **Approve**.
6. `What is the status of that request?` → **✅ Done! All your orders are placed**: **1 purchase order**, $8,490.00, DisplayCo.

**Say:** *"Same steps, but above $5,000 a person must approve first. The agent cannot order before that. Try asking it to skip the approval: it refuses."*
(Optional: after step 4, type `Skip the approval and place the order now.` → refused.)

### Run 1C: above the limit, declined

Repeat 1B up to the approval email, but click **Reject**. Then:

> What is the status of that request?

**You see:** ❌ **Rejected**, *nothing was bought*. No purchase order exists. The assistant offers to re-plan (a smaller quantity, say, which might fall under the limit).

**Say:** *"An approver can say no, and then nothing is ordered."*

---

## Story 2: a campaign

> *"I am creating a campaign. Help me set it up."* The assistant asks four easy questions, shows what we can offer, spots what is missing, compares vendors, gets the OK and places all orders together.

### Step 1: say hello

> Hi

**You see:** the hello card (what it can do, **Two ways to start**) and the first question.

### Step 2: close on four things

| The assistant asks | You say |
|---|---|
| 🧭 Whole campaign or selected items? | `A whole campaign` |
| 🎪 What is your campaign called? | `Summer Sale Campaign` |
| 📅 By what date must everything be in hand? | `<DATE>` |
| 🛍️ **What would you like from our offer?** (it shows **🛍️ What we can offer you**) | *(the pick, below)* |

The offer table shows **🎁 ready-made packs** (what is inside, which parts we already have in stock, price per pack, ready-by date, 🟢 fits) and **🧩 single items** (♻️ our stock and where, 💰 best price and vendor, 📅 ready by, ⚡ a faster option, 🌱 eco price).
The checklist (✅/⬜) updates on every turn.

### Step 3: pick from the offer (one message)

> I will take 150 VIP guest welcome kits, 300 sales folders and 10 venue display stands. Add 150 canvas tote bags for EMEA, 150 steel water bottles for the US and 30 roll-up banners for the US.

**You see:**
1. 🧾 **Shopping list (Bill of Materials)**: 1,540 items. Kits and folders are broken down into their parts; the tote bags, bottles and banners are single items.
2. 💡 **Anything you may be missing?** *A few spares (5% extra: 8 kits, 15 folders, 1 stand).* (Nothing else: you already have all three kinds of pack.)
3. Say `Looks good`. *(To show the loop instead: `Add the spares`, then `Looks good`: the list and the plan update.)*

### Step 4: the plan

**You see, in this order:**
1. 📌 **In short**: *Best choice: Option 2, Use our stock first, buy the rest. **$37,594.50** (save **$12,726.00**). Arrives with 3 days to spare. OK from: **VP Product Marketing***. Our own stock covers **570 of 1,540 items** (37%) with a picture bar.
2. ♻️ **What we already have in stock**: for example 120 folders in Dallas, 60 gift boxes in London, 150 bottles in Dallas, 150 totes in London, banners in Dallas and London, adapters.
3. 🏭 **What vendors can do, and by when**: one row per vendor and item with price, ready-by date, who was chosen, and why RapidDisplay is used even though DisplayCo is cheaper.
4. 🎯 **Your 3 choices**:

| | Option 1: Buy everything new | Option 2: Use our stock first, buy the rest ⭐ | Option 3: Go green |
|---|---|---|---|
| 💰 Total | $50,320.50 | **$37,594.50** | $56,698.00 |
| 💸 vs Option 1 | | **Save $12,726.00** | Pay $6,377.50 more |
| ⏳ Spare time | 🟡 none (tight!) | 🟢 3 days | 🟢 2 days |
| ✍️ Who has to say OK | **CMO** | **VP Product Marketing** | **CMO** |

**Say:** *"Three ways to do the same campaign. The cheapest is also the safest, and it needs the VP, not the CMO."*

### Step 5: choose and get the OK

> Choose option 2

**You see:** **HUMAN APPROVAL REQUIRED**, *$37,594.50 is $5,000 to $50,000, so the VP Product Marketing has to say OK*, the ladder with 👈 *this order*, a four-step tracker and *the stock is held for you*.
Open the email → click **Approve**.

### Step 6: procurement

> What is the status of that request?

**You see:** **✅ Done! All your orders are placed**: **$37,594.50**, $12,726.00 saved, **27 purchase orders + 11 warehouse moves** (38 orders in one go), 570 items from our own stock, a vendor table with a *why* for every vendor, **Why so many orders?** (one per item per region), and a launch-team email.

**Say:** *"One conversation: a whole campaign, many vendors, our own stock first, the right approver, and every order placed together, with the reason for each."*

### Optional: show the top approval level (CMO)

New chat, the same four answers and pick, `Looks good`, then:

> Choose option 3

**You see:** **HUMAN APPROVAL REQUIRED** for the **CMO** (**$56,698.00** is above $50,000). Approve and ask for the status: **34 purchase orders**, no warehouse moves (the eco plan buys everything new).

---

## The full cycle at a glance

| # | Step | Single item | Campaign |
|---|---|---|---|
| 1 | Ask | Selected items, no campaign, date | Whole campaign, name, date |
| 2 | Offer | Pick one item from the table | Pick packs and items from the table |
| 3 | List | One-row shopping list | Bill of Materials (parts of each pack) |
| 4 | Advice | *Plan the whole campaign* | Spares and anything missing |
| 5 | Stock and vendors | Stock, vendors, ready-by dates | Stock, vendors, ready-by dates |
| 6 | Choices | Three choices, one amount | Three choices, three amounts |
| 7 | Approval | Automatic up to $5,000, VP up to $50,000, CMO above | Same ladder, by the chosen option |
| 8 | Orders | After approval; declined if rejected | All orders at once after approval |

## If something looks different

| You see | Why | Fix |
|---|---|---|
| Different dollar amounts | `<DATE>` is not exactly 25 days from today, or the old catalog is loaded | Use the printed date; run `--refresh-reference` |
| No stock rows for the extras | The old catalog is loaded | `python scripts/setup_bigquery.py --refresh-reference` |
| The assistant still asks old questions | The agent was not redeployed | `python scripts/deploy_agent_engine.py` |
| Status still says waiting after you clicked Approve | The click did not register | Open the email again; `python scripts/check_approval.py` |
| It uses the last chat's request | Old chat | Open a **new chat** for every run |

More prompts and the 8 test cases: [`DEMO_RUN.md`](DEMO_RUN.md). How each step works inside: [`PROMPT_EXPLAINER.md`](PROMPT_EXPLAINER.md).
