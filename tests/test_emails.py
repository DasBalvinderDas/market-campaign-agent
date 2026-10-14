"""The two HTML emails: the approval request with Approve / Reject buttons, and the orders-placed update."""
import re

from conftest import FakeExecutor
from launchkit_provisioner import config, decision_flow, emails, execution


def _authorize(repo, aurora, option="2"):
    ex = FakeExecutor()
    out = decision_flow.authorize(repo, ex, aurora, option, "Cheapest choice with spare time")
    return ex, out


def _approval_mails(ex):
    return [i for t, i in ex.calls if t == config.UPDATE_TRIGGER and i["email_subject"].startswith("Approval needed")]


def test_the_approver_gets_our_own_html_email_with_two_buttons(repo, aurora):
    ex, out = _authorize(repo, aurora)
    mails = _approval_mails(ex)
    assert out["status"] == "pending_approval" and len(mails) == 1 and mails[0]["recipient_email"] == "vp@example.com"
    html = mails[0]["email_body"]
    assert html.startswith("<div") and "&#10003; Approve" in html and "&#10007; Reject" in html
    assert html.count("<a href=") == 2 and "display:inline-block;background:#16a34a" in html and "background:#dc2626" in html
    assert mails[0]["email_subject"] == "Approval needed: Spring Product Launch Event, $37,399.50"
    assert "REQ-001" not in mails[0]["email_subject"] and "REQ-001" not in html


def test_the_buttons_open_the_approval_page_of_this_run(repo, aurora):
    ex, _ = _authorize(repo, aurora)
    html = _approval_mails(ex)[0]["email_body"]
    links = set(re.findall(r'<a href="([^"]+)"', html))
    assert len(links) == 1                                    # both buttons go to the same approval page
    url = links.pop().replace("&amp;", "&")
    assert url.startswith("https://console.cloud.google.com/integrations/integration/launchkit-workflows/locations/")
    assert "/approval?project=" in url and "&execution_id=exec-9&task_number=10" in url


def test_the_long_link_is_only_behind_the_buttons_never_shown_as_text(repo, aurora):
    ex, _ = _authorize(repo, aurora)
    html = _approval_mails(ex)[0]["email_body"]
    assert html.count("console.cloud.google.com") == 2                    # the two hrefs, nowhere else
    assert "Copy this address" not in html
    visible = re.sub(r"<a href=\"[^\"]*\"", "<a", html)
    assert "console.cloud.google.com" not in visible and "execution_id" not in visible


def test_the_approval_email_carries_the_decision_the_shopping_list_and_the_vendors(repo, aurora):
    ex, _ = _authorize(repo, aurora)
    html = _approval_mails(ex)[0]["email_body"]
    assert "$37,399.50" in html and "Use our stock first, buy the rest" in html and "Saves $8,676.00" in html
    assert "VP Product Marketing" in html and "$5,000.00 to $50,000.00" in html and "Cheapest choice with spare time" in html
    assert "Shopping list (Bill of Materials)" in html and "VIP guest welcome kit" in html and "1,210 items in total" in html
    assert "Vendors we are ordering from" in html and "DisplayCo" in html and "RapidDisplay" in html and "PrintCo" in html
    assert "Taken from our own warehouses" in html and "London EMEA Marketing Hub" in html and "Dallas Marketing Depot" in html


def test_every_approver_of_the_role_gets_the_email(repo, aurora):
    repo.t["approvers"].append({"approver_role": "VP Product Marketing", "email": "vp2@example.com", "active": True})
    ex, out = _authorize(repo, aurora)
    assert sorted(m["recipient_email"] for m in _approval_mails(ex)) == ["vp2@example.com", "vp@example.com"]
    assert out["approvers_notified"] == 2 and "@" not in str(out["announce"])


def test_the_cmo_gets_it_for_the_largest_option(repo, aurora):
    ex, out = _authorize(repo, aurora, "3")
    assert out["approver_role"] == "CMO" and [m["recipient_email"] for m in _approval_mails(ex)] == ["cmo@example.com"]


def test_no_approver_address_means_no_order_and_a_clear_message(repo, aurora):
    repo.t["approvers"] = []
    ex, out = _authorize(repo, aurora)
    assert out["status"] == "error" and "no email address is set for VP Product Marketing" in out["message"]
    assert repo.get_decision_for_request(aurora)["status"] == "FAILED" and not [h for h in repo.t["depot_holds"] if h["status"] == "ACTIVE"]


def test_if_the_email_cannot_be_sent_nothing_stays_pending(repo, aurora):
    ex = FakeExecutor(fail_on=lambda t, i: t == config.UPDATE_TRIGGER)
    out = decision_flow.authorize(repo, ex, aurora, "2", "x")
    assert out["status"] == "error" and "could not be sent" in out["message"]
    assert repo.get_decision_for_request(aurora)["status"] == "FAILED" and "approval_email_failed" in [a["action"] for a in repo.list_audit(aurora)]


def test_the_orders_placed_email_now_also_has_the_shopping_list_the_vendors_and_the_po_numbers(repo, aurora):
    repo.t["approvers"] += [{"approver_role": "Launch Team", "email": "team@example.com", "active": True}]
    ex, _ = _authorize(repo, aurora)
    dec = repo.get_decision_for_request(aurora)
    repo.decide(dec["decision_id"], "APPROVED", "Application Integration approval", "ok")
    execution.execute_plan(repo, ex, aurora)
    mail = next(i for t, i in ex.calls if t == config.UPDATE_TRIGGER and i["email_subject"].startswith("Orders placed"))
    html = mail["email_body"]
    assert "ORDERS PLACED" in html and "Purchase orders placed" in html and "<b>7</b>" not in html
    assert "Shopping list (Bill of Materials)" in html and "Vendors we are ordering from" in html
    assert "Purchase order numbers" in html and f"PO-{aurora}-V-DISPLAYCO" in html and "DisplayCo" in html


def test_the_approval_url_is_built_from_the_project_integration_and_run():
    url = emails.approval_url("abc-123")
    assert url.endswith("&execution_id=abc-123&task_number=10") and "launchkit-workflows" in url and "us-central1" in url
