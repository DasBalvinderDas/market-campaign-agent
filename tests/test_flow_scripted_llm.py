"""End-to-end run of the real agent tree and ADK runner with a scripted (fake) model.

The model's answers are scripted; everything else is real: ADK's transfer between agents, tool calls, the
human-approval pause and resume, the guard callbacks and the repository. It catches wiring problems that unit tests
of single tools cannot (for example a callback that was never registered, or a flow that stops after the approval).
"""
import asyncio

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types


def _calls(contents):
    """(name, response) of every function response in the history, oldest first."""
    out = []
    for c in contents or []:
        for p in c.parts or []:
            if p.function_response:
                out.append((p.function_response.name, p.function_response.response))
    return out


def _names(contents):
    return [n for n, _ in _calls(contents)]


def _last_response(contents, name):
    for n, r in reversed(_calls(contents)):
        if n == name:
            return r
    return None


def fc(name, **args):
    return types.Part(function_call=types.FunctionCall(name=name, args=args))


_STATE = {"calls": {}, "request_id": ""}


def _agent_key(system: str) -> str:
    for key in ("Inventory Agent", "Procurement Agent", "Budget Agent"):
        if f"You are the {key}" in system:
            return key
    return "Root"


class ScriptedLlm(BaseLlm):
    """Answers like a well-behaved model, one scripted step per call of each agent (each agent sees only its own
    history, so the script is keyed on how often that agent has been called)."""
    model: str = "scripted"

    async def generate_content_async(self, llm_request, stream=False):
        key = _agent_key(str(llm_request.config.system_instruction))
        n = _STATE["calls"][key] = _STATE["calls"].get(key, 0) + 1
        reg = _last_response(llm_request.contents, "register_campaign_request")
        if reg:
            _STATE["request_id"] = reg.get("request_id", "")
        approved = any(r_ and r_.get("status") == "approved" for name, r_ in _calls(llm_request.contents) if name == "approve_budget")
        yield LlmResponse(content=types.Content(role="model", parts=[self.decide(key, n, _STATE["request_id"], approved)]))

    def decide(self, key, n, req, approved=False):
        back = fc("transfer_to_agent", agent_name="campaign_provisioner")
        if key == "Inventory Agent":
            return [fc("find_sku", description="booth LED video wall"),
                    fc("check_inventory", sku="BOOTH-LEDWALL", quantity_needed=1), back][min(n, 3) - 1]
        if key == "Procurement Agent":
            plan = [fc("get_vendor_quotes", sku="BOOTH-LEDWALL", quantity=1), back,
                    fc("create_purchase_order", request_id=req, sku="BOOTH-LEDWALL", quantity=1, vendor_id="V-EXPOVISION"),
                    types.Part(text="Purchase order created.")]
            return plan[min(n, 4) - 1]
        if key == "Budget Agent":
            plan = [fc("check_budget", campaign_id="NEXT27-MAIN"), fc("get_approval_policy", amount=18000),
                    fc("notify_approver", request_id=req, campaign_id="NEXT27-MAIN", amount=18000,
                       approver_role="Marketing Director", summary="1 LED wall"), back]
            return plan[min(n, 4) - 1]
        # root orchestrator: it holds the approval gate (approve_budget)
        if n <= 5:
            return [fc("register_campaign_request", campaign_id="NEXT27-MAIN", summary="1 LED wall"),
                    fc("transfer_to_agent", agent_name="inventory_agent"),
                    fc("transfer_to_agent", agent_name="procurement_agent"),
                    fc("transfer_to_agent", agent_name="budget_agent"),
                    fc("approve_budget", request_id=req, campaign_id="NEXT27-MAIN", amount=18000,
                       justification="1 LED wall")][n - 1]
        if n == 6:
            return fc("transfer_to_agent", agent_name="procurement_agent") if approved else \
                types.Part(text="Not approved, nothing was ordered.")
        return types.Part(text="All done: stock reserved, budget approved, purchase order created.")


def _use_scripted_model(agent):
    agent.model = ScriptedLlm()
    for sub in agent.sub_agents:
        _use_scripted_model(sub)


async def _run(confirm: bool):
    _STATE["calls"], _STATE["request_id"] = {}, ""
    from campaign_provisioner.agent import root_agent
    _use_scripted_model(root_agent)
    svc = InMemorySessionService()
    runner = Runner(agent=root_agent, app_name="t", session_service=svc)
    session = await svc.create_session(app_name="t", user_id="u")
    events, pending = [], []

    async def stream(message):
        async for ev in runner.run_async(user_id="u", session_id=session.id, new_message=message):
            events.append(ev)
            for p in (ev.content.parts if ev.content and ev.content.parts else []):
                if p.function_call and p.function_call.name == "adk_request_confirmation":
                    pending.append(p.function_call.id)

    await stream(types.Content(role="user", parts=[types.Part(text="NEXT27-MAIN needs 1 booth LED video wall.")]))
    assert pending, "the run must pause for a human decision"
    reply = types.Content(role="user", parts=[types.Part(function_response=types.FunctionResponse(
        id=pending[0], name="adk_request_confirmation", response={"confirmed": confirm}))])
    await stream(reply)
    return events


def _tool_names(events):
    return [p.function_call.name for ev in events for p in (ev.content.parts if ev.content and ev.content.parts else [])
            if p.function_call]


def test_confirmed_request_continues_to_a_purchase_order():
    from campaign_provisioner.repositories import get_repo
    get_repo().t["approvers"] = [{"approver_role": "Marketing Director", "email": "md@example.com", "active": True}]
    events = asyncio.run(_run(confirm=True))
    tools = _tool_names(events)
    assert "approve_budget" in tools
    assert "create_purchase_order" in tools, f"flow stopped after the approval; calls were {tools}"
    assert get_repo().t["purchase_orders"], "the PO must be recorded"
    actions = [a["action"] for a in get_repo().t["audit_log"]]
    assert "approver_notified" in actions and "budget_approved" in actions and "po_created" in actions


def test_rejected_request_creates_nothing():
    from campaign_provisioner.repositories import get_repo
    events = asyncio.run(_run(confirm=False))
    assert "create_purchase_order" not in _tool_names(events)
    assert not get_repo().t["purchase_orders"]
    assert "budget_approved" not in [a["action"] for a in get_repo().t["audit_log"]]
