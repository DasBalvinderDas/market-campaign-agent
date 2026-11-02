# Inbox test

Step 1 of the notification work.
Goal: see one notification in the Gemini Enterprise Inbox.

## What the test does

- The agent has a harmless tool called `inbox_test`.
- It changes nothing.
- It replies with the time it ran.
- It says what sign-in the agent sees.
- It says if that sign-in is on the approver list.
- It never prints an email address.

## Steps

1. Deploy the agent: `python scripts/deploy_agent_engine.py`
2. Open **Workflow** in Gemini Enterprise.
3. Paste the prompt below into the builder.
4. Check the draft. Publish it.
5. Run the workflow.
6. Open **Inbox**.
7. Look under **Needs input**.

## The prompt

> Build a workflow called "LaunchKit inbox test".
> It has no start form.
> Step 1: run the existing agent launchkit_provisioner with the instruction "Run the inbox test".
> Step 2: ask the person running the workflow "Do you see this in your Inbox?" with the choices Yes and No, and show the reply of step 1.
> Show the answer as the result.

If the agent is not found, add it with the puzzle-piece icon.

## What to report

- A screenshot of the Inbox.
- The reply of step 1.
- Was the agent found by the builder?
- Did a **Needs input** item appear?
- Did **Done** appear after you answered?

## Check the agent alone first

In a normal chat, type: `Run the inbox test`.
You should see two lines.

## Next steps (not built yet)

- One notification for a real approval.
- Then the order-placed notification.
- Then the email notices.
