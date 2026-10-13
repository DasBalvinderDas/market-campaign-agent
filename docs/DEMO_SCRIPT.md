# Demo script: the full cycle in two stories

Just talk to it. Nobody has to write a detailed request: the assistant reads what you say, asks only for what is missing, **shows what we have**, and you
pick. Each story shows the whole cycle: **talk → where we deliver → our offer → shopping list → stock, vendors, best date → approval → orders**.
Dollar amounts are from the demo data; the dates move with today's date.

| Story | Who | What it proves |
|---|---|---|
| **1. One item** (three runs) | A buyer who needs one thing | Within the limit: ordered at once. Above the limit: approval first, then ordered (or declined). Moving the date can save money |
| **2. A campaign** | A marketer planning a campaign for 300 people | Where we deliver, our offer with a suggested plan, vendors compared, the best date, approval by amount, then all orders together |

---

## Before you start

```bash
cd ~/market-campaign-agent && source scripts/env_setup.sh
python scripts/setup_bigquery.py --refresh-reference      # latest items, vendors, prices, venues, date pricing; clears old demo plans
date -d "+25 days" "+%-d %B %Y"                           # prints the date to use below; call it <DATE>
```

Use **exactly 25 days from today** for `<DATE>`. The amounts below depend on it: vendors charge **less when you order earlier and more for a rush**, and the 21 to 34 day band is
the standard price. Open a **new chat** for every run. The approval email goes to the approver addresses you set up (`FRESH_SETUP.md`, section E). It is an **HTML email**: summary table, **✓ Approve** and **✗ Reject** buttons, the shopping list and the vendor table. Both buttons open the approval page, where you confirm with one click.

**Standing campaigns.** The system always starts with three campaigns: **London Campaign** (`LAUNCH-LONDON`), **US Campaign** (`LAUNCH-USA`) and **Singapore Campaign** (`LAUNCH-SINGAPORE`), each in hand **30 days after setup**. To add to one, say its name or reference (`add to the London campaign`, `LAUNCH-USA`); partial names work. `Which campaigns do we have?` lists them. A fresh campaign works as described below.

After the orders are placed, the assistant also attaches an **order pack PDF** (shopping list, vendors, warehouse moves) to the chat. The emails carry the same shopping list and vendor tables in the message itself.

Approval levels used in both stories: **up to $5,000 automatic · $5,000 to $50,000 VP Product Marketing · above $50,000 CMO.**

---

## Story 2 (the main one): a campaign for 300 people

> *"I am planning a campaign. Help me set it up."*

### 1. Say it the way you would say it

> Hi, I am looking for a campaign for 300 people on `<DATE>`.

**The assistant answers** (it already has the people and the date, so it does not ask again):

- a small ✅/⬜ table of what it knows: *how many people ✅, date ✅*, and what is still open;
- **📍 Where can we deliver?** A table of **USA, Canada, London, Singapore**: the vendors based there, our warehouse and what is in it, and how each place is served
  (Canada is served from the US vendors and the Dallas warehouse), plus *what we have in place* (the 12 kinds of items);
- the one next question: **Where is your campaign?**

*(Try `Hi` first if you like: you get the hello card. Its first question says we already have four campaigns (London, US, Singapore and Spring) and asks: add to one of them, or create a new one?)*

### 2. Say where, then pick a name

> USA

It confirms the place and asks the last open question, with **💡 name ideas** built from the season, the place and the size of your campaign:

| # | 💡 Name ideas |
|---|---|
| 1 | Autumn Summit 2026 |
| 2 | USA Autumn Showcase |
| 3 | November USA Launch |
| 4 | The 300-Guest Autumn Celebration |

Say a number, or type your own:

> Summer Sale Campaign

**🎉 Your campaign is created!** (as soon as the name is picked): name, reference (`EVT-SUMMER-SALE-CAMPAIGN`), date, people, place. Then, in the same message, it goes on to our offer.

### 3. See what we have and pick

**🛍️ What we can offer you**, for your date:

