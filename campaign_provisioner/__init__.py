"""The Campaign Provisioner ADK agent package.

Nothing is imported here on purpose: importing the package must not build the agents, because building them
connects to Application Integration, which the setup scripts have not created yet. ADK finds the agent in
`campaign_provisioner/agent.py` (`root_agent`) by itself.
"""
