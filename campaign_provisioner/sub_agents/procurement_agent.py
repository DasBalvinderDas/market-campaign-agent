from google.adk.agents import LlmAgent

from .. import config
from ..tools.procurement_tools import get_vendor_quotes, place_purchase_order

procurement_agent = LlmAgent(
    name="procurement_agent",
    model=config.MODEL,
    description="Sources shortfall items: gets vendor quotes, recommends a vendor, places POs once budget is approved.",
    instruction=(
        "You are the Procurement Agent. Step 1 (quote): for each shortfall SKU call get_vendor_quotes "
        "and recommend a vendor (cheapest unless lead time breaks the campaign date); report the "
        "total cost and then transfer to campaign_provisioner so budget approval can happen. "
        "Step 2 (order): only when the orchestrator tells you the budget is approved, call "
        "place_purchase_order per SKU. If a PO is 'blocked', never retry or work around it - "
        "transfer to campaign_provisioner and explain. Never approve budget yourself."
    ),
    tools=[get_vendor_quotes, place_purchase_order],
)
