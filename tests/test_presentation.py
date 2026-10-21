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


def test_greeting_card_lists_the_capabilities_then_the_first_question():
    card = orchestration_tools.show_capabilities()["display_markdown"]
    assert "Campaign Procurement Assistant" in card and "Share **our catalog**" in card and "Show the **carbon**" in card
    assert "Place all the orders" in card and "name, the date, the city and the country" in card or "name, date, city and country" in card
    assert "We already have **4 campaigns**" in card and "**London Campaign**" in card


def test_bom_is_short_one_row_per_pack_with_what_is_inside(repo, aurora):
    md = presentation.bom_markdown(repo, aurora)
    assert "Bill of Materials" in md
    assert "| **VIP guest welcome kit** | **150 kits** | Black gift box · Event hoodie (4 sizes) · Power adapter (5 plug types) · Engraved name card |" in md
    assert "| **Sales team folder pack** | **300 folders** | Leather sales folder · Product brochure |" in md
    assert "| **Venue display stand** | **10 stands** |" in md and "1,210 items** in total" in md
    assert md.count("\n|") <= 7                                    # header, separator and three packs: short for a demo


def test_build_requirements_returns_a_short_list_for_the_chat(repo):
    rid = brief_tools.register_launch_request("LAUNCH-SPRING", "x")["request_id"]
    out = brief_tools.build_requirements(rid, [brief_tools.BundleRequest(bundle_type="SALES_PACK", quantity=30)])
    md = out["display_markdown"]
    assert "Leather sales folder" in md and "Product brochure" in md and len(md.split("\n\n")) == 2 and md.split("\n\n")[0].count("\n") == 1


def test_vendor_report_shows_vendors_compared_and_why_the_faster_one_was_used(repo, aurora):
    md = presentation.vendor_report(repo, aurora)
    assert "12 vendors" in md and "38 price offers" in md and "Chosen vendor" in md and "Next best" in md
    assert "| **Venue display stand** | **DisplayCo + RapidDisplay** | $1,400.00 |" in md and "StagePro Displays $1,760.00" in md
    assert "Ready by" in md and "🔴" not in md and md.count("\n|") <= 12      # one short row per item


def test_build_scenarios_returns_the_vendor_report_and_a_table_card(repo):
    rid = brief_tools.register_launch_request("LAUNCH-SPRING", "x")["request_id"]
    brief_tools.build_requirements(rid, [brief_tools.BundleRequest(bundle_type="VENUE_DISPLAY", quantity=10)])
    out = sourcing_tools.build_scenarios(rid)
    assert "Vendors we compared" in out["vendor_report"] and "What we already have in stock" in out["stock_report"]
    assert "| 💰 Total price |" in out["decision_card"] and "Does this plan feel good?" in out["decision_card"]
    assert "Buy everything new" in out["decision_card"] and "Who has to say OK" in out["decision_card"]


def test_options_have_friendly_names(repo, aurora):
    names = [s["option_name"] for s in repo.get_scenarios(aurora)]
    assert names == ["Buy everything new", "Use our stock first, buy the rest", "Go green with eco-friendly materials"]


def test_approval_rules_show_all_three_levels(repo):
    md = orchestration_tools.get_approval_rules()["display_markdown"]
    assert "Nobody, it is automatic" in md and "**VP Product Marketing**" in md and "**CMO**" in md


def test_sign_off_message_names_the_approver_in_two_lines(repo, aurora):
    repo.t["approvers"] = [{"approver_role": "VP Product Marketing", "email": "vp@example.com", "active": True}]
    out = decision_flow.authorize(repo, FakeExecutor(), aurora, "2", "x")
    md = out["display_markdown"]
    assert "VP Product Marketing" in md and "@" not in md and "Nothing is bought until it is approved" in md and md.count("\n\n") == 1


