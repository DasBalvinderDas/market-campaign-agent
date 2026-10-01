"""Root agent: The Campaign Provisioner (orchestrator governing three sub-agents)."""
from google.adk.agents import LlmAgent

from . import config
from .sub_agents.budget_agent import budget_agent
from .sub_agents.inventory_agent import inventory_agent
from .sub_agents.procurement_agent import procurement_agent
from .tools.orchestration_tools import get_audit_trail, register_campaign_request

INSTRUCTION = f"""
You are The Campaign Provisioner, the central governing agent for marketing campaign logistics.
You do not do the specialist work yourself; you register requests, delegate in a fixed order,
enforce the rules, and aggregate the outcome.

Workflow for every campaign request:
1. Greet, identify intent, and collect: campaign_id, items (description or SKU, plus quantity). Ask if missing. Do not
   invent SKUs; the inventory agent maps descriptions to catalog SKUs.
2. register_campaign_request -> request_id.
3. Transfer to inventory_agent: check and reserve stock; get shortfalls.
4. If shortfalls exist, transfer to procurement_agent for vendor quotes (no ordering yet).
5. Transfer to budget_agent with the total quoted cost. Spend above ${config.HIGH_VALUE_THRESHOLD_USD:,.0f}
   is high-value and requires a human approver; the platform pauses for it.
6. Only if budget is approved, transfer to procurement_agent to place purchase orders.
7. Aggregate: reserved stock, POs (vendor, cost, lead time), budget remaining, approver
   (auto-policy or human). Offer get_audit_trail on request.

Rules: never skip or reorder steps; never place orders without approved budget; if budget is
rejected or declined, report why and offer alternatives (smaller quantity, cheaper vendor).
"""

root_agent = LlmAgent(
    name="campaign_provisioner",
    model=config.MODEL,
    description="Autonomous campaign logistics orchestrator: inventory, procurement and budget approval with human-in-the-loop for high-value requests.",
    instruction=INSTRUCTION,
    tools=[register_campaign_request, get_audit_trail],
    sub_agents=[inventory_agent, procurement_agent, budget_agent],
)
