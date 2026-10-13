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
        pdf, name = order_pack.build_pdf(get_repo(), a.request), a.request
    else:
        pdf, name = sample_pdf(), "TEST"
    print(f"  OK  PDF built ({len(pdf):,} bytes)")
    path = storage.upload_pack(name, pdf)
    if not path:
        sys.exit("  FAIL the file could not be written to the bucket (check the log line above, the bucket name and the "
                 "service account's Storage Object Admin role).")
    print(f"  OK  file in the bucket: {path}")
    ex = IntegrationExecutor()
    base = {"request_id": name, "launch_id": "TEST", "recipient_email": a.to, "email_subject": "Order pack PDF test (please ignore)",
            "email_body": "<div style='font-family:Arial'><h3>PDF attachment test</h3><p>The order pack PDF should be attached to this email.</p></div>"}
    for label, value in (("text", path), ("list", [path])):
        try:
            ex.execute(config.UPDATE_TRIGGER, {**base, "attachment_path": value})
            print(f"  OK  the workflow accepted the attachment as a {label}. Check the inbox of {a.to} for the PDF.")
            return
        except Exception as exc:  # noqa: BLE001
            print(f"  ..  as a {label}: {str(exc)[:220]}")
    sys.exit("  FAIL the workflow refused the attachment in both forms (see the messages above).")


if __name__ == "__main__":
    main()
