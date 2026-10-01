# The Campaign Provisioner

Autonomous Google ADK agent for marketing campaign logistics. A root orchestrator governs three sub-agents (inventory, procurement, budget) and pauses high-value spend for human approval.

- Solution guide (problem, design, code flow): [docs/SOLUTION.md](docs/SOLUTION.md)
- Management deck (3 slides, editable architecture): `docs/Campaign_Provisioner_Management_Deck.pptx` (generator: `docs/build_deck.js`)

Quick start: `pip install -r requirements.txt && cp .env.example .env && adk web`, then run `pytest` for the offline tests.
