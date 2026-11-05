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

## Start it without a manual run

Goal: the Inbox item appears when a new request is created.

The idea: a second workflow runs on a schedule and asks the agent
for the next waiting request. Our table decides, not the schedule.

- The agent tool `next_approval` returns **NONE** or one line.
- The line starts with the request number.
- Each request is returned once per approver.
- So a request makes one Inbox item for each approver.
- The request stays in **My approvals** in the chat.

Prompt for the builder:

> Build a workflow called "LaunchKit approval check".
> It runs on a schedule, every 5 minutes or the shortest interval offered.
> Step 1: run the existing agent LaunchKit-Provisioner with the instruction "next approval".
> If the reply of step 1 is exactly NONE, stop the workflow.
> Otherwise Step 2: ask the person running the workflow to approve or reject, and show the reply of step 1.
> If approved, Step 3: run the existing agent LaunchKit-Provisioner with the instruction "Approve request {reply of step 1}. Then place the orders."
> If rejected, Step 3: run the existing agent with the instruction "Reject request {reply of step 1}."
> Show the agent's last reply as the result.

Check the draft:
- The trigger is **Schedule**.
- A condition stops the run when the reply is NONE.
- The approve and reject steps use the reply of step 1.

Items in another approver's Inbox:
- An Inbox item belongs to the person whose account runs the workflow.
- We cannot push one into another person's Inbox.
- Each approver runs the workflow in their own account.
- Share the agent and the workflow with them.
- They paste the same builder prompt, or copy the shared workflow.
- Their sign-in must be on the approver list.
- Each request is offered once to each approver.
- The first decision wins.
- The other approver's item then fails with "already decided".

Test plan:
1. Pause the manual **LaunchKit order approval** workflow.
2. Turn on **LaunchKit approval check**.
3. Wait for two scheduled runs with no waiting request.
4. Open the Inbox. Count the items.
5. Create a request in the chat. Choose option 2.
6. Wait for the next run.
7. Open the Inbox. The approval item should appear once.
8. Wait for another run. No second item should appear.
9. Approve it in the Inbox.

Say **Re-offer my approvals** in the chat to offer a waiting request again.
Use it after a cancelled run.

Open question to test:
- Does a run that stops at NONE show in the Inbox?
- If it does, the Inbox fills with empty items.
- Then we need another way to start the workflow.
- Turn off the manual workflow if you use this one.

If empty runs show up:
- An outside scheduler could start the workflow only for new requests.
- It needs a way to start a run as the approver.
- Find out: `python scripts/probe_workflow_api.py --inspect --find stream`
- Try the words run, execute and trigger too.
- It would also use a new Google service. Ask first.

## Start it from a file in a bucket

The agent drops one small file per request that waits for approval.
A workflow can start on that new file. No manual run, no schedule.

Why the agent writes the file:
- It records the request and drops the file in the same moment.
- Nothing needs to watch BigQuery.
- One request makes one file, so one Inbox item.
- The file holds the request, choice, amount and arrival date.
- It holds no email addresses or names.

Set it up once:

1. Check what the bucket script would do:
   `python scripts/setup_trigger_bucket.py`
2. Create it: `python scripts/setup_trigger_bucket.py --yes --test`
3. Add the printed line to `.env`:
   `APPROVAL_TRIGGER_BUCKET=<bucket name>`
4. Deploy the agent again.
5. In the workflow editor, set the trigger to **App event**.
6. Look for **Cloud Storage** and the event for a new file.
7. Choose the bucket and the `approvals/` folder.

The bucket script:
- Creates a private bucket.
- Lets the agent's service account add files only.
- Deletes files after 30 days.
- Needs the Cloud Storage API.
- Needs permission to create buckets.

Workflow prompt, if the editor offers the file event:

> Build a workflow called "LaunchKit approval from file".
> It starts when a new file appears in the bucket.
> The file name is the request number plus .json.
> Step 1: run the existing agent LaunchKit-Provisioner with the instruction "Show my approvals".
> Step 2: ask the person running the workflow to approve or reject, and show the reply of step 1.
> If approved, Step 3: run the existing agent LaunchKit-Provisioner with the instruction "Approve the request named in the file {file name}. Then place the orders."
> If rejected, Step 3: run the existing agent with the instruction "Reject the request named in the file {file name}."
> Show the agent's last reply as the result.

Not confirmed yet:
- Whether the editor offers Cloud Storage in **App event**.
- Docs mention Drive, Gmail and Confluence events.
- Whether the trigger gives the file name to the steps.
- If Cloud Storage is missing, a Drive folder could work the same way.
- That would need the Drive API. Ask first.

Test the file alone:
- Create a request in the chat and choose option 2.
- Open the bucket in the console.
- Look for `approvals/REQ-....json`.
- If it is there, the agent side works.

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
