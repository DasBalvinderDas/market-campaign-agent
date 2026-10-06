from google.adk.agents import LlmAgent

from .. import config, handoff
from ..workflow import guard
from ..tools.inventory_tools import check_inventory, find_sku, release_inventory, reserve_inventory

inventory_agent = LlmAgent(
    name="inventory_agent",
    model=config.MODEL,
    description="Checks campaign material stock in BigQuery, reserves in-stock units, reports shortfalls, releases reservations.",
    instruction=handoff.adapt(
        "You are the Inventory Agent. For each requested item: if the user gave a description rather than an "
        "exact SKU, call find_sku first and use only SKUs it returns (never invent a SKU; if there is no match, "
        "tell the root agent so the user can pick from the catalog). Then call check_inventory and "
        "reserve_inventory for the free units. Report per SKU: reserved quantity and the shortfall to procure. "
        "If the root agent asks you to release a request's stock (budget declined or rejected), call "
        "release_inventory. Do not buy anything or discuss budget. "
        "Do not write commentary between tool calls. When finished, transfer back to campaign_provisioner."
    ),
    tools=[find_sku, check_inventory, reserve_inventory, release_inventory],
    on_tool_error_callback=guard.on_tool_error,
)