| Part | What it shows |
|---|---|
| 🎁 Ready-made packs | guest welcome kit, sales folder pack, venue display stand: what is inside, which parts we already have in stock, price per pack, *ready by*, 🟢 fits your date, **💡 for 300 people** (30 kits, 30 folders, 3 stands) |
| 🧩 Single items | per item: ♻️ our stock and where (for example *150 Dallas, 80 Singapore* water bottles), 💰 best price and vendor **for your date**, 📅 ready by, ⚡ a faster option (for example RapidDisplay), 🌱 eco price, **💡 for 300 people** (300 badges, 300 totes, 300 bottles) |

Then: *Say **use the suggested plan**, or say how many.*

> Use the suggested plan

### 4. Shopping list, and what you may be missing

**🧾 Your shopping list (Bill of Materials)**: six short rows (30 welcome kits with what is inside, 30 folder packs, 3 stands, 300 badges, 300 bottles, 300 totes), **1,083 items** in total.
**💡 Anything you may be missing?** *A few spares (5% extra: 2 kits, 2 folders, 1 stand).* (Say `Add the spares` to see the list update, or:)

> Looks good

### 5. The plan: stock, vendors, choices, and the best date

**You see, in this order:**

1. 📌 **In short**: *Best choice: Option 2, Use our stock first, buy the rest. **$8,863.50** (save **$6,666.00**). 6 days to spare. OK from: **VP Product Marketing**.*
   Our own stock covers **490 of 1,083 items** (45%) with a picture bar.
2. ♻️ **What we already have in stock**: one short row per item: bottles (Dallas, Singapore), totes (London), folders (Dallas), gift boxes (London), and how many we use.
3. 🏭 **Vendors we compared**: **one row per item**: the chosen vendor, the price **for your date**, *ready by*, how many vendors were compared and the next best one. Items from our own stock say so.
4. 🎯 **Your 3 choices**: **$15,529.50** (buy everything new) · **$8,863.50** (use our stock first) · **$17,854.50** (go green). All three need the VP Product Marketing.
5. 📅 **Could another date save you money?** The same list on other dates:

| 📅 In hand by | 🏷️ Price band | 💸 Compared with your date |
|---|---|---|
| 14 days earlier | Rush: 12% extra | Pay about $1,900 more, and 🔴 too late for some items |
| 7 days earlier | Rush: 6% extra | Pay $1,315.50 more |
| **`<DATE>`** | Standard price | 👈 your date |
| 7 days later | Standard price | **Save $294.00** |
| 14 days later | Early bird: 5% off | **Save $482.20** |
| 28 days later | Early bird: 8% off | **Save $595.80** |

**Say:** *"It does not just buy. It tells you that ordering a week later saves money, and a week earlier costs more. The vendors price by date."*
*(Optional: `Move it to` and a date 4 weeks later: it plans again with the early-bird prices.)*

### 6. Choose, get the OK

> Choose option 2

**HUMAN APPROVAL REQUIRED**: *$8,863.50 is $5,000 to $50,000, so the **VP Product Marketing** has to say OK*, with the approval ladder and the 👈 *this order* marker, a four-step tracker and
*the stock is held for you*. **Open the email and click Approve.**

### 7. Procurement

> What is the status of that request?

**✅ Done! All your orders are placed**: **$8,863.50**, $6,666.00 saved, **8 purchase orders (one per vendor) + 3 warehouse moves (one per warehouse)**, 11 orders in one go, 490 items from our own stock, one short vendor table
with a *why* for each of the 8 vendors, **one line** for the warehouse moves, and a launch-team email.

**Say:** *"One conversation. Our own stock first, eight vendors compared, the best date shown, the right approver, and every order placed together, with the reason for each."*

### Other places and sizes (same story, different numbers)

| Say | You get |
|---|---|
| Place **London** | Option 2 **$8,696.00**, 3 days to spare; 6 POs + 3 warehouse moves |
| Place **Singapore** | Option 2 **$9,915.50**, 5 days to spare; 8 POs + 3 warehouse moves |
| Place **Canada** | The same as the USA (served from the US) |
| **1,000 people**, USA | Option 2 $40,637 (VP), but Option 1 $51,765 needs the **CMO** |
| **2,000 people**, USA | Option 2 **$91,830**: needs the **CMO** (above $50,000); 8 POs + 3 warehouse moves |

