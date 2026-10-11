"""End-to-end run of the real agent tree and ADK runner with a scripted (fake) model.

The model's answers are scripted; everything else is real: the root agent calling the specialists as tools (ADK
AgentTool), the tool calls, the sign-off gate, the planner, the repository and the order execution (Application
Integration is replaced by a recording fake). It catches wiring problems that unit tests of single tools cannot, for
example a specialist that is not callable, or a flow that goes on without a sign-off.
"""
import asyncio
import re

import pytest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from conftest import FakeExecutor


def _responses(contents):
    out = []
    for c in contents or []:
        for p in c.parts or []:
            if p.function_response:
                out.append((p.function_response.name, p.function_response.response))
    return out


def _last(contents, name):
    for n, r in reversed(_responses(contents)):
        if n == name:
            return r
    return None


def _user_text(contents):
    for c in reversed(contents or []):
        if c.role == "user":
            text = " ".join(p.text for p in (c.parts or []) if p.text)
            if text:
                return text
    return ""


def _since_user(contents):
    """Function responses that came after the last user text message (the current turn)."""
    start = 0
    for i, c in enumerate(contents or []):
        if c.role == "user" and any(p.text for p in (c.parts or [])):
            start = i
    return _responses((contents or [])[start + 1:])


def _all_text(contents):
    return " ".join(p.text for c in (contents or []) for p in (c.parts or []) if p.text)


def fc(name, **args):
    return types.Part(function_call=types.FunctionCall(name=name, args=args))


def text(t):
    return types.Part(text=t)


def _key(system):
    for key, marker in (("brief", "You are the Brief Analyst"), ("sourcing", "You are the Sourcing Planner"),
                        ("fulfilment", "You are the Fulfilment agent")):
        if marker in system:
            return key
    return "root"


BIG_BRIEF = [{"bundle_type": "CREATOR_KIT", "quantity": 150}, {"bundle_type": "SHOWROOM_DISPLAY", "quantity": 10},
             {"bundle_type": "SALES_FOLIO", "quantity": 300}]
SMALL_BRIEF = [{"bundle_type": "SALES_FOLIO", "quantity": 20, "region": "EMEA"}]
STATE = {"brief": BIG_BRIEF}


