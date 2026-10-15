---
name: plan-and-advice
description: Use once the details are closed and the user has picked what they need, and whenever they change the list, the region, the date, or report a vendor delay before approval. Builds the shopping list, gives advice, and shows the stock, vendors, three choices and other dates.
---

# From the picks to the plan

1. register_launch_request(campaign, summary, deadline_date=date_iso) -> request_id (this creates a new campaign; if the campaign
   was already created with create_campaign, it is found and not duplicated).
2. Call the brief_analyst_agent tool with the request_id, the bundles and the items. It returns the shopping list and business
   advice together as `display_markdown` (plus advice_count).
   - advice_count above 0: reply with its `display_markdown` exactly as it is, with real line breaks, never as text with \n in it
     (the advice ends with the question "Want any of these? ... Say Looks good"). End your turn there. When the user adds
     something, call the brief_analyst_agent tool again with the COMPLETE updated list and show the new shopping list and
     advice. When they say it looks good, go on to step 3.
   - advice_count is 0: go straight to step 3 in the same turn.
3. Call the sourcing_planner_agent tool with the request_id. It returns an "In short" box, what we have in stock, what vendors can
   do and by when, the three choices and a table of other dates.
4. Read decision_mode from its answer.
   - AUTOPILOT: the best option is within the automatic limit. Load the `approval-and-orders` skill, then call authorize_launch
     with option "recommended", then call the fulfilment_agent tool, then show its summary.
   - CHOOSE: reply with ONE message in this order: the "In short" box, what we have in stock, what vendors can do, the 3 choices
     table, the dates table. It asks "Does this plan feel good?". End your turn there: do NOT authorise anything.
5. If the user wants a change (more or less of something, another region): call the brief_analyst_agent tool with the complete
   updated list, then the sourcing_planner_agent tool, and show the new plan as in step 4. If the user wants another date ("move
   it to 14 Nov", "do it earlier"): call register_launch_request again with the same campaign and the new date as YYYY-MM-DD,
   then proceed with the new request_id and the same list. Never change anything after a sign-off.
6. When the user reports a vendor delay: call the sourcing_planner_agent tool with the request_id and the delay. If the request is
   not signed off yet, show the new plan again as in step 4.

For selected items the steps are the same, just shorter. The tip that a whole campaign plan gets better stock reuse, more vendors
and better rates is already in the 3-choices table text.

The specialists are tools you call: write everything one needs in its request (request_id, campaign, bundles and items with
quantities and regions, vendor and delay days) and use what it returns.
