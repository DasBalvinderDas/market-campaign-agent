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
The examples below use October 24. Change it in both prompts.

## The demo: two prompts

Open a new chat. Send two prompts.

Replies are short. Each has two paragraphs at most.
The first paragraph is a two-line summary.
The catalog is never shown as text.
It arrives as a PDF in the chat.

**Prompt 1: the campaign**

> Create a campaign called Aether Strider Pro Global Marathon Launch. It is needed by October 24, in New York, USA.

It has four campaign facts:
1. Campaign name
2. Date
3. City
4. Country

- No year means the current year.
- The number of people is optional.
- The assistant creates the campaign.
- It attaches the catalog PDF.
- Then it asks what you need.

**Prompt 2: what to procure**

> I need 120 VIP athlete kits with handle etching and sized singlets. Also 12 illuminated podiums for the expo. And 250 cork buyer kits with foam samples. Check depots for spare boxes first. Is October 24 safe?

The assistant shows a short shopping list and advice.

Then:

| # | You say | The assistant |
|---|---|---|
| 1 | `Looks good.` | Shows the best plan and three choices. |
| 2 | `Choose option 2.` | Asks the VP to approve. Attaches the PDF. |
| 3 | VP clicks **Approve**. Then: `What is the status?` | Places all the orders. |

## The plan reply

- The first line names the best option.
- It shows price, arrival day and spare time.
- It shows what comes from our stock.
- The second line highlights the carbon.
- The carbon is marked with a 🌱.
- The greenest option is bold in the table.

## How the carbon is worked out

- Each vendor gives a CO₂ estimate per item.
- We multiply it by the quantity.
- We add a little for transport.
- Eco means recycled or organic materials.
- Eco does not always mean biodegradable.

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
