---
name: plan-and-advice
description: Use once the details are closed and the user has picked what they need, and whenever they change the list, the region, the date, or report a vendor delay before approval. Builds the shopping list, gives advice, and shows the stock, vendors, three choices and other dates.
---

# From the picks to the plan

1. register_launch_request(campaign, summary, deadline_date=date_iso) -> request_id (this creates a new campaign; if the campaign
   was already created with create_campaign, it is found and not duplicated).
2. Call the brief_analyst_agent tool with the request_id, the bundles and the items. It returns the shopping list and advice as
   a short `display_markdown` (two summary lines and one small table) plus advice_count.
   - advice_count above 0: reply with its `display_markdown` exactly, with real line breaks. End your turn there. When the user
     adds something, call the brief_analyst_agent tool again with the COMPLETE updated list. When they say it looks good, go on
     to step 3.
   - advice_count is 0: go straight to step 3 in the same turn.
3. Call the sourcing_planner_agent tool with the request_id. It returns a short plan: two summary lines (the best choice, what
   we have in stock and what we buy, and the highlighted CO₂ with how it is worked out) and one small table of the three choices.
4. Read decision_mode from its answer.
   - AUTOPILOT: the best option is within the automatic limit. Load the `approval-and-orders` skill, call authorize_launch with
     option "recommended", then the fulfilment_agent tool, then show its summary.
   - CHOOSE: reply with the plan's `display_markdown` exactly. Do NOT authorise anything. Only if the user asks for more (vendors,
     other dates, stock), call get_vendor_report or the sourcing planner again and show just what they asked for.
5. If the user wants a change (more or less of something, another region): call the brief_analyst_agent tool with the complete
   updated list, then the sourcing_planner_agent tool, and show the new plan as in step 4. If the user wants another date ("move
   it to 14 Nov", "do it earlier"): call register_launch_request again with the same campaign and the new date as YYYY-MM-DD,
   then proceed with the new request_id and the same list. Never change anything after a sign-off.
6. When the user reports a vendor delay: call the sourcing_planner_agent tool with the request_id and the delay. If the request is
   not signed off yet, show the new plan again as in step 4.

For selected items the steps are the same, just shorter. Every reply is two short paragraphs at most.

The specialists are tools you call: write everything one needs in its request (request_id, campaign, bundles and items with
quantities and regions, vendor and delay days) and use what it returns.
