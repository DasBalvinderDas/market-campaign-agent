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


def test_the_plan_starts_with_two_lines_then_the_full_tables_and_the_carbon_is_highlighted(repo, aurora):
    out = sourcing_tools.build_scenarios(aurora)
    md = out["display_markdown"]
    assert md.startswith("### 🎯 Step 1: Your 3 choices")
    order = [md.index(x) for x in ("Step 1:", "Step 2:", "Step 3:", "Step 4:", "Step 5:", "Does this plan feel good?")]
    assert order == sorted(order)                                    # choices, stock, vendors, our pick, dates, the question last
    first = md.split("Step 4: Our pick, in short\n")[1].split("\n\n")[0]
    assert first.count("\n") == 1                                  # the summary is exactly two lines
    assert "🌱 **CO₂ (making + shipping):" in first and "worked out" not in first and "biodegradable" not in first
    assert "Choose option" in first
    for part in ("What we already have in stock", "Vendors we compared", "Your 3 choices", "Could another date save you money?"):
        assert part in md
    assert "Bill of Materials" not in md and "Catalog" not in md      # the catalog is never in the text
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
    assert out["display_markdown"].split("\n\n")[0].count("\n") == 1
    assert "📎 Order pack PDF attached." in out["display_markdown"]


def test_a_date_without_a_year_is_the_current_year():
    md = orchestration_tools.checklist("campaign", "X", 0, "31st Oct", "New York, USA")
    assert md["date_iso"] == f"{date.today().year}-10-31" and md["region"] == "US"


def test_the_city_is_kept_with_the_country():
    out = orchestration_tools.checklist("campaign", "X", 0, "2099-01-05", "New York, USA")
    assert out["place"] == "New York, USA" and out["venue_name"] == "USA" and "📍 New York, USA" in out["display_markdown"]
    assert orchestration_tools.checklist("campaign", "X", 0, "2099-01-05", "USA")["place"] == "USA"


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


def test_the_checklist_creates_the_campaign_and_attaches_the_catalog_once_name_date_and_place_are_known(repo):
    ctx = _Ctx()
    when = date.today().replace(year=date.today().year + 1).isoformat()
    part = asyncio.run(orchestration_tools.show_checklist("campaign", "Aether Launch", 0, when, "", tool_context=ctx))
    assert "launch_id" not in part and not ctx.saved                         # the place is missing: only a question
    out = asyncio.run(orchestration_tools.show_checklist("campaign", "Aether Launch", 0, when, "Javits Center, New York, USA",
                                                         tool_context=ctx))
    md = out["display_markdown"]
    _shape(md)
    assert out["launch_id"] == "EVT-AETHER-LAUNCH" and "catalog.pdf" in ctx.saved
    assert "Javits Center, New York, USA" in md and "What do you need?" in md and out["region"] == "US"
    items = asyncio.run(orchestration_tools.show_checklist("items", "", 0, when, "USA", tool_context=_Ctx()))
    assert "launch_id" not in items                                          # items only: no campaign is made


def test_the_catalog_is_sent_once_per_chat_even_if_the_checklist_is_called_again(repo):
    ctx = _Ctx()
    ctx.state = {}
    when = date.today().replace(year=date.today().year + 1).isoformat()
    args = ("campaign", "Again Launch", 0, when, "London, UK")
    asyncio.run(orchestration_tools.show_checklist(*args, tool_context=ctx))
    ctx.saved.clear()
    out = asyncio.run(orchestration_tools.show_checklist(*args, "150 bottles", tool_context=ctx))
    assert not ctx.saved and "launch_id" in out and "attached as a PDF" in out["display_markdown"]


def test_the_order_pack_follows_the_orders_and_purchase_order_numbers_are_bold(repo, aurora):
    from conftest import FakeExecutor
    from launchkit_provisioner import decision_flow, execution
    from launchkit_provisioner.workflow.callbacks import attach_pack_after_orders

    repo.t["approvers"] = [{"approver_role": r, "email": f"{r[:2].lower()}@example.com", "active": True}
                           for r in ("VP Product Marketing", "CMO", "Launch Team")]
    ex = FakeExecutor()
    decision_flow.authorize(repo, ex, aurora, "2", "because")
    repo.decide(repo.get_decision_for_request(aurora)["decision_id"], "APPROVED", "Application Integration approval", "ok")
    out = execution.execute_plan(repo, ex, aurora)
    md = out["display_markdown"]
    for po in repo.list_pos(aurora):
        assert f"**{po['po_number']}**" in md
    assert f"Request **{aurora}**" in md and "Move numbers:" in md

    class _Tool:
        name = "fulfilment_agent"

    ctx = _Ctx()
    asyncio.run(attach_pack_after_orders(_Tool(), {"request": f"Request {aurora} is approved"}, ctx, {"result": "x"}))
    assert any("purchase-orders" in k for k in ctx.saved)
    ctx2 = _Ctx()
    asyncio.run(attach_pack_after_orders(type("T", (), {"name": "other"})(), {"request": aurora}, ctx2, {}))
    assert not ctx2.saved


def test_shipping_is_added_to_every_vendor_line_by_weight_and_distance(repo):
    from launchkit_provisioner import planner
    ctx = type("C", (), {"rules": repo.get_planning_rules()})()
    near = planner._ship_carbon(ctx, 10, 2.0, "US", "US")
    far = planner._ship_carbon(ctx, 10, 2.0, "US", "APAC")
    assert near == 10 * 2.0 * 1.5 * 0.1 and far == 10 * 2.0 * 12 * 0.1 and far > near
    assert planner._ship_carbon(ctx, 10, 2.0, "US", "MARS") == 0