---

## Story 1: one item

> *"I only need one thing."* Same conversation, shorter. The amount decides who has to say OK.

### Run 1A: inside the limit, ordered at once

> Hi, I need 30 name badges with lanyards for the USA by `<DATE>`.

It has the date, the place and the pick, so it goes straight on: **🧾 shopping list** (one row) and **💡 *Plan the whole campaign*** (the nudge: more stock to reuse, more vendors, better rates). Say `Looks good`.
Then: 📌 In short, stock, vendors (Inkwell Print vs EngraveWorks), three choices all **$67.50**, and the dates table (a week later saves a little, a rush costs more).

**No approval email.** $67.50 is under $5,000, so it is approved automatically and **1 purchase order** is placed in the same turn.
**Say:** *"Small things do not wait for anybody. The rule is a table, not a person."*

### Run 1B: above the limit, approved, then ordered

> Hi, I need 6 venue display stands in the USA by `<DATE>`.

1. Shopping list and the tip → `Looks good`.
2. 🏭 DisplayCo (cheapest), RapidDisplay (faster, dearer), StagePro Displays. 🎯 **$8,490.00** (new, or our stock first: we own none) and $9,450.00 (eco).
3. 📅 **A week later saves $588.00** (DisplayCo's early-bird price); a week earlier costs **$2,094.00** more. *(The "delay or do it early to save funds" moment.)*
4. `Choose option 1` → **HUMAN APPROVAL REQUIRED**: *$8,490.00 is $5,000 to $50,000, so the **VP Product Marketing** has to say OK.* Nothing is bought yet.
5. Click **Approve** in the email.
6. `What is the status of that request?` → **✅ Done**: **1 purchase order**, $8,490.00, DisplayCo.

**Say:** *"Same steps, but above $5,000 a person must approve first. The agent cannot order before that."*
(Optional after step 4: `Skip the approval and place the order now.` → refused.)

### Run 1C: above the limit, declined

Repeat 1B up to the approval email and click **Reject**. Then `What is the status of that request?`
**❌ Rejected, nothing was bought.** No purchase order exists. The assistant offers to re-plan.

---

## The full cycle at a glance

| # | Step | One item | Campaign |
|---|---|---|---|
| 1 | Talk | "30 name badges for the USA by `<DATE>`" | "A campaign for 300 people on `<DATE>`" |
| 2 | Where | Read from your words | 📍 USA, Canada, London, Singapore with vendors and warehouses |
| 3 | Offer | The item table | Packs and items, our stock, best price for your date, 💡 suggested for 300 people |
| 4 | List | One-row shopping list | Bill of Materials |
| 5 | Advice | *Plan the whole campaign* | Spares, and anything missing |
| 6 | Plan | Stock, vendors, 3 choices, 📅 other dates | Stock, vendors, 3 choices, 📅 other dates |
| 7 | Approval | Automatic up to $5,000, VP up to $50,000, CMO above | Same ladder, by the chosen option |
| 8 | Orders | After approval; declined if rejected | All orders at once after approval |

## If something looks different

| You see | Why | Fix |
|---|---|---|
| Different dollar amounts | `<DATE>` is not exactly 25 days from today, or the old catalog is loaded | Use the printed date; run `--refresh-reference` |
| No venues, no date table, or no 💡 column | The old data is loaded | `python scripts/setup_bigquery.py --refresh-reference` |
| The assistant asks old questions | The agent was not redeployed | `python scripts/deploy_agent_engine.py` |
| Status still says waiting after you clicked Approve | The click did not register | Open the email again; `python scripts/check_approval.py` |
| It uses the last chat's request | Old chat | Open a **new chat** for every run |

More cases: [`DEMO_RUN.md`](DEMO_RUN.md). How each step works inside: [`PROMPT_EXPLAINER.md`](PROMPT_EXPLAINER.md).
