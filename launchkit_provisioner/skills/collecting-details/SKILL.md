---
name: collecting-details
description: Use at the start of a conversation and whenever the user is still describing a new campaign or a quick purchase (campaign name, date, city, country, what they want). Tracks the facts given so far, asks the one next question and creates the campaign.
---

# Collecting the details

The conversation has TWO steps. Replies are two short paragraphs at most; the first is a two-line summary.

**Step 1: the campaign.** The user gives the campaign name, the date, the city and the country. Example: "Create a campaign called
Aether Strider Pro Global Marathon Launch, needed by November 15, in New York, USA." The number of people is optional: never ask
for it.
**Step 2: what to procure.** The user describes what they want and how many. Example: "I need 120 VIP athlete kits and 12
illuminated podiums."

Read what you can from their words and NEVER make them repeat anything. If they only want some items: just the date, the place
and the items; use the campaign name "Quick purchase".

## Step 1, every turn
Call show_checklist with everything said so far (mode="campaign" unless they only want some items) and show its `display_markdown`
exactly. It asks the ONE next question. Pass the place as the user said it ("New York, USA"). It returns `date_iso`, `region`,
`venue_name` and `place` (the city and country): use them. If an answer could mean two things (the London Campaign or the place London), ask ONE short question.

As soon as the name, the date and the place are known, call create_campaign(campaign, deadline_date=date_iso, people, venue=place)
and show its `display_markdown` exactly. It attaches the catalog PDF to the chat and asks "What do you need?". Do not call
show_checklist again and do not show the catalog as text.

## Dates
A date needs day and month. Pass it exactly as the user said it ("31st Oct"); the tool uses the current year when none is given.
Never ask for the year and never add one yourself.

## Step 2
Turn their words into bundles (VIP or guest kits = GUEST_KIT, display podiums and stands = VENUE_DISPLAY, buyer kits and folders
= SALES_PACK) and single items, each with the region of the place. Then load the `plan-and-advice` skill and carry on. The
headcount is NOT needed when the quantities are given. A complete brief in one message (name, date, place and what they need) is
fine: create the campaign, then carry on with the plan. A cost center or embargo date in the brief goes to create_campaign as
`cost_center` and `embargo_date` (YYYY-MM-DD).

If they start with only the picks ("150 water bottles"), keep them as `picks` for show_checklist and ask for the missing facts.
Do not ask about stock, vendors or prices.
