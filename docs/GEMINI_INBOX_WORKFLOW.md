# Approval in the Gemini Enterprise Inbox

Status: to test. The code is ready. The workflow is built in the console.

## The idea

- A workflow runs our agent in three steps.
- The person running it is the approver.
- Between the steps, an approval step asks that person.
- It shows in their Inbox as **Needs input**.
- They approve or reject there.
- A notice email gives them the request number.

Found while testing: an approval step can only ask the person running the workflow.
It cannot route to another person. So the VP starts the workflow.

## The defaults

This is how the agent ships. No `.env` lines are needed.

```
APPROVAL_CHANNEL=workflow
APPROVAL_NOTIFY_EMAIL=true
```

- The approval happens in the Inbox.
- A plain notice email goes to the approvers.
- It has no buttons.
- It says an approval waits in the Inbox.
- The orders-placed email goes to the launch team.
- `APPROVAL_NOTIFY_EMAIL=false` turns all of it off.
- `APPROVAL_CHANNEL=email` brings back the approval email with buttons.
- If the workflow is not built yet, the VP can say **My approvals** in the chat.
- Deploy the agent again after any change.

## What the agent does in this mode

- It records the sign-off as waiting.
- It sends no approval email with buttons.
- It starts no approval workflow.
- It tells the user the request waits in the Inbox.
- Later it accepts the answer from the workflow.

## Who does what

1. The requester chats with the assistant and chooses an option.
2. The reply says the request waits in the Inbox.
3. A notice email gives the VP the request number.
4. The VP starts the workflow with that number.
5. The VP approves or rejects in the Inbox.
6. The workflow places the orders.

## Build the workflow in the console

The step names may differ in your console. Adjust as needed.

1. Open **Workflow** in the left menu.
2. Add a start form with one field: **Request number**.
3. Add an **existing agent** step. Pick the assistant.
4. Its instruction: *Show my approvals for request {request number}.*
5. Add a **human approval** step. It asks the person running the workflow.
6. Show step 3's reply in the question.
7. Add a second **existing agent** step for approval.
8. Its instruction: *Approve request {request number}. Then place the orders.*
9. Add a branch for rejection with: *Reject request {request number}.*
10. Publish and share it with the approvers.

## Fastest way: describe it in words

The console can build a workflow from a plain description.
Open **Workflow**, choose the natural language option, and paste this:

> Build a workflow called "LaunchKit order approval".
> The start form asks for a request number.
> Step 1: run the existing agent launchkit_provisioner with the instruction
> "Show my approvals for request {request number}".
> Step 2: ask the person running the workflow to approve or reject, and show the reply of step 1.
> If approved, Step 3: run the existing agent launchkit_provisioner with the instruction
> "Approve request {request number}. Then place the orders."
> If rejected, Step 3: run the existing agent with the instruction
> "Reject request {request number}."
> Show the agent's last reply as the result.

Then check each step in the builder and fix what is wrong.

## Can it be automated?

Not confirmed. The script `scripts/probe_workflow_api.py` finds out.

1. Check the API for a create method:
   `python scripts/probe_workflow_api.py --inspect`
2. It prints RESULT. Either a create method exists, or not.
3. If it exists, build the workflow once in the console.
4. Save it:
   `python scripts/probe_workflow_api.py --engine APP_ID --export "LaunchKit order approval" --out workflows/order_approval.json`
5. Rebuild it anywhere:
   `python scripts/probe_workflow_api.py --engine APP_ID --create workflows/order_approval.json --yes`

- APP_ID is your Gemini Enterprise app id.
- `--list` shows the agents in the app.
- Without `--yes`, `--create` only prints what it would send.
- Run it in Cloud Shell. It needs your sign-in.
- The agents API is v1alpha, so names may change.

## What lives in Application Integration

- This workflow is not built by `setup_application_integration.py`.
- It is a Gemini Enterprise workflow, not an Application Integration one.
- Whether an API can create it is not confirmed.
- Application Integration keeps its four triggers.
- `create_purchase_order` and `create_depot_transfer` place the orders.
- `send_launch_update` sends the notice emails.
- `request_approval` is used only with `APPROVAL_CHANNEL=email` or `both`.

## How the agent checks the answer

- The agent steps run as the person who started the workflow.
- That person's sign-in must be on the approver list.
- Otherwise the agent refuses and logs it.
- Add the VP to the list:
  `python scripts/setup_bigquery.py --approver-email vp@example.com`

## Things to confirm while testing

- Can the assistant be picked in an existing agent step?
- Does the approval step show in the Inbox?
- Does it give the approver's address to the next step?
- Does the final reply show as the run result?

## Limits

- Anyone who can call the agent could name an approver.
- The list check lowers the risk. It does not remove it.
- The email approval keeps the stronger record.
- Use `APPROVAL_CHANNEL=email` for anything real.
