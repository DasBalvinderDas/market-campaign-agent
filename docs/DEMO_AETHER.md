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

## The chat (new chat)

Paste this brief (the assistant reads the campaign name, cost center, dates, place and quantities from it and asks for nothing else):

> We need to roll out the global marketing collateral for the Aether Strider Pro marathon shoe launch under cost center CC-GLOBAL-BRAND-4410. Our public race-day embargo lifts on November 1 for NYC Marathon weekend, so all assets must be in hands by October 24 sharp. Here's what we need: 1. 120 VIP elite athlete seeding kits with custom handle laser etching and sized race singlets. 2. 12 illuminated shoe display podiums for our NYC Marathon expo pop-ups. 3. 250 cork buyer presentation kits with foam samples for specialty running retailers. Check if we have any spare boxes or packaging in our regional depots first, make sure the timeline is safe for Oct 24.

Then:
1. It creates the campaign (cost center, embargo 1 Nov, in hand 24 Oct), shows the shopping list and any advice: say `Looks good`.
2. It shows our stock (**50 boxes in Boston, 100 cork folios in Portland**), the vendors compared, the three choices and the other dates. **Choose option 2** (the recommended one).
3. The VP clicks **Approve** in the email, then `What is the status of that request?`: orders are placed, the order pack PDF is in the chat.

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
