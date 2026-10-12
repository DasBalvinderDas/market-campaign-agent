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


def test_greeting_card_invites_a_natural_conversation():
    card = orchestration_tools.show_capabilities()["display_markdown"]
    assert "Campaign Procurement Assistant" in card and "Just talk to me" in card and "300 people on 31st Oct" in card
    assert "where we can deliver" in card and "best date" in card and "Compare **vendors**" in card
    assert "how many people, and on which date?" in card


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
    assert "12 vendors" in md and "38 price offers" in md
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


def _iso(days):
    from datetime import date, timedelta
    return (date.today() + timedelta(days=days)).isoformat()


def test_nothing_known_asks_to_tell_about_the_campaign():
    c = orchestration_tools.show_checklist()["display_markdown"]
    assert "Tell me about your campaign" in c and "Just talk to me" in c


def test_a_natural_first_message_is_enough_and_the_next_question_is_where():
    out = orchestration_tools.show_checklist("campaign", "", 300, "31st Oct")
    md = out["display_markdown"]
    assert "300" in md and out["date_iso"].endswith("-10-31")
    assert md.count("✅") == 2 and "Where is your campaign?" in md
    assert "where can we deliver?" in md and "**USA**" in md and "**Canada**" in md and "**London**" in md and "**Singapore**" in md
    assert "UK and European vendors" in md and "Dallas Marketing Depot" in md


def test_questions_come_in_order_people_date_place_name_then_picks():
    assert "How many people" in orchestration_tools.show_checklist("campaign")["display_markdown"]
    assert "On which date" in orchestration_tools.show_checklist("campaign", "", 300)["display_markdown"]
    assert "Where is your campaign?" in orchestration_tools.show_checklist("campaign", "", 300, _iso(25))["display_markdown"]
    named = orchestration_tools.show_checklist("campaign", "", 300, _iso(25), "London")
    assert named["region"] == "EMEA" and "What would you like to call your campaign?" in named["display_markdown"]
    offer = orchestration_tools.show_checklist("campaign", "Summer Sale", 300, _iso(25), "London")["display_markdown"]
    assert "What would you like from our offer?" in offer and "What we can offer you" in offer


def test_canada_is_served_from_the_us_region():
    out = orchestration_tools.show_checklist("campaign", "", 100, _iso(25), "Toronto, Canada")
    assert out["region"] == "US" and out["venue_name"] == "Canada"


def test_an_unknown_place_is_asked_again_without_losing_what_we_know():
    md = orchestration_tools.show_checklist("campaign", "", 100, _iso(25), "Mars")["display_markdown"]
    assert "I do not serve 'Mars' yet" in md and "**Singapore**" in md and md.count("✅") == 2


def test_a_date_in_the_past_or_unreadable_is_explained():
    assert "not in the future" in orchestration_tools.show_checklist("campaign", "", 100, "2020-01-01")["display_markdown"]
    assert "could not read the date" in orchestration_tools.show_checklist("campaign", "", 100, "sometime soon")["display_markdown"]


def test_items_only_needs_a_date_a_place_and_the_pick_but_no_name_or_headcount():
    md = orchestration_tools.show_checklist("items", "", 0, _iso(25), "USA")["display_markdown"]
    assert "How many people" not in md and "Campaign name" not in md
    assert "What would you like from our offer?" in md and "Single items" in md and md.index("Single items") < md.index("Ready-made packs")


def test_the_offer_shows_a_suggested_plan_for_the_headcount():
    out = orchestration_tools.show_checklist("campaign", "Summer Sale", 300, _iso(25), "USA")
    md = out["display_markdown"]
    assert "💡 For 300 people" in md and "use the suggested plan" in md
    assert out["suggested"]["bundles"] == [{"bundle_type": "GUEST_KIT", "quantity": 30, "region": "US"},
                                           {"bundle_type": "SALES_PACK", "quantity": 30, "region": "US"},
                                           {"bundle_type": "VENUE_DISPLAY", "quantity": 3, "region": "US"}]
    assert {"item": "Name badge with lanyard", "quantity": 300, "region": "US"} in out["suggested"]["items"]
    assert {"item": "Roll-up banner", "quantity": 6, "region": "US"} in out["suggested"]["items"]


def test_the_offer_shows_stock_in_every_warehouse_because_it_can_be_moved():
    md = orchestration_tools.show_checklist("campaign", "S", 100, _iso(25), "Singapore")["display_markdown"]
    assert "| Leather sales folder | 120 Dallas |" in md and "| Steel water bottle | 150 Dallas, 80 Singapore |" in md


def test_the_offer_prices_follow_the_date():
    near = orchestration_tools.show_checklist("campaign", "S", 100, _iso(10), "USA")["display_markdown"]
    far = orchestration_tools.show_checklist("campaign", "S", 100, _iso(50), "USA")["display_markdown"]
    std = orchestration_tools.show_checklist("campaign", "S", 100, _iso(25), "USA")["display_markdown"]
    assert "rush: 12% extra" in near and "$9.52" in near            # 8.5 * 1.12 (steel water bottle)
    assert "early bird: 8% off" in far and "$7.82" in far            # 8.5 * 0.92
    assert "standard price" in std and "$8.50" in std


def test_the_offer_marks_what_cannot_make_the_date():
    md = orchestration_tools.show_checklist("items", "", 0, _iso(3), "USA")["display_markdown"]
    assert "🔴 too late" in md


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


def test_the_name_question_comes_with_ideas_built_from_the_season_place_and_size():
    out = orchestration_tools.show_checklist("campaign", "", 300, _iso(25), "Singapore")
    names = out["name_suggestions"]
    assert len(names) == 4 and any("Singapore" in n for n in names) and any("300-Guest" in n for n in names)
    md = out["display_markdown"]
    assert "Pick one of these, or type your own" in md and "| 1 | **" + names[0] + "** |" in md and "create the campaign right away" in md


def test_name_ideas_are_the_same_every_time_and_follow_the_season_and_size():
    from datetime import date
    a = presentation.name_suggestions(300, date(2026, 10, 31), "London")
    assert a == presentation.name_suggestions(300, date(2026, 10, 31), "London")
    assert a == ["Autumn Summit 2026", "London Autumn Showcase", "October London Launch", "The 300-Guest Autumn Celebration"]
    assert presentation.name_suggestions(20, date(2027, 1, 5), "USA")[0] == "Winter Meetup 2027"
    assert presentation.name_suggestions(2000, date(2027, 7, 1), "USA")[0] == "Summer Festival 2027"
    assert presentation.name_suggestions(0, date(2027, 4, 1))[1] == "Spring Showcase 2027"


def test_no_name_ideas_once_a_name_is_given():
    out = orchestration_tools.show_checklist("campaign", "Summer Sale", 300, _iso(25), "USA")
    assert "name_suggestions" not in out and "What we can offer you" in out["display_markdown"]
