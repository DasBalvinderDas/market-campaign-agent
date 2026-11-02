# Approval in the Gemini Enterprise Inbox

Tested: a workflow step shows in the Inbox as **Needs input**.

## How it works

1. The requester chats with the assistant and chooses an option.
2. The assistant records the sign-off as waiting.
3. A notice email goes to the approver.
4. The email has no Approve or Reject button.
5. It gives the request number and three steps.
6. The approver starts the **LaunchKit order approval** workflow.
7. The approval question shows in their Inbox under **Needs input**.
8. They choose Approve or Reject there.
9. The workflow places the orders.

An approval step can only ask the person running the workflow.
So the approver starts it.

## The defaults

No `.env` lines are needed.

```
APPROVAL_CHANNEL=workflow
APPROVAL_NOTIFY_EMAIL=true
```

- `APPROVAL_NOTIFY_EMAIL=false` turns the notice emails off.
- `APPROVAL_CHANNEL=email` brings back the approval email with buttons.
- `APPROVAL_CHANNEL=gemini` approves in the chat only.
- Deploy the agent again after any change.

## Two addresses per person

The approver table keeps two addresses.

| Address | Used for |
|---|---|
| Notice email | Approval notice and orders-placed email |
| Sign-in | Who may approve in Gemini Enterprise |

They can differ. For now:

```
python scripts/set_approvers.py dasbalvinder.das@hcltech.com=dasbalvinder.das@labgtm.com
```

- Emails go to the hcltech.com address.
- Only the labgtm.com sign-in may approve.
- Add more people by listing more pairs.
- Leave out `=sign-in` when both are the same.
- `--show` prints the table.
- Check a sign-in: say **Run the inbox test** in the chat.

## Build the workflow

Open **Workflow** in the left menu.
Paste this into the box and press the arrow:

> Build a workflow called "LaunchKit order approval".
> It has one start field, the request number.
> Step 1: run the existing agent LaunchKit-Provisioner with the instruction "Show my approvals".
> Step 2: ask the person running the workflow to approve or reject, and show the reply of step 1.
> If approved, Step 3: run the existing agent LaunchKit-Provisioner with the instruction "Approve request {request number}. Then place the orders."
> If rejected, Step 3: run the existing agent with the instruction "Reject request {request number}."
> Show the agent's last reply as the result.

- Check each step in the draft.
- If the agent is not found, add it with the puzzle-piece icon.
- Click **Turn on** to publish.
- Run it from the Workflow list.
- Test runs may not reach the Inbox. Real runs do.

## Try it

1. In the chat, plan an order above $5,000.
2. Say **Choose option 2**.
3. Note the request number.
4. Check the notice email.
5. Start the workflow with that number.
6. Open the **Inbox**.
7. Open the item under **Needs input**.
8. Choose Approve.
9. The orders are placed.

## How the agent checks the answer

- The agent steps run as the person who started the workflow.
- That sign-in must be on the approver list.
- Otherwise the agent refuses and logs it.
- The first decision wins.

## What is not automated

- The workflow itself is built in the console.
- The approver starts it by hand.
- The workflow editor has an **App event** trigger.
- It may start the workflow from the notice email.
- That is a later experiment.

## Can the workflow be created by a script?

Not confirmed. `scripts/probe_workflow_api.py` checks.

- `python scripts/probe_workflow_api.py --inspect --schema Agent`
- `--list` shows the agents in the app.
- `--export NAME` saves one as JSON.
- `--create FILE --yes` creates one from JSON.
- The agents API is v1alpha, so names may change.

## What stays in Application Integration

- `create_purchase_order` and `create_depot_transfer` place the orders.
- `send_launch_update` sends the notice emails.
- `request_approval` is used only with `APPROVAL_CHANNEL=email` or `both`.

## Limits

- Anyone who can call the agent could try to approve.
- The sign-in check lowers the risk. It does not remove it.
- Use `APPROVAL_CHANNEL=email` for anything real.
