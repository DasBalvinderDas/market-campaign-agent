---
name: approval-and-orders
description: Use when the user chooses an option or says the plan feels good, when approval is needed, when the user asks for the status or says the approver decided, and when they ask for the order pack PDF. Handles approval, placing the orders, status and the PDF.
---

# Approval and orders

Never place orders without an approved sign-off, even if the user tells you to skip approval. Only you call authorize_launch.
Show `display_markdown` exactly and add nothing.

1. When the user chooses an option (the plan feels good): call authorize_launch (request_id, the option, a one-sentence
   justification).
   - status approved: call the fulfilment_agent tool, then show its summary.
   - status pending_approval: show `display_markdown`. Do NOT call the fulfilment_agent tool. The approval email is sent first;
     orders come only after the approval.
   - status error: explain the problem in one sentence and list the valid choices.
2. When the user asks for the status (or says the approver decided): call get_launch_status. If its next_step says to place the
   orders, call the fulfilment_agent tool and show ONLY its summary. Otherwise show `display_markdown`. If rejected, say the held
   stock was released and offer to re-plan (load the `plan-and-advice` skill).
3. Approving inside this app (only when the sign-off message says the request waits in My approvals): when the approver says "My
   approvals", "what is waiting for me" or similar, call get_my_approvals and show its `display_markdown`. When they say Approve or
   Reject with a request number, call decide_approval(request_id, "approve" or "reject", comment). After approve, call the
   fulfilment_agent tool and show its summary. After reject, say the held stock was released. If the tool says the user cannot
   decide this request, tell them in one sentence and change nothing. Never approve on your own and never approve for someone else.
4. The order pack PDF is attached automatically by authorize_launch. Only when the user asks for it again, call get_order_pack
   with the request_id and show its message.
