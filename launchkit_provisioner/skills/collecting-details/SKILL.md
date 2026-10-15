---
name: collecting-details
description: Use at the start of a conversation and whenever the user is still describing a new campaign or a quick purchase (how many people, date, place, campaign name, what they want). Tracks the facts given so far and asks the one next question.
---

# Collecting the details

Users talk naturally. They say things like "Hi, I am looking for a campaign for 300 people on 31st Oct in London". Read what you
can from their words and NEVER make them repeat anything.

Before the user chooses what they need, you must have these facts (any order, or all in one go):
1. the campaign: an existing one (load the `existing-campaigns` skill) or a new name
2. how many people
3. the date
4. the place
5. what they pick (only after 1 to 4)

If they only want some items: just the date, the place and the items. No name or headcount (use the campaign name "Quick purchase").

## What to do on every turn while collecting
Keep track of what they have given across the WHOLE conversation. Call show_checklist with all of it (mode="campaign" unless they
only want some items) and show its `display_markdown` exactly. It shows ✅ or ⬜ and asks the ONE next question. Add nothing else.

If an answer conflicts with what they said before, or could mean two things (for example "london" could be the London Campaign
or the place London), do not guess. Ask ONE short clarifying question, then carry on.

## A complete brief in one message
Sometimes the user pastes a whole brief: a product or launch name, a cost center, a public embargo date, an in-hand date ("by Oct
24 sharp"), what they need with quantities ("120 VIP athlete seeding kits, 12 display podiums, 250 buyer presentation kits") and
where it goes (an event or city, for example the New York marathon expo means the USA). Take everything from it and ask for
NOTHING that is already there:
- campaign name: the launch or product name in the brief (for example "Aether Strider Pro Marathon Launch")
- cost center and embargo date: pass them to create_campaign as `cost_center` and `embargo_date` (YYYY-MM-DD)
- date: the in-hand date. A date with no year means this year
- place: the place the brief points to (a New York event means USA). If it is really unclear, ask one short question
- picks: turn the quantities into bundles (VIP kits = GUEST_KIT, display podiums = VENUE_DISPLAY, buyer kits and folders =
  SALES_PACK) with the region of the place. The headcount is NOT needed when the quantities are given
Then call show_checklist with all of it, create_campaign (with the cost center and embargo date), and carry on with the plan
(skill `plan-and-advice`) without asking anything else. If the brief asks to check spare stock or packaging first, the plan's
stock table is that answer; if it asks for a safe timeline, the plan's dates and buffer are that answer.

## If they start with the picks
Sometimes the first message is only what they want ("150 water bottles and 10 of each pack"). Keep it: pass it to show_checklist as
`picks` and ask for the missing facts (date, place, then people and name for a campaign). Do not build the shopping list yet.

## Details
- After the date it shows where we can deliver. After the place it shows our offer with a suggestion for their headcount.
- A date needs day and month. With no year the tool uses the current year. The tool returns `date_iso`, `region` and
  `venue_name`: use them. Every pick (bundles and items) gets the region of the place.
- "Use the suggested plan": use the `suggested` bundles and items from the last show_checklist result. Otherwise turn their words
  into bundles (guest welcome kits, venue display stands, sales folders) and items.
- For a new campaign it shows name ideas. The user may say a number ("2") or give their own name. As soon as the name is known,
  call create_campaign(campaign, deadline_date=date_iso, people, venue=venue_name), then call show_checklist again (now with the
  name) and write ONE message: the campaign-created confirmation (its `display_markdown`) followed by the checklist's
  `display_markdown`.
- Do not ask about stock, vendors or prices: you show them.
- When every fact is in and the user has picked what they need, load the `plan-and-advice` skill and carry on.
