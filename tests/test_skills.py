"""The step-by-step instructions live in skills; check they load, are listed in the prompt, and name only real tools."""
import asyncio
import re
from pathlib import Path

from google.adk.skills import load_skills_from_dir

from launchkit_provisioner import agent

SKILLS_DIR = Path(agent.__file__).parent / "skills"


def _tool_names():
    names = set()
    for t in agent.root_agent.tools:
        if hasattr(t, "__name__"):
            names.add(t.__name__)
        elif hasattr(t, "name"):
            names.add(t.name)
    return names


def test_every_skill_loads_and_is_named_in_the_prompt():
    skills = load_skills_from_dir(SKILLS_DIR)
    assert {s.name for s in skills} == {"collecting-details", "existing-campaigns", "plan-and-advice", "approval-and-orders", "quick-answers"}
    for s in skills:
        assert s.frontmatter.description and s.instructions.strip()
        assert s.name in agent.INSTRUCTION, f"{s.name} is not in the root prompt"


def test_the_agent_offers_only_load_skill():
    tools = [t for t in agent.root_agent.tools if type(t).__name__ == "SkillToolset"]
    assert len(tools) == 1
    assert [t.name for t in asyncio.run(tools[0].get_tools())] == ["load_skill"]


def test_skills_mention_only_tools_the_agent_has():
    known = _tool_names()
    wanted = {"show_checklist", "create_campaign", "open_campaign", "register_launch_request", "brief_analyst_agent",
              "sourcing_planner_agent", "fulfilment_agent", "authorize_launch", "get_launch_status", "get_order_pack",
              "get_launch_overview", "get_audit_trail", "get_approval_rules", "get_vendor_report"}
    text = " ".join(p.read_text() for p in SKILLS_DIR.glob("*/SKILL.md"))
    for name in set(re.findall(r"\b([a-z]+(?:_[a-z]+)+)\b", text)) & (wanted | {"authorize_launch"}):
        assert name in known, name
    assert wanted <= known


def test_the_hard_rules_stay_in_the_prompt_not_only_in_skills():
    assert "never place orders without an approved sign-off" in agent.INSTRUCTION
    assert "only you call" in agent.INSTRUCTION and "authorize_launch" in agent.INSTRUCTION


def test_a_skill_loads_in_a_real_run_and_gives_its_instructions(monkeypatch, repo):
    """The real runner and the real skill tool, with a scripted model that loads a skill and then answers."""
    import asyncio as _a

    from google.adk.models.base_llm import BaseLlm
    from google.adk.models.llm_response import LlmResponse
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    seen = {}

    class Llm(BaseLlm):
        model: str = "scripted"

        async def generate_content_async(self, llm_request, stream=False):
            system = str(llm_request.config.system_instruction)
            seen["catalog"] = "<available_skills>" in system and "approval-and-orders" in system
            resp = [p.function_response for c in llm_request.contents for p in (c.parts or []) if p.function_response]
            if not resp:
                part = types.Part(function_call=types.FunctionCall(name="load_skill", args={"skill_name": "approval-and-orders"}))
            else:
                seen["loaded"] = str(resp[-1].response)
                part = types.Part(text="done")
            yield LlmResponse(content=types.Content(role="model", parts=[part]))

    agent.root_agent.model = Llm()
    svc = InMemorySessionService()
    runner = Runner(agent=agent.root_agent, app_name="t", session_service=svc)
    session = _a.run(svc.create_session(app_name="t", user_id="u"))

    async def go():
        return [e async for e in runner.run_async(user_id="u", session_id=session.id,
                                                  new_message=types.Content(role="user", parts=[types.Part(text="Choose option 2")]))]
    _a.run(go())
    assert seen["catalog"] and "authorize_launch" in seen["loaded"] and "get_order_pack" in seen["loaded"]


def test_the_prompt_forbids_naming_who_gets_the_emails():
    assert "Never write an email address" in agent.INSTRUCTION


def test_without_skill_support_the_same_text_goes_into_the_prompt():
    from launchkit_provisioner.skill_loader import skills_as_text
    text = skills_as_text(SKILLS_DIR)
    for name in ("collecting-details", "existing-campaigns", "plan-and-advice", "approval-and-orders", "quick-answers"):
        assert f"=== {name}:" in text
    assert "authorize_launch" in text and "open_campaign" in text


def test_the_prompt_forbids_planning_before_the_date_and_place_are_known():
    assert "Never build a shopping list or a plan until the date, the place and" in agent.INSTRUCTION
    assert "Never say \"technical issue\"" in agent.INSTRUCTION
