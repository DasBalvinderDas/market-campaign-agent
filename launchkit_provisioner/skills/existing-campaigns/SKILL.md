---
name: existing-campaigns
description: Use when the user wants to add to an existing campaign, names a campaign by its reference or name (London, US, Singapore, LAUNCH-LONDON), or asks which campaigns we have.
---

# Existing campaigns

We always have three standing campaigns: the London Campaign (LAUNCH-LONDON), the US Campaign (LAUNCH-USA) and the Singapore
Campaign (LAUNCH-SINGAPORE). Their dates are 30 days after setup. Campaigns made in chat are kept too.

1. When the user wants to add to one, or names one by its reference or by its name or a part of it ("london", "the US campaign"),
   call open_campaign(campaign) and show its `display_markdown`.
2. Then use that campaign's name and `date_iso` as the campaign and the date (the user may give another date). Ask only for what is
   still missing (people, place, what they pick) as in the `collecting-details` skill.
3. If they ask which campaigns exist, call open_campaign with no name and show the table.
4. If a reply could mean two things (the London Campaign or the place London), ask ONE short question first, for example "Do you
   want to add to the London Campaign, or start a new campaign delivered to London?"

A fresh campaign works exactly as before: use the `collecting-details` skill.
