"""What the user reads: simple wording, tables and the story after the orders (all built from stored data)."""
from conftest import FakeExecutor
from launchkit_provisioner import decision_flow, execution, presentation
from launchkit_provisioner.tools import brief_tools, orchestration_tools, sourcing_tools


def _approved(repo, aurora, option="2"):
    repo.t["approvers"] = [{"approver_role": r, "email": f"{r[:2].lower()}@example.com", "active": True}
                           for r in ("VP Product Marketing", "CMO", "Launch Team")]
    ex = FakeExecutor()
    decision_flow.authorize(repo, ex, aurora, option, "because")
    d = repo.get_decision_for_request(aurora)
    repo.decide(d["decision_id"], "APPROVED", "Application Integration approval", "ok")
    return ex


def test_greeting_card_says_what_it_does_and_what_it_needs():
    card = orchestration_tools.show_capabilities()["display_markdown"]
    assert "I can" in card and "Let's close on 3 things" in card and "Shopping list" in card or "shopping list" in card
    assert "What is the event?" in card and "single item" in card.lower() and "whole event" in card
    assert "Compare **vendors**" in card and "what you may be missing" in card


def test_bom_lists_every_item_with_totals(repo, aurora):
    md = presentation.bom_markdown(repo, aurora)
    assert "Bill of Materials" in md and "VIP guest welcome kit" in md and "(150 kits)" in md
    assert "| Event hoodie | 1 | **150** | L 60 · M 45 · S 20 · XL 25 |" in md
    assert "1,210 items in total" in md


def test_build_requirements_returns_the_bom_for_the_chat(repo):
    rid = brief_tools.register_launch_request("LAUNCH-SPRING", "x")["request_id"]
    out = brief_tools.build_requirements(rid, [brief_tools.BundleRequest(bundle_type="SALES_PACK", quantity=30)])
    assert "Leather sales folder" in out["bom_markdown"] and "Product brochure" in out["bom_markdown"]


def test_vendor_report_shows_vendors_compared_and_why_the_faster_one_was_used(repo, aurora):
    md = presentation.vendor_report(repo, aurora)
    assert "7 vendors" in md and "24 price offers" in md
    assert "DisplayCo" in md and "RapidDisplay" in md and "✅ Chosen" in md
    assert "even though DisplayCo is cheaper" in md
    assert "Ready by" in md and "🔴" not in md


def test_build_scenarios_returns_the_vendor_report_and_a_table_card(repo):
    rid = brief_tools.register_launch_request("LAUNCH-SPRING", "x")["request_id"]
    brief_tools.build_requirements(rid, [brief_tools.BundleRequest(bundle_type="VENUE_DISPLAY", quantity=10)])
    out = sourcing_tools.build_scenarios(rid)
    assert "What vendors can do" in out["vendor_report"] and "What we already have in stock" in out["stock_report"]
    assert "| 💰 Total price |" in out["decision_card"] and "Does this plan feel good?" in out["decision_card"]
    assert "Buy everything new" in out["decision_card"] and "Who has to say OK" in out["decision_card"]


def test_options_have_friendly_names(repo, aurora):
    names = [s["option_name"] for s in repo.get_scenarios(aurora)]
    assert names == ["Buy everything new", "Use our stock first, buy the rest", "Go green with eco-friendly materials"]


def test_approval_rules_show_all_three_levels(repo):
    md = orchestration_tools.get_approval_rules()["display_markdown"]
    assert "Nobody, it is automatic" in md and "**VP Product Marketing**" in md and "**CMO**" in md


def test_sign_off_message_marks_the_level_of_this_order(repo, aurora):
    repo.t["approvers"] = [{"approver_role": "VP Product Marketing", "email": "vp@example.com", "active": True}]
    out = decision_flow.authorize(repo, FakeExecutor(), aurora, "2", "x")
    md = out["display_markdown"]
    assert "👈 **this order**" in md and "vp@example.com" in md and "Nothing has been bought yet" in md
    assert md.index("**VP Product Marketing** | 👈") > 0


