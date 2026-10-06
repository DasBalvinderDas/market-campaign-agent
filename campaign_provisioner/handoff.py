"""How the root agent reaches the specialists.

SUBAGENT_MODE=transfer (default): the chat is handed over with transfer_to_agent and the specialist writes the replies.
SUBAGENT_MODE=tool: each specialist is a tool the root agent calls; the root agent writes every reply. Use it where the
front end only shows the root agent's answers (for example Gemini Enterprise).
"""
import re

from . import config

TOOL_MODE = config.SUBAGENT_MODE == "tool"

_TO_TOOL = [
    (r"[Tt]ransfer back to campaign_provisioner right away with", "Finish right away by replying with"),
    (r"transfer back to campaign_provisioner", "reply with your report"),
    (r"then transfer to campaign_provisioner so", "then reply with your quotes so"),
    (r"transfer to campaign_provisioner and explain", "reply and explain"),
    (r"[Tt]ransfer to (\w+_agent)", lambda m: f"call the {m.group(1)} tool"),
    (r"do NOT call the (\w+_agent) tool", r"do NOT call \1"),
]

_REQUEST_RULE = (" When you call a specialist tool, write everything it needs in its request: request_id, "
                 "campaign_id, each item as its catalog SKU (from the inventory agent's report) with the quantity and shortfall, and any totals or amounts.")


def adapt(text: str) -> str:
    """Rewrite hand-off wording for the active mode (unchanged in transfer mode)."""
    if not TOOL_MODE:
        return text
    for pattern, repl in _TO_TOOL:
        text = re.sub(pattern, repl, text)
    return text.replace("call the call the", "call the")


def root_wiring(inventory, procurement, budget):
    """(tools to add, sub_agents) for the root agent."""
    if not TOOL_MODE:
        return [], [inventory, procurement, budget]
    from google.adk.tools.agent_tool import AgentTool
    return [AgentTool(agent=a) for a in (inventory, procurement, budget)], []


def root_note() -> str:
    return _REQUEST_RULE if TOOL_MODE else ""
