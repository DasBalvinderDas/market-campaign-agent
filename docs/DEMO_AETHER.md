# Aether demo

A running-shoe launch. Talk to the assistant step by step.

## Load the data

```bash
cd ~/market-campaign-agent && source .venv/bin/activate
python scripts/setup_demo_aether.py --preview   # shows the options, changes nothing
python scripts/setup_demo_aether.py             # wipes everything, loads Aether data
```

- It asks you to type YES first.
- Add `--yes` to skip that question.
- No campaign is created.
- You create it in the chat.
- Approver emails stay as they are.
- Go back to Spring: `python scripts/setup_bigquery.py --refresh-reference`

## What is loaded

| Part | Content |
|---|---|
| Vendors | 18, with two or three per item |
| Items | Box, bib plate, singlet, podium, cork folio, flask, foam |
| Express offers | 3-day delivery at a higher price |
| Our stock | 50 boxes in Boston |
| | 100 cork folios in Portland |
| | 0 podiums in Amsterdam |
| Packs | Athlete kit, display podium, buyer kit |
| Athletes | A standing list of 120 with sizes |
| Approval | Up to $5,000 automatic |
| | $5,000 to $50,000: VP |
| | Above that: CMO |

## Pick the date first

The demo date must be 9 or more days away.

| Today is | Use this date |
|---|---|
| 15 Oct | October 24 |
| 19 Oct | October 28 |
| Any day | Today plus 9 days |

Closer dates are flagged as risky. That is correct.
The examples below use October 24.

## Option A: one prompt

Open a new chat. Paste this in one go.

> Create a campaign called Aether Strider Pro Global Marathon Launch. It is for 120 elite athletes in the USA. Everything is needed by October 24. I need 120 VIP athlete kits. Add handle etching and sized singlets. Also 12 illuminated podiums for the expo. And 250 cork buyer kits with foam samples. Check depots for spare boxes first. Is October 24 safe?

It has all five facts:
1. Campaign name
2. How many people
3. Date
4. Place
5. What you need

So the assistant asks nothing more. It will:
- Create the campaign.
- Show the shopping list and advice.

Then:

| # | You say | The assistant |
|---|---|---|
| 1 | `Looks good.` | Shows stock, vendors, three choices, other dates. |
| 2 | `Go with option 2.` | Asks the VP to approve. Attaches the PDF. |
| 3 | VP clicks **Approve**. Then: `What is the status?` | Places all the orders. |

## Option B: step by step

Open a new chat. Each step is a short message.

| # | You say | The assistant |
|---|---|---|
| 1 | `Hi` | Says there are no campaigns yet. |
| 2 | `We are launching the Aether Strider Pro shoe. Need everything by October 24.` | Asks how many people. |
| 3 | `120 elite athletes.` | Asks where. Shows delivery places. |
| 4 | `The NYC Marathon expo, so the USA.` | Asks for a campaign name. |
| 5 | `Call it Aether Strider Pro Global Marathon Launch.` | Creates the campaign. Shows our offer. |
| 6 | `120 VIP athlete kits with handle etching and sized singlets. 12 illuminated podiums for the expo. 250 cork buyer kits with foam samples.` | Shows the shopping list and advice. |
| 7 | `Looks good. Check depots for spare boxes first. Is October 24 safe?` | Shows stock, vendors, three choices, other dates. |
| 8 | `Go with option 2.` | Asks the VP to approve. Attaches the PDF. |
| 9 | VP clicks **Approve**. Then: `What is the status?` | Places all the orders. |

Tips:
- Answer again if it asks something twice.
- Give quantities first to skip the headcount.

## What to expect

Ordering on 15 Oct for 24 Oct.

| Option | Total | Arrives | Note |
|---|---|---|---|
| 1. Everything new | $30,290 | 2 Nov | Misses 24 Oct |
| 2. Our stock first | $30,110 | 21 Oct | Recommended. 72-hour buffer |
| 3. Eco | $36,960 | 21 Oct | Dearer |

- Option 2 uses 50 boxes from Boston.
- It also uses 100 folios from Portland.
- Express vendors make 24 Oct possible.
- Ordering on 8 Oct also works.
- On 18 Oct there is no buffer.
- From 19 Oct it is high risk.
- Numbers come from the data.
- They differ from the demo pack's mock-up.

## Not in this demo

- Cost-center budget check
- SAP purchase order number
- Slack post
