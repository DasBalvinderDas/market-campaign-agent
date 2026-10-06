from google.adk.agents import LlmAgent

from .. import config, handoff
from ..workflow import guard
from ..tools.inventory_tools import (check_inventory, find_sku, release_inventory, reserve_inventory,
                                     reserve_items)

inventory_agent = LlmAgent(
    name="inventory_agent",
    model=config.MODEL,
    description="Checks campaign material stock in BigQuery, reserves in-stock units, reports shortfalls, releases reservations.",
    instruction=handoff.adapt(
        "You are the Inventory Agent. Call reserve_items ONCE with every requested item (SKU or description, plus "
        "quantity): it matches the catalog, checks stock and reserves the free units for all items in one step. "
        "If it returns needs_clarification, report the unresolved items and their candidates so the user can pick "
        "(never invent a SKU). Use find_sku / check_inventory / reserve_inventory only for a single follow-up. "
        "Report per SKU: reserved quantity and the shortfall to procure. "
        "If the root agent asks you to release a request's stock (budget declined or rejected), call "
        "release_inventory. Do not buy anything or discuss budget. "
        "Do not write commentary between tool calls. When finished, transfer back to campaign_provisioner."
    ),
    tools=[reserve_items, find_sku, check_inventory, reserve_inventory, release_inventory],
    on_tool_error_callback=guard.on_tool_error,
)
