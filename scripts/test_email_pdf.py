#!/usr/bin/env python3
"""Test the PDF attachment end to end, without the chat: build a sample order pack PDF, put it in the private bucket and send
a test email with it through the same workflow the agent uses.

  python scripts/test_email_pdf.py --to you@example.com
  python scripts/test_email_pdf.py --to you@example.com --request REQ-1A2B3C4D     # the real order pack of a request

It reports every step: PDF built, file in the bucket, workflow accepted the attachment, and which form of the attachment
(text or list) it took. Then check the inbox of --to for the PDF.
"""
import argparse
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import resolve_project  # noqa: E402


def sample_pdf() -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate
    buf = io.BytesIO()
    st = getSampleStyleSheet()
    SimpleDocTemplate(buf, pagesize=A4).build([Paragraph("Order pack: test", st["Title"]),
                                               Paragraph("If you can read this, the PDF attachment works.", st["BodyText"])])
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--to", required=True, help="who gets the test email")
    ap.add_argument("--request", help="use the real order pack of this request id instead of a sample")
    ap.add_argument("--project")
    a = ap.parse_args()
    import os
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", resolve_project(a.project))
    from launchkit_provisioner import config, storage
    from launchkit_provisioner.workflow.integration_client import IntegrationExecutor

    print(f"Project: {config.PROJECT}   Bucket: {config.ORDER_PACK_BUCKET or '(not set)'}")
    if not config.ORDER_PACK_BUCKET:
        sys.exit("ORDER_PACK_BUCKET is not set. Run: python scripts/setup_order_pack_bucket.py")
    if a.request:
        from launchkit_provisioner.repositories import get_repo
        from launchkit_provisioner import order_pack
        try:
            pdf, name = order_pack.build_pdf(get_repo(), a.request), a.request
        except ValueError as exc:
            print(f"  ..  {a.request}: {exc}. Using a sample PDF instead (pick a request that has been through the choice step).")
            pdf, name = sample_pdf(), "TEST"
    else:
        pdf, name = sample_pdf(), "TEST"
    print(f"  OK  PDF built ({len(pdf):,} bytes)")
    path = storage.upload_pack(name, pdf)
    if not path:
        sys.exit("  FAIL the file could not be written to the bucket (check the log line above, the bucket name and the "
                 "service account's Storage Object Admin role).")
    print(f"  OK  file in the bucket: {path}")
    ex = IntegrationExecutor()
    body = "<div style='font-family:Arial'><h3>PDF attachment test</h3><p>Form: <b>%s</b>. The order pack PDF should be attached to this email.</p></div>"
    sent = []
    for form in storage.FORMS:
        try:
            ex.execute(config.UPDATE_TRIGGER, {"request_id": name, "launch_id": "TEST", "recipient_email": a.to,
                                               "email_subject": f"PDF test [{form}] (please ignore)", "email_body": body % form,
                                               "attachment_path": storage.attachment_value(path, form)})
            print(f"  OK  sent the test email for form '{form}'")
            sent.append(form)
        except Exception as exc:  # noqa: BLE001
            print(f"  ..  form '{form}' refused by the workflow: {str(exc)[:200]}")
    if not sent:
        sys.exit("  FAIL the workflow refused every form (see above).")
    print(f"\nNow open the inbox of {a.to}: the subject of the email that HAS the PDF tells you the form, e.g. 'PDF test [list-gs]'.\n"
          "Put it in .env as ORDER_PACK_ATTACH_FORM=<form> and redeploy the agent. If none has the PDF, tell the maintainer.")


if __name__ == "__main__":
    main()