def test_order_summary_is_two_lines_and_a_short_paragraph(repo, aurora):
    ex = _approved(repo, aurora)
    out = execution.execute_plan(repo, ex, aurora)
    md = out["display_markdown"]
    first, rest = md.split("\n\n")
    assert first.count("\n") == 1 and "All orders placed" in first and "7 purchase orders + 3 warehouse moves" in first
    assert "CO₂" in first and "Dallas: 120 Leather sales folder" in rest


def test_launch_team_update_is_a_formatted_html_email(repo, aurora):
    ex = _approved(repo, aurora)
    execution.execute_plan(repo, ex, aurora)
    update = [i for t, i in ex.calls if t.endswith("send_launch_update") and "Orders placed" in i["email_subject"]]
    assert update and update[0]["email_body"].startswith("<div") and "<table" in update[0]["email_body"]
    assert "Orders placed for the Spring Product Launch Event" in update[0]["email_subject"]


def test_status_is_two_lines_and_the_board_is_a_table(repo, aurora):
    _approved(repo, aurora)
    md = decision_flow.status(repo, aurora, executor=FakeExecutor())["display_markdown"]
    assert "Placing your orders now" in md and "orders not placed yet" in md and md.split("\n\n")[0].count("\n") == 1
    assert "REBALANCE" not in md and "Application Integration" not in md
    board = orchestration_tools.get_launch_overview()["display_markdown"]
    assert "Event status board" in board and "Stock we already own" in board
    assert "What happened" in orchestration_tools.get_audit_trail()["display_markdown"]


def test_stock_report_lists_what_we_own_and_what_the_best_plan_uses(repo, aurora):
    md = presentation.stock_report(repo, aurora)
    assert "What we already have in stock" in md and "| **Leather sales folder** | 120 | Dallas 120 | **120** |" in md


def test_stock_report_says_so_when_we_own_nothing(repo):
    rid = brief_tools.register_launch_request("LAUNCH-SPRING", "x")["request_id"]
    brief_tools.build_requirements(rid, [brief_tools.BundleRequest(bundle_type="VENUE_DISPLAY", quantity=2)])
    sourcing_tools.build_scenarios(rid)
    assert "none of these items" in presentation.stock_report(repo, rid)


def _iso(days):
    from datetime import date, timedelta
    return (date.today() + timedelta(days=days)).isoformat()


def test_nothing_known_asks_for_name_date_city_and_country():
    c = orchestration_tools.checklist()["display_markdown"]
    assert "campaign name, the date, the city and the country" in c and len(c.split("\n\n")) == 2


def test_a_natural_first_message_is_enough_and_the_next_question_is_the_name():
    out = orchestration_tools.checklist("campaign", "", 300, "31st Oct")
    md = out["display_markdown"]
    assert "300" in md and out["date_iso"].endswith("-10-31") and "campaign name" in md and "What is the campaign called?" in md
    assert "city and country" in md and "Dallas" not in md        # no vendors, warehouses or catalog as text


def test_questions_come_in_order_name_date_place_then_picks():
    assert "What is the campaign called?" in orchestration_tools.checklist("campaign")["display_markdown"]
    assert "On which date" in orchestration_tools.checklist("campaign", "Summer Sale")["display_markdown"]
    assert "Which city and country?" in orchestration_tools.checklist("campaign", "Summer Sale", 0, _iso(25))["display_markdown"]
    named = orchestration_tools.checklist("campaign", "Summer Sale", 0, _iso(25), "London, UK")
    assert named["region"] == "EMEA" and "What do you need?" in named["display_markdown"] and "catalog PDF" in named["display_markdown"]
    assert "People" not in named["display_markdown"] and "how many people" not in named["display_markdown"].lower()


def test_canada_is_served_from_the_us_region():
    out = orchestration_tools.checklist("campaign", "", 100, _iso(25), "Toronto, Canada")
    assert out["region"] == "US" and out["venue_name"] == "Canada"


def test_an_unknown_place_is_asked_again_without_losing_what_we_know():
    md = orchestration_tools.checklist("campaign", "Summer Sale", 100, _iso(25), "Mars")["display_markdown"]
    assert "I do not serve 'Mars' yet" in md and "Singapore" in md and "Summer Sale" in md