def test_order_summary_explains_vendors_and_why_so_many_orders(repo, aurora):
    ex = _approved(repo, aurora)
    out = execution.execute_plan(repo, ex, aurora)
    md = out["display_markdown"]
    assert "Done! All your orders are placed" in md and "What we did, in 4 lines" in md
    assert "27 purchase orders + 7 warehouse moves" in md and "Why so many orders" in md
    assert "RapidDisplay" in md and "a cheaper vendor was too slow" in md
    assert "is $5,000.00 to $50,000.00, so **VP Product Marketing** approved it" in md and "🟩" in md


def test_launch_team_update_is_a_formatted_html_email(repo, aurora):
    ex = _approved(repo, aurora)
    execution.execute_plan(repo, ex, aurora)
    update = [i for t, i in ex.calls if t.endswith("send_launch_update")]
    assert update and update[0]["email_body"].startswith("<div") and "<table" in update[0]["email_body"]
    assert "Orders placed for the Spring Product Launch Event" in update[0]["email_subject"]


def test_status_and_board_are_tables(repo, aurora):
    _approved(repo, aurora)
    md = decision_flow.status(repo, aurora, executor=FakeExecutor())["display_markdown"]
    assert "Status of" in md and "| Status |" in md
    board = orchestration_tools.get_launch_overview()["display_markdown"]
    assert "Event status board" in board and "Stock we already own" in board
    assert "What happened" in orchestration_tools.get_audit_trail()["display_markdown"]


def test_stock_report_lists_what_we_own_and_what_the_best_plan_uses(repo, aurora):
    md = presentation.stock_report(repo, aurora)
    assert "What we already have in stock" in md and "| Leather sales folder | Dallas Marketing Depot | 120 | 120 |" in md


def test_stock_report_says_so_when_we_own_nothing(repo):
    rid = brief_tools.register_launch_request("LAUNCH-SPRING", "x")["request_id"]
    brief_tools.build_requirements(rid, [brief_tools.BundleRequest(bundle_type="VENUE_DISPLAY", quantity=2)])
    sourcing_tools.build_scenarios(rid)
    assert "none of these items" in presentation.stock_report(repo, rid)


def test_checklist_closes_one_thing_at_a_time():
    c0 = orchestration_tools.show_checklist()["display_markdown"]
    assert c0.count("⬜") == 3 and "What is the event?" in c0
    c1 = orchestration_tools.show_checklist("Spring Product Launch Event")["display_markdown"]
    assert c1.count("✅") == 1 and "By what date" in c1
    c2 = orchestration_tools.show_checklist("Spring Product Launch Event", "6 Nov 2026")["display_markdown"]
    assert "What do you need, and how many?" in c2 and "whole event" in c2
    c3 = orchestration_tools.show_checklist("E", "d", "150 kits")["display_markdown"]
    assert c3.count("✅") == 4 and "All 3 closed" in c3


def test_the_plan_starts_with_an_in_short_box(repo):
    rid = brief_tools.register_launch_request("LAUNCH-SPRING", "x")["request_id"]
    brief_tools.build_requirements(rid, [brief_tools.BundleRequest(bundle_type="SALES_PACK", quantity=300),
                                         brief_tools.BundleRequest(bundle_type="GUEST_KIT", quantity=150),
                                         brief_tools.BundleRequest(bundle_type="VENUE_DISPLAY", quantity=10)])
    box = sourcing_tools.build_scenarios(rid)["tldr"]
    assert "In short" in box and "Best choice: Option 2" in box and "$37,399.50" in box and "VP Product Marketing" in box
    assert "stock covers" in box and "🟩" in box


def test_bar_is_a_tiny_picture():
    assert presentation.bar(50) == "🟩🟩🟩🟩🟩⬜⬜⬜⬜⬜" and presentation.bar(0) == "⬜" * 10 and presentation.bar(100) == "🟩" * 10
