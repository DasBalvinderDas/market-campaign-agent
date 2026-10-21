"""Gemini Enterprise replies: two short paragraphs, a two-line summary, the catalog as a PDF, the carbon explained."""
import asyncio
from datetime import date

from conftest import FakeExecutor
from launchkit_provisioner import catalog_pdf, presentation
from launchkit_provisioner.tools import brief_tools, decision_tools, orchestration_tools, sourcing_tools


class _Ctx:
    def __init__(self):
        self.saved = {}

    async def save_artifact(self, name, part):
        self.saved[name] = part


def _shape(md):
    paras = md.split("\n\n")
    assert len(paras) <= 2, md
    assert paras[0].count("\n") == 1, md                       # the summary is exactly two lines


def test_the_plan_is_two_paragraphs_and_the_carbon_is_highlighted_and_explained(repo, aurora):
    out = sourcing_tools.build_scenarios(aurora)
    md = out["display_markdown"]
    first = md.split("\n\n")[0]
    assert len(md.split("\n\n")) == 2 and first.count("\n") == 1
    assert "🌱 **CO₂:" in first and "not necessarily biodegradable" in first and "times the quantity" in first
    assert "Choose option" in first and "Vendors we compared" not in md and "Bill of Materials" not in md
    assert md.count("| 🌱") <= 1 and "**🌱" in md                # the greenest figure is bold in the table
    assert "How CO₂ is worked out" in out["carbon_explanation"]


def test_the_catalog_is_a_pdf_never_text(repo):
    data = catalog_pdf.build_pdf(repo, date.today().replace(year=date.today().year + 1), "USA")
    assert data.startswith(b"%PDF-") and len(data) > 1500
    ctx = _Ctx()
    out = asyncio.run(orchestration_tools.get_catalog(tool_context=ctx))
    assert out["status"] == "ok" and "catalog.pdf" in ctx.saved and "|" not in out["display_markdown"]
    assert asyncio.run(orchestration_tools.get_catalog())["status"] == "error"       # no chat, no attachment


def test_creating_a_campaign_attaches_the_catalog_and_asks_what_you_need(repo):
    ctx = _Ctx()
    when = date.today().replace(year=date.today().year + 1).isoformat()
    out = asyncio.run(brief_tools.create_campaign("Spring Showcase", when, 0, "USA", tool_context=ctx))
    md = out["display_markdown"]
    _shape(md)
    assert "catalog.pdf" in ctx.saved and "attached as a PDF" in md and "What do you need?" in md
    assert "Leather sales folder" not in md


def test_the_order_pack_is_announced_inside_the_last_line(repo, aurora, monkeypatch):
    repo.t["approvers"] = [{"approver_role": "VP Product Marketing", "email": "vp@example.com", "active": True}]
    monkeypatch.setattr(decision_tools, "IntegrationExecutor", FakeExecutor)
    ctx = _Ctx()
    out = asyncio.run(decision_tools.authorize_launch(aurora, "2", "saves money", tool_context=ctx))
    assert out["status"] == "pending_approval" and any(k.startswith("order-pack") for k in ctx.saved)
    _shape(out["display_markdown"])
    assert "📎 Order pack PDF attached." in out["display_markdown"]


def test_a_date_without_a_year_is_the_current_year():
    md = orchestration_tools.show_checklist("campaign", "X", 0, "31st Oct", "New York, USA")
    assert md["date_iso"] == f"{date.today().year}-10-31" and md["region"] == "US"


def test_the_city_is_kept_with_the_country():
    out = orchestration_tools.show_checklist("campaign", "X", 0, "2099-01-05", "New York, USA")
    assert out["place"] == "New York, USA" and out["venue_name"] == "USA" and "📍 New York, USA" in out["display_markdown"]
    assert orchestration_tools.show_checklist("campaign", "X", 0, "2099-01-05", "USA")["place"] == "USA"


def test_the_carbon_note_explains_what_green_means():
    assert "recycled or organic" in presentation.CARBON_NOTE and "biodegradable" in presentation.CARBON_NOTE


def test_a_long_place_and_a_date_in_words_are_understood(repo):
    from launchkit_provisioner import planner
    assert planner.normalize_region(repo, "Javits Center, New York, USA") == "US"
    assert planner.normalize_region(repo, "New York, USA") == "US" and planner.normalize_region(repo, "Paris, France") == "PARIS, FRANCE"
    from datetime import timedelta
    soon = date.today() + timedelta(days=3)
    if soon.year == date.today().year:
        out = asyncio.run(brief_tools.create_campaign("Words Date", f"{soon:%B} {soon.day}", 0, "Javits Center, New York, USA"))
        assert out["status"] == "ok" and out["in_hand_by"] == soon.isoformat()


def test_the_prompt_carries_todays_date():
    from launchkit_provisioner import agent
    text = agent._instruction()
    assert date.today().isoformat() in text and "Never tell the user a date has passed" in text


def test_a_bare_greeting_gets_the_full_card_from_the_shortcut(repo):
    from google.adk.models import LlmRequest
    from google.genai import types

    from launchkit_provisioner.workflow.callbacks import greeting_shortcut

    def ask(*texts):
        req = LlmRequest(contents=[types.Content(role="user", parts=[types.Part(text=t)]) for t in texts])
        return greeting_shortcut(None, req)

    out = ask("Hi")
    card = out.content.parts[0].text
    assert "Campaign Procurement Assistant" in card and "| 📎 |" in card and "First question" in card
    assert ask("Hello!")  is not None and ask("what can you do?") is not None
    assert ask("Hi", "Hi") is None                                  # not the first message of the chat
    assert ask("Hi, create a campaign for 31 Oct") is None