def test_a_date_in_the_past_or_unreadable_is_explained():
    assert "has already passed" in orchestration_tools.checklist("campaign", "X", 100, "2020-01-01")["display_markdown"]
    assert "could not read the date" in orchestration_tools.checklist("campaign", "X", 100, "sometime soon")["display_markdown"]


def test_items_only_needs_a_date_a_place_and_the_pick_but_no_name_or_headcount():
    md = orchestration_tools.checklist("items", "", 0, _iso(25), "USA")["display_markdown"]
    assert "campaign name" not in md and "people" not in md and "What do you need?" in md


def test_the_suggested_plan_for_the_headcount_is_still_returned_but_not_listed():
    out = orchestration_tools.checklist("campaign", "Summer Sale", 300, _iso(25), "USA")
    assert "suggested plan" not in out["display_markdown"]
    assert out["suggested"]["bundles"] == [{"bundle_type": "GUEST_KIT", "quantity": 30, "region": "US"},
                                           {"bundle_type": "SALES_PACK", "quantity": 30, "region": "US"},
                                           {"bundle_type": "VENUE_DISPLAY", "quantity": 3, "region": "US"}]


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
    out = orchestration_tools.checklist("campaign", "", 300, _iso(25), "Singapore")
    names = out["name_suggestions"]
    assert len(names) == 4 and any("Singapore" in n for n in names) and any("300-Guest" in n for n in names)
    assert names[0] in out["display_markdown"]


def test_name_ideas_are_the_same_every_time_and_follow_the_season_and_size():
    from datetime import date
    a = presentation.name_suggestions(300, date(2026, 10, 31), "London")
    assert a == presentation.name_suggestions(300, date(2026, 10, 31), "London")
    assert a == ["Autumn Summit 2026", "London Autumn Showcase", "October London Launch", "The 300-Guest Autumn Celebration"]
    assert presentation.name_suggestions(20, date(2027, 1, 5), "USA")[0] == "Winter Meetup 2027"
    assert presentation.name_suggestions(2000, date(2027, 7, 1), "USA")[0] == "Summer Festival 2027"
    assert presentation.name_suggestions(0, date(2027, 4, 1))[1] == "Spring Showcase 2027"


def test_no_name_ideas_once_a_name_is_given():
    out = orchestration_tools.checklist("campaign", "Summer Sale", 300, _iso(25), "USA")
    assert "name_suggestions" not in out and "What do you need?" in out["display_markdown"]


def test_a_date_without_a_year_is_this_year():
    from datetime import date
    md = orchestration_tools.checklist("campaign", "", 300, "31st Oct")["display_markdown"]
    assert f"31 Oct {date.today().year}" in md


def test_facts_given_without_a_mode_are_not_asked_again():
    md = orchestration_tools.checklist("", "", 300, _iso(25), "London")["display_markdown"]
    assert "Tell me the campaign name" not in md and "What is the campaign called?" in md
    assert "Tell me the campaign name" in orchestration_tools.checklist("", "", 0, "", "")["display_markdown"]


def test_picks_first_still_asks_for_the_missing_facts():
    md = orchestration_tools.checklist("", "", 0, "", "", "150 water bottles, 10 of each pack")["display_markdown"]
    assert "150 water bottles" in md and "Still needed" in md and "date" in md


def test_october_24_with_a_guessed_past_year_is_not_reported_as_passed():
    from datetime import date as _d
    md = orchestration_tools.checklist("campaign", "", 0, f"{_d.today().year - 1}-12-31")["display_markdown"]
    assert "has already passed" not in md and "campaign name" in md


def test_new_york_usa_is_the_usa_and_other_cities_are_recognised():
    for text, venue in [("New York, USA", "USA"), ("Toronto, Canada", "Canada"), ("London, UK", "London"), ("United States", "USA")]:
        assert orchestration_tools.checklist("campaign", "X", 0, _iso(25), text)["venue_name"] == venue


