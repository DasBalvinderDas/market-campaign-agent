"""End-to-end run of the real agent tree and ADK runner with a scripted (fake) model.

The model's answers are scripted; everything else is real: the root agent calling the specialists as tools (ADK AgentTool), tool calls, the
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


_STATE = {"calls": {}, "request_id": "", "email": False}


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
        back = types.Part(text="Done, here is my report.")  # a specialist ends by replying to the root agent
        if key == "Inventory Agent":
            return [fc("find_sku", description="booth LED video wall"),
                    fc("check_inventory", sku="BOOTH-LEDWALL", quantity_needed=1),
                    fc("reserve_inventory", request_id=req, sku="BOOTH-LEDWALL", quantity=1), back][min(n, 4) - 1]
        if key == "Procurement Agent":
            plan = [fc("get_vendor_quotes", sku="BOOTH-LEDWALL", quantity=1), back,
                    fc("create_purchase_order", request_id=req, sku="BOOTH-LEDWALL", quantity=1, vendor_id="V-EXPOVISION"),
                    types.Part(text="Purchase order created.")]
            return plan[min(n, 4) - 1]
        if key == "Budget Agent":
            if _STATE["email"]:  # the orchestrator sends the approval email itself in this channel
                return [fc("check_budget", campaign_id="NEXT27-MAIN"), fc("get_approval_policy", amount=18000), back][min(n, 3) - 1]
            plan = [fc("check_budget", campaign_id="NEXT27-MAIN"), fc("get_approval_policy", amount=18000),
                    fc("notify_approver", request_id=req, campaign_id="NEXT27-MAIN", amount=18000,
                       approver_role="Marketing Director", summary="1 LED wall"), back]
            return plan[min(n, 4) - 1]
        # root orchestrator: it holds the approval gate (approve_budget)
        if n <= 5:
            return [fc("register_campaign_request", campaign_id="NEXT27-MAIN", summary="1 LED wall"),
                    fc("inventory_agent", request=f"{req}: 1 booth LED video wall"),
                    fc("procurement_agent", request=f"Quote the shortfalls of {req}"),
                    fc("budget_agent", request="NEXT27-MAIN total 18000"),
                    fc("approve_budget", request_id=req, campaign_id="NEXT27-MAIN", amount=18000,
                       justification="1 LED wall")][n - 1]
        if n == 6 and _STATE["email"]:
            return types.Part(text="Approval requested by email; the order follows automatically after the click.")
        if n == 6:
            return fc("procurement_agent", request=f"Budget approved for {req}. Create the purchase orders now.") if approved else \
                types.Part(text="Not approved, nothing was ordered.")
        return types.Part(text="All done: stock reserved, budget approved, purchase order created.")


def _use_scripted_model(agent):
    from google.adk.tools.agent_tool import AgentTool
    agent.model = ScriptedLlm()
    for tool in agent.tools:
        if isinstance(tool, AgentTool):
            _use_scripted_model(tool.agent)


async def _run(confirm: bool, expect_pause: bool = True):
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
    if not expect_pause:
        assert not pending, "email channel: the chat must not pause"
        return events
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
    assert tools.count("procurement_agent") == 2, f"flow stopped after the approval; calls were {tools}"
    assert get_repo().t["purchase_orders"], "the PO must be recorded"
    actions = [a["action"] for a in get_repo().t["audit_log"]]
    assert "approver_notified" in actions and "budget_approved" in actions and "po_created" in actions


def test_rejected_request_creates_nothing():
    from campaign_provisioner.repositories import get_repo
    events = asyncio.run(_run(confirm=False))
    assert _tool_names(events).count("procurement_agent") == 1  # quotes only, never the order
    assert not get_repo().t["purchase_orders"]
    assert "budget_approved" not in [a["action"] for a in get_repo().t["audit_log"]]


def test_email_channel_end_to_end_request_then_click(monkeypatch):
    """Chat run ends with a pending approval and an email with links; clicking Approve then creates the PO."""
    from urllib.parse import parse_qs, urlparse
    from campaign_provisioner import config
    from campaign_provisioner.repositories import get_repo
    from campaign_provisioner.tools import budget_tools
    from approval_service import main

    class Executor:
        def __init__(self):
            self.calls = []

        def execute(self, trigger_id, inputs):
            self.calls.append((trigger_id, inputs))
            return {"po_number": "PO-1", "execution_id": "e1"} if trigger_id == config.PO_TRIGGER else {"status": "NOTIFIED"}

    ex = Executor()
    monkeypatch.setattr(config, "APPROVAL_CHANNEL", "email")
    monkeypatch.setattr(config, "APPROVAL_BASE_URL", "https://approve.example")
    monkeypatch.setattr(config, "APPROVAL_LINK_SECRET", "s3cret")
    monkeypatch.setattr(budget_tools, "IntegrationExecutor", lambda: ex)
    monkeypatch.setattr(main, "_executor", lambda: ex)
    _STATE["email"] = True
    try:
        repo = get_repo()
        repo.t["approvers"] = [{"approver_role": "Marketing Director", "email": "md@example.com", "active": True}]
        events = asyncio.run(_run(confirm=True, expect_pause=False))
    finally:
        _STATE["email"] = False
    tools = _tool_names(events)
    assert "approve_budget" in tools and tools.count("procurement_agent") == 1
    assert repo.get_approval_for_request(_STATE["request_id"])["status"] == "PENDING"
    assert repo.get_budget("NEXT27-MAIN")["committed"] == 30000.0
    body = next(i["email_body"] for t, i in ex.calls if t == config.NOTIFY_TRIGGER)
    approve_url = next(l.split(": ", 1)[1].strip() for l in body.splitlines() if l.startswith("APPROVE:"))
    token = parse_qs(urlparse(approve_url).query)["t"][0]
    main.app.testing = True
    r = main.app.test_client().post("/decide", data={"t": token})
    assert r.status_code == 200 and b"PO-1" in r.data
    assert repo.get_budget("NEXT27-MAIN")["committed"] == 48000.0 and repo.list_purchase_orders(_STATE["request_id"])
