from google.adk.agents import LlmAgent

from .. import config
from ..tools.inventory_tools import check_inventory, find_sku, reserve_inventory

inventory_agent = LlmAgent(
    name="inventory_agent",
    model=config.MODEL,
    description="Checks campaign material stock and reserves in-stock units; reports shortfalls to procure.",
    instruction=(
        "You are the Inventory Agent. For each item in the request: if the user gave a description rather "
        "than an exact SKU, call find_sku first and use only SKUs it returns (never invent a SKU; if there is "
        "no match, tell the root agent and ask the user to pick from the catalog). Then call check_inventory, then "
        "reserve_inventory for the free units. Report per SKU: reserved quantity and the shortfall "
        "that must be procured. Do not buy anything or discuss budget. "
        "When finished, transfer back to campaign_provisioner with the shortfall list."
    ),
    tools=[find_sku, check_inventory, reserve_inventory],
)
