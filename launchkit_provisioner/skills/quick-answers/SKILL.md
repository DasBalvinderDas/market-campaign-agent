---
name: quick-answers
description: Use when the user asks about the status board, warehouse stock, what happened so far (audit), who approves what (approval levels), or wants the vendor comparison for a request.
---

# Quick answers

Call the matching tool and show its `display_markdown` exactly:
- the status board and warehouse stock: get_launch_overview
- what happened, step by step: get_audit_trail
- who approves what: get_approval_rules
- the stock and vendor comparison for a request: get_vendor_report
- the catalog: get_catalog (it attaches the PDF; never list the catalog as text)
- how the CO₂ is worked out: answer in two sentences from the carbon note in the plan
