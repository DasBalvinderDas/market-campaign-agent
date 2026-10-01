from google.adk.agents import LlmAgent

from .. import config
from ..tools.inventory_tools import check_inventory, reserve_inventory

inventory_agent = LlmAgent(
    name="inventory_agent",
    model=config.MODEL,
    description="Checks campaign material stock and reserves in-stock units; reports shortfalls to procure.",
    instruction=(
        "You are the Inventory Agent. For each item in the request: call check_inventory, then "
        "reserve_inventory for the free units. Report per SKU: reserved quantity and the shortfall "
        "that must be procured. Do not buy anything or discuss budget. "
        "When finished, transfer back to campaign_provisioner with the shortfall list."
    ),
    tools=[check_inventory, reserve_inventory],
)
