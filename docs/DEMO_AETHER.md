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
| Vendors | 13: Apex Luxury Packaging, Metro NYC Engraving, Apex Technical Apparel, Midwest Exhibit Fabricators, EcoPackaging Ltd., BioHydrate Nutrition, and a second or third vendor for every item |
| Items and prices | Box $65 (10 days), bib plate $20 (2), singlet XS to L $45 (8), podium $380 (16), cork folio $22 (7), flask kit $27.42 (4); eco box $74 and organic singlet $52 |
| Our stock | **50 boxes in Boston**, **100 cork folios in Portland**, **0 podiums in Amsterdam** |
| Packs | **VIP athlete seeding kit** = presentation box + laser-etched bib plate + sized race singlet + flask kit; **display podium**; **buyer presentation folio** (cork) |
| Athletes | A standing list of 120 (XS 18, S 44, M 43, L 15; 70 in the US, 50 in EMEA) that gives every new campaign's kits the right singlet sizes. Emily S. `@emily_runs_fast`, Marcus T. `@marathon_marcus`, David K. `@kenya_stride` are the first three |
| Also | Delivery places (USA, Canada, London, Singapore), shipping lanes, planning rules, approval levels (up to $5,000 automatic, $5,000 to $50,000 VP, above that CMO) and date pricing |

## The chat (new chat)

1. `Hi`: it says we have no campaigns yet and asks about yours.
2. `A campaign for 120 people on 24 Oct in the USA`, then name it **Aether Strider Pro Global Marathon Launch** (a date without a year means this year; use a date at least 20 days away).
3. `Use the suggested plan` (120 kits, 12 podiums, 250 folios), then `Looks good`: stock, vendors, three choices, other dates. **Choose option 2** (the recommended one).
4. The VP clicks **Approve** in the email, then `What is the status of that request?`: orders are placed, the order pack PDF is in the chat.

## What to expect (computed by the planner, today's date)

| Option | Total | Note |
|---|---|---|
| 1. Buy everything new | about $29,640 | baseline |
| 2. Use our stock first (recommended) | about $24,190 | saves about $5,450: 50 boxes from Boston and 100 folios from Portland; the VP approves |
| 3. Eco | about $31,560 | recycled box and organic singlet, about $1,920 dearer |

With a date 20 days away, all three arrive with a 48-hour safety buffer (the podium's 16-day lead time decides the date); a date much closer is flagged as risky. The numbers come from the data, so they differ a little from
the demo pack's mock-up ($31,400 / $21,850 / $24,600).

## Not in this demo (yet)

The pack also shows a cost-center budget check ($140,000 left), a SAP purchase order number and a Slack post. This assistant has no budget table, no SAP link
and no Slack step: its orders are Application Integration purchase orders and a launch-team email.
