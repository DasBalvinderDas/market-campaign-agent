import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODE = """
import json
from campaign_provisioner.agent import root_agent
from campaign_provisioner.sub_agents.inventory_agent import inventory_agent
from campaign_provisioner.sub_agents.procurement_agent import procurement_agent
from campaign_provisioner.sub_agents.budget_agent import budget_agent
print(json.dumps({
  "sub_agents": [a.name for a in root_agent.sub_agents],
  "tools": [getattr(t, "name", getattr(t, "__name__", str(t))) for t in root_agent.tools],
  "texts": [root_agent.instruction, inventory_agent.instruction, procurement_agent.instruction, budget_agent.instruction],
}))
"""


def load(mode):
    env = {**os.environ, "SUBAGENT_MODE": mode, "DATA_BACKEND": "memory", "WORKFLOW_BACKEND": "mock", "PYTHONPATH": str(ROOT)}
    out = subprocess.run([sys.executable, "-c", CODE], env=env, capture_output=True, text=True, cwd=ROOT, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_transfer_mode_is_the_default_shape():
    d = load("transfer")
    assert d["sub_agents"] == ["inventory_agent", "procurement_agent", "budget_agent"]
    assert "inventory_agent" not in d["tools"]
    assert "Transfer to inventory_agent" in d["texts"][0]


def test_tool_mode_makes_the_root_agent_call_the_specialists():
    d = load("tool")
    assert d["sub_agents"] == []
    assert {"inventory_agent", "procurement_agent", "budget_agent", "approve_budget"} <= set(d["tools"])
    for text in d["texts"]:
        assert "ransfer" not in text.replace("transfer_to_agent", "")  # no hand-off wording left in any instruction
    assert "call the inventory_agent tool" in d["texts"][0]
    assert "write everything it needs in its request" in d["texts"][0]
