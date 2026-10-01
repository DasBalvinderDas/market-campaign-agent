# The Campaign Provisioner (Google Next 2027 edition)

Autonomous Google ADK agent for campaign logistics. A root orchestrator governs three sub-agents (inventory,
procurement, budget). Data lives in **BigQuery**, workflow actions run through **Google Application Integration**, and
high-value spend pauses for a named human approver.

- Setup and 7 demo prompts (with HITL cases): [docs/DEMO_RUN.md](docs/DEMO_RUN.md)
- Design, code flow, data and assumptions: [docs/SOLUTION.md](docs/SOLUTION.md)
- Application Integration contract: [integration/README.md](integration/README.md)
- BigQuery DDL: [bigquery/schema.sql](bigquery/schema.sql); setup: `scripts/setup_bigquery.py`, `scripts/setup_application_integration.py`
- Management deck (updated for BigQuery + Application Integration): `docs/Campaign_Provisioner_Management_Deck.pptx`

Quick start (offline rehearsal): `pip install -r requirements.txt && pytest`, then set `DATA_BACKEND=memory` and
`WORKFLOW_BACKEND=mock` in `.env` and run `adk web`.