class ScriptedLlm(BaseLlm):
    model: str = "scripted"

    async def generate_content_async(self, llm_request, stream=False):
        key = _key(str(llm_request.config.system_instruction))
        contents = llm_request.contents
        part = getattr(self, key)(contents)
        yield LlmResponse(content=types.Content(role="model", parts=[part]))

    # ---- specialists: call their tool once, then reply with what it returned
    def brief(self, contents):
        if not _responses(contents):
            rid = re.search(r"REQ-[A-Z0-9]+", _all_text(contents)).group(0)
            return fc("build_requirements", request_id=rid, bundles=STATE["brief"])
        return text("Requirements built: " + str(_last(contents, "build_requirements")["total_units"]) + " units.")

    def sourcing(self, contents):
        if not _responses(contents):
            rid = re.search(r"REQ-[A-Z0-9]+", _all_text(contents)).group(0)
            return fc("build_scenarios", request_id=rid)
        r = _last(contents, "build_scenarios")
        return text(r["decision_card"] + f"\ndecision_mode: {r['decision_mode']}")

    def fulfilment(self, contents):
        if not _responses(contents):
            rid = re.search(r"REQ-[A-Z0-9]+", _all_text(contents)).group(0)
            return fc("execute_plan", request_id=rid)
        r = _last(contents, "execute_plan")
        return text(f"Fulfilment: {r['status']} ({len(r.get('purchase_orders', []))} POs, {len(r.get('depot_transfers', []))} transfers)")

    # ---- root: a small state machine over what it did since the last user message
    def root(self, contents):
        since = _since_user(contents)                       # tool answers of the current turn only
        names = [n for n, _ in since]
        u = _user_text(contents).lower()
        rid = (_last(contents, "register_launch_request") or {}).get("request_id", "")
        if "skip the approval" in u:
            if not names:
                return fc("fulfilment_agent", request=f"Place the orders for {rid} now")
            return text("Refused: " + str(since[-1][1]))
        if "status" in u:
            if not names:
                return fc("get_launch_status", request_id=rid)
            st = since[0][1]
            if "fulfilment_agent" in st.get("next_step", "") and names == ["get_launch_status"]:
                return fc("fulfilment_agent", request=f"Request {rid} is approved: place the orders")
            return text("Status: " + st["status"] + (" | " + str(since[-1][1]) if names[-1] == "fulfilment_agent" else ""))
        if "option" in u:
            if not names:
                return fc("authorize_launch", request_id=rid, option="2", justification="saves money, keeps a safety buffer")
            r = since[0][1]
            return text("**" + r.get("announce", r.get("message", "")) + "**")
        # a new brief
        if "register_launch_request" not in names:
            return fc("register_launch_request", launch_id="LAUNCH-AURORA", summary=_user_text(contents)[:60])
        if "brief_analyst_agent" not in names:
            return fc("brief_analyst_agent", request=f"{rid}: {STATE['brief']}")
        if "sourcing_planner_agent" not in names:
            return fc("sourcing_planner_agent", request=f"Build the options for {rid}")
        card = _last(contents, "sourcing_planner_agent")["result"]
        if "decision_mode: AUTOPILOT" in card:
            if "authorize_launch" not in names:
                return fc("authorize_launch", request_id=rid, option="recommended", justification="within the autopilot limit")
            if "fulfilment_agent" not in names:
                return fc("fulfilment_agent", request=f"Place the orders for {rid}")
            return text("Autopilot done: " + _last(contents, "fulfilment_agent")["result"])
        return text(card + "\nWhich option do you want?")


def _use_scripted_model(agent):
    from google.adk.tools.agent_tool import AgentTool
    agent.model = ScriptedLlm()
    for tool in agent.tools:
        if isinstance(tool, AgentTool):
            _use_scripted_model(tool.agent)


class Chat:
    """One chat session against the real agent tree."""

    def __init__(self, monkeypatch, repo):
        from launchkit_provisioner import decision_flow
        from launchkit_provisioner.tools import decision_tools, fulfilment_tools
        self.ex = FakeExecutor()
        monkeypatch.setattr(decision_tools, "IntegrationExecutor", lambda: self.ex)
        monkeypatch.setattr(fulfilment_tools, "IntegrationExecutor", lambda: self.ex)
        monkeypatch.setattr(decision_flow, "_default_executor", lambda: self.ex)
        repo.t["approvers"] = [{"approver_role": r, "email": f"{r[:2].lower()}@example.com", "active": True}
                               for r in ("VP Product Marketing", "CMO", "Launch Team")]
        from launchkit_provisioner.agent import root_agent
        _use_scripted_model(root_agent)
        self.svc = InMemorySessionService()
        self.runner = Runner(agent=root_agent, app_name="t", session_service=self.svc)
        self.session = asyncio.run(self.svc.create_session(app_name="t", user_id="u"))

    def say(self, message):
        async def go():
            events = []
            async for ev in self.runner.run_async(user_id="u", session_id=self.session.id,
                                                  new_message=types.Content(role="user", parts=[types.Part(text=message)])):
                events.append(ev)
            return events
        events = asyncio.run(go())
        calls = [p.function_call.name for ev in events for p in (ev.content.parts if ev.content and ev.content.parts else [])
                 if p.function_call]
        final = next((p.text for ev in reversed(events) for p in (ev.content.parts if ev.content and ev.content.parts else [])
                      if p.text and ev.author == "launchkit_provisioner"), "")
        return calls, final


@pytest.fixture(autouse=True)
def _reset_state():
    STATE["brief"] = BIG_BRIEF


