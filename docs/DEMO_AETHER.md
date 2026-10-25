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
| Vendors | 22, with two or three per item |
| | 2 based in London, 2 in Singapore |
| Items | Box, bib plate, singlet, podium, cork folio, flask, foam |
| | Banner and tote, for London and Singapore |
| Express offers | 3-day delivery at a higher price |
| Our stock | 50 boxes in Boston |
| | 100 cork folios in Portland |
| | 0 podiums in Amsterdam |
| | London: 40 banners, 150 totes |
| | Singapore: 30 banners, 200 totes |
| Packs | Athlete kit, display podium, buyer kit |
| Athletes | A standing list of 120 with sizes |
| Approval | Up to $5,000 automatic |
| | $5,000 to $50,000: VP |
| | Above that: CMO |

## Pick the date first

Use a date 25 or more days away.
Then all three choices arrive in time.
Nothing asks you to pick another date.

| Today is | Use this date |
|---|---|
| 21 Oct | November 15 |
| Any day | Today plus 25 days |

Closer dates make "buy everything new" miss the deadline.
The examples below use November 15. Change it in prompt 1.

## The demo: two prompts

Open a new chat. Send two prompts.

Replies are short. Each has two paragraphs at most.
The first paragraph is a two-line summary.
The catalog is never shown as text.
It arrives as a PDF in the chat.

**Prompt 1: the campaign**

> Create a campaign called Aether Strider Pro Global Marathon Launch. It is needed by November 15, at the Javits Center, New York, USA.

It has four campaign facts:
1. Campaign name
2. Date
3. Place and city
4. Country

- No year means the current year.
- The number of people is optional.
- The assistant creates the campaign.
- It attaches the catalog PDF.
- Then it asks what you need.

**Prompt 2: what to procure**

> I need 120 VIP athlete kits with handle etching and sized singlets. Also 12 illuminated podiums for the expo. And 250 cork buyer kits with foam samples. Check depots for spare boxes first.

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

- CO₂ is carbon dioxide from making and shipping.
- Making is the vendor's figure per item.
- We multiply it by the quantity.
- Shipping is the item's weight factor.
- We multiply it by the lane distance.
- We use 0.1 kg per factor per 1,000 km.
- Items from our stock only add shipping.
- Eco means recycled or organic materials.
- Eco does not always mean biodegradable.
- Vendor figures are demo estimates.
- Real vendors would supply their own.
- Every reply with CO₂ says "making + shipping".

## Tracking the orders

- The request number is in bold.
- Every purchase order number is in bold.
- Warehouse move numbers are in bold too.
- Both numbers appear in the order pack PDF.
- The PDF arrives again when orders are placed.

## What to expect

Ordering on 21 Oct for 15 Nov.

| Option | Total | Spare time |
|---|---|---|
| 1. Everything new | $30,290 | 7 days |
| 2. Our stock first | $24,840 | 7 days |
| 3. Eco | $32,210 | 7 days |

- Option 2 is recommended.
- It uses 50 boxes from Boston.
- It also uses 100 folios from Portland.
- The VP approves it.
- Numbers come from the data.
- They differ from the demo pack's mock-up.

## Approving inside the app

Set this in `.env`, then deploy again.

```
APPROVAL_CHANNEL=gemini
```

| Value | What happens |
|---|---|
| email | Approval email with buttons. The default. |
| gemini | No emails. The approver decides in the chat. |
| both | Email and in-app. |

- The approver says **My approvals**.
- The agent lists the waiting requests.
- The approver says **Approve REQ-…** or **Reject REQ-…**.
- Then the agent places the orders.
- The approver's address must be on the approver list.
- Add it: `python scripts/setup_bigquery.py --approver-email you@example.com`
- Set `APPROVAL_CHECK_USER=false` to skip that check.
- Use that only for a demo.
- No launch-team email is sent in gemini mode.
- The reply and the order pack PDF are the confirmation.
- This is not the Gemini Enterprise Inbox page.
- That page shows agent tasks and workflow runs.

## Not in this demo

- Cost-center budget check
- SAP purchase order number
- Slack post
