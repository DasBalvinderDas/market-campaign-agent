# Live demo: Aether Strider Pro Global Marathon Launch

A different story on the same assistant: a running-shoe launch with 120 VIP athlete kits, 12 expo podiums and 250 cork buyer folios.

## Load the data (wipes everything first)

```bash
cd ~/market-campaign-agent && source .venv/bin/activate
python scripts/setup_demo_aether.py --preview      # shows the three options the demo will produce, changes nothing
python scripts/setup_demo_aether.py                 # empties every table (approver emails stay) and loads the Aether data; asks first
```

Option: `--yes` (no question). The agent does not need a redeploy. To get the original Spring demo back: `python scripts/setup_bigquery.py --refresh-reference`.
**No campaign is created.** You create it in the chat, like any new campaign.

## What is loaded

| Part | Content |
|---|---|
| Vendors | 18: Apex Luxury Packaging, Metro NYC Engraving, Apex Technical Apparel, Midwest Exhibit Fabricators, EcoPackaging Ltd., BioHydrate Nutrition, and a second or third vendor for every item |
| Items and prices | Box $65 (10 days), bib plate $20 (2), singlet XS to L $45 (8), podium $380 (16), cork folio $22 (7), flask kit $27.42 (4), foam samples $2.50 (3); eco box $74 and organic singlet $52; express offers at 3 days (box $79, cork folio $29, singlet $58, podium $520) |
| Our stock | **50 boxes in Boston**, **100 cork folios in Portland**, **0 podiums in Amsterdam** |
| Packs | **VIP athlete seeding kit** = presentation box + laser-etched bib plate + sized race singlet + flask kit; **display podium**; **buyer presentation kit** = cork folio + foam sample set |
| Athletes | A standing list of 120 (XS 18, S 44, M 43, L 15; 70 in the US, 50 in EMEA) that gives every new campaign's kits the right singlet sizes. Emily S. `@emily_runs_fast`, Marcus T. `@marathon_marcus`, David K. `@kenya_stride` are the first three |
| Also | Delivery places (USA, Canada, London, Singapore), shipping lanes, planning rules, approval levels (up to $5,000 automatic, $5,000 to $50,000 VP, above that CMO) and date pricing |

## The chat (open a new chat and talk, step by step)

Nothing is pasted in one go. Say it the way a marketer would, and the assistant asks for what it still needs. After each of your messages it shows a small
✅/⬜ table of what it knows and asks the one next question.

| # | You say | The assistant |
|---|---|---|
| 1 | `Hi` | Greets you, says we have no campaigns yet, and asks about yours |
| 2 | `We are launching the Aether Strider Pro marathon shoe, and everything has to be in hands by October 24 sharp.` | Has the date (this year); asks **how many people** |
| 3 | `120 elite athletes.` | Has the headcount; asks **where** and shows where we can deliver (USA, Canada, London, Singapore, with vendors and warehouses) |
| 4 | `It is for the NYC Marathon expo, so the USA. The cost center is CC-GLOBAL-BRAND-4410 and our public embargo lifts on November 1.` | Has the place; asks the **campaign name** and offers name ideas |
| 5 | `Call it Aether Strider Pro Global Marathon Launch.` | **Creates the campaign** (cost center, embargo 1 Nov, in hand 24 Oct) and shows our offer: packs, single items, our stock, prices, ready-by dates |
| 6 | `I need 120 VIP athlete seeding kits with handle laser etching and sized race singlets, 12 illuminated podiums for the expo pop-ups, and 250 cork buyer presentation kits with foam samples.` | Builds the **shopping list** (Bill of Materials) and gives advice (spares and anything missing) |
| 7 | `Looks good. Please check our depots for spare boxes or packaging first, and make sure the timeline is safe for October 24.` | Shows the plan: **our stock** (50 boxes in Boston, 100 cork folios in Portland), the **vendors compared**, the **three choices** with the delivery date and safety buffer, and **other dates** |
| 8 | `Go with option 2.` | Asks the **VP** to approve (email with Approve and Reject buttons); the order pack PDF appears in the chat |
| 9 | The VP clicks **Approve**, then you say `What is the status of that request?` | **Orders placed**: the purchase orders, the warehouse moves and the launch-team email |

Tips for the demo
- If the assistant asks something you already told it, just answer again; it keeps what you said.
- Step 7 can be split in two ("Looks good", then "Is the timeline safe for October 24?") if you want to pause on the stock table.
- The same story also works in fewer, longer messages, for example steps 2 to 4 in one sentence. The assistant takes whatever you give it and asks only for the rest.
- If you want to show the "no headcount needed" path, give the quantities first (step 6) and the assistant keeps them and asks for the date and place.

## What to expect (computed by the planner, ordering on 15 Oct for 24 Oct)

| Option | Total | Arrives | Note |
|---|---|---|---|
| 1. Buy everything new | about $30,290 | 2 Nov | **misses 24 Oct**: the standard lead times (a podium takes 16 days) are too long |
| 2. Use our stock first (recommended) | about $30,110 | 21 Oct | 72-hour safety buffer. 50 boxes from Boston and 100 folios from Portland; express vendors for the slow items; the VP approves |
| 3. Eco | about $36,960 | 21 Oct | eco materials where they are fast enough, dearer |

Express vendors (RushPack Express, SprintStitch Apparel, FastStage Displays) deliver in 3 days at a higher price. They are what makes 24 Oct possible
from mid-October. The same brief ordered on 8 Oct also works (the stock-first option arrives 22 Oct); on 18 Oct it is just possible (no safety buffer, flagged as moderate risk); from 19 Oct 24 Oct is no longer possible
and the assistant flags it as high risk. The numbers come from the data, so they differ from the demo pack's mock-up ($31,400 / $21,850 / $24,600).

## Not in this demo (yet)

The pack also shows a cost-center budget check ($140,000 left), a SAP purchase order number and a Slack post. This assistant has no budget table, no SAP link
and no Slack step: its orders are Application Integration purchase orders and a launch-team email.