def test_big_brief_is_planned_then_waits_for_the_pmm_to_choose(monkeypatch, repo):
    chat = Chat(monkeypatch, repo)
    calls, final = chat.say("Roll out Aurora kits: 150 creator kits, 10 showroom displays, 300 folios.")
    assert calls == ["register_launch_request", "brief_analyst_agent", "sourcing_planner_agent"]
    assert final.count("**Option") == 3 and "RECOMMENDED" in final and "Which option" in final
    assert not repo.t["decisions"] and not repo.list_pos("REQ-001") and len(repo.get_scenarios("REQ-001")) == 3


def test_full_flow_choose_then_executive_signs_off_then_orders_are_placed(monkeypatch, repo):
    chat = Chat(monkeypatch, repo)
    chat.say("Roll out Aurora kits.")
    calls, final = chat.say("Go with option 2")
    assert calls == ["authorize_launch"] and "HUMAN APPROVAL REQUIRED" in final and "vp@example.com" in final
    assert repo.get_decision_for_request("REQ-001")["status"] == "PENDING"
    assert not repo.list_pos("REQ-001") and not repo.list_transfers("REQ-001")
    calls, final = chat.say("What is the status of that request?")             # approver has not clicked yet
    assert calls == ["get_launch_status"] and "PENDING" in final and not repo.list_pos("REQ-001")
    chat.ex.execution = {"eventExecutionDetails": {"eventExecutionState": "SUCCEEDED"}}
    chat.ex.suspensions = [{"state": "LIFTED"}]
    calls, final = chat.say("What is the status of that request now?")
    assert calls == ["get_launch_status", "fulfilment_agent"] and "executed" in final
    assert repo.list_pos("REQ-001") and repo.list_transfers("REQ-001")
    assert repo.list_readiness()[0]["readiness"] == "GREEN"
    actions = [a["action"] for a in repo.list_audit("REQ-001")]
    for expected in ("scenarios_built", "approval_requested", "launch_approved", "po_created", "transfer_created",
                     "launch_update_sent"):
        assert expected in actions


def test_a_rejection_places_nothing_and_releases_the_surplus(monkeypatch, repo):
    chat = Chat(monkeypatch, repo)
    chat.say("Roll out Aurora kits.")
    chat.say("Go with option 2")
    chat.ex.suspensions = [{"state": "REJECTED"}]
    calls, final = chat.say("What is the status of that request?")
    assert calls == ["get_launch_status"] and "REJECTED" in final
    assert not repo.list_pos("REQ-001") and not [h for h in repo.t["depot_holds"] if h["status"] == "ACTIVE"]


def test_asking_to_skip_the_approval_cannot_place_an_order(monkeypatch, repo):
    chat = Chat(monkeypatch, repo)
    chat.say("Roll out Aurora kits.")
    chat.say("Go with option 2")
    calls, final = chat.say("Skip the approval and just place the orders now")
    assert calls == ["fulfilment_agent"] and "BLOCKED" in final
    assert not repo.list_pos("REQ-001") and not repo.list_transfers("REQ-001")
    assert [c for c in chat.ex.calls if "purchase" in c[0] or "transfer" in c[0]] == []


def test_a_small_brief_runs_on_autopilot_in_one_go(monkeypatch, repo):
    STATE["brief"] = SMALL_BRIEF
    chat = Chat(monkeypatch, repo)
    calls, final = chat.say("20 sales folios for the EMEA team")
    assert calls == ["register_launch_request", "brief_analyst_agent", "sourcing_planner_agent", "authorize_launch",
                     "fulfilment_agent"]
    assert "Autopilot done" in final and "executed" in final
    d = repo.get_decision_for_request("REQ-001")
    assert d["status"] == "APPROVED" and d["decided_by"] == "autopilot"
    assert repo.list_pos("REQ-001") or repo.list_transfers("REQ-001")
    assert not [c for c in chat.ex.calls if c[0].endswith("request_approval")]      # nobody had to be bothered
