# Live demo: Aether Strider Pro Global Marathon Launch

A different story on the same assistant: a running-shoe launch with 120 VIP athlete kits, 12 expo podiums and 250 cork buyer folios.

## Load the data (wipes everything first)

```bash
cd ~/market-campaign-agent && source .venv/bin/activate
python scripts/setup_demo_aether.py --preview      # shows the three options the demo will produce, changes nothing
python scripts/setup_demo_aether.py                 # empties every table (approver emails stay) and loads the Aether data; asks first
```

Options: `--no-standing` (only the Aether campaign: no London, US or Singapore campaigns), `--yes` (no question), `--in-hand-days 25` (default 20), `--exact-dates` (the pack's 24 Oct and 1 Nov 2026).
The agent does not need a redeploy. To get the original Spring demo back: `python scripts/setup_bigquery.py --refresh-reference`.

## What is loaded

| Part | Content |
|---|---|
| Campaign | **Aether Strider Pro Global Marathon Launch**, cost center `CC-GLOBAL-BRAND-4410`, in hand today + 20 days, embargo 8 days later. The London, US and Singapore campaigns stay |
| Athletes | 120: XS 18, S 44, M 43, L 15; 70 in the US, 50 in EMEA (UK and Kenya). Emily S. `@emily_runs_fast`, Marcus T. `@marathon_marcus`, David K. `@kenya_stride` are the first three |
| Packs | **VIP athlete seeding kit** = presentation box + laser-etched bib plate + sized race singlet + flask kit; **display podium**; **buyer presentation folio** (cork) |
| Items and vendors | Box $65 (10 days), bib plate $20 (2), singlet $45 (8), podium $380 (16), cork folio $22 (7), flask kit $27.42 (4), each with two or three vendors; eco box ($74) and organic singlet ($52) |
| Our stock | **50 boxes in Boston**, **100 cork folios in Portland**, **0 podiums in Amsterdam** |
| Approval | Up to $5,000 automatic, $5,000 to $50,000 VP, above that CMO (unchanged) |

## The chat (new chat)

1. `Hi`: it shows the campaigns we have.
2. `Add to the Aether Strider Pro campaign`: it opens the campaign and its date.
3. `120 people, USA`, then `use the suggested plan` (120 kits, 12 podiums, 250 folios).
4. `Looks good`: stock, vendors, three choices, other dates. **Choose option 2** (the recommended one).
5. The VP clicks **Approve** in the email, then `What is the status of that request?`: orders are placed, the order pack PDF is in the chat.

## What to expect (computed by the planner, today's date)

| Option | Total | Note |
|---|---|---|
| 1. Buy everything new | about $29,640 | baseline |
| 2. Use our stock first (recommended) | about $24,190 | saves about $5,450: 50 boxes from Boston and 100 folios from Portland; the VP approves |
| 3. Eco | about $31,560 | recycled box and organic singlet, about $1,920 dearer |

All three arrive with a 48-hour safety buffer (the podium's 16-day lead time decides the date). The numbers come from the data, so they differ a little from
the demo pack's mock-up ($31,400 / $21,850 / $24,600).

## Not in this demo (yet)

The pack also shows a cost-center budget check ($140,000 left), a SAP purchase order number and a Slack post. This assistant has no budget table, no SAP link
and no Slack step: its orders are Application Integration purchase orders and a launch-team email.
