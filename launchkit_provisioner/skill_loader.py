"""Load the SKILL.md files in launchkit_provisioner/skills and build the skill toolset.

Written against the few stable pieces of the ADK skills API (the Skill and Frontmatter models and SkillToolset) so that it also
works when the deployed ADK is a little older than the one used while developing.
"""
from pathlib import Path

import yaml


def load_skills(skills_dir: Path) -> list:
    from google.adk.skills import models
    skills = []
    for md in sorted(Path(skills_dir).glob("*/SKILL.md")):
        text = md.read_text(encoding="utf-8")
        _, header, body = text.split("---", 2)
        skills.append(models.Skill(frontmatter=models.Frontmatter.model_validate(yaml.safe_load(header)), instructions=body.strip()))
    return skills


def build_toolset(skills_dir: Path):
    """The skill toolset: catalog in the system instruction and only load_skill offered, when this ADK supports those options."""
    from google.adk.tools.skill_toolset import SkillToolset
    skills = load_skills(skills_dir)
    try:
        from google.adk.tools.skill_toolset import SkillDiscoveryMode
        return SkillToolset(skills=skills, discovery_mode=SkillDiscoveryMode.EAGER, tool_filter=["load_skill"])
    except (ImportError, TypeError):
        return SkillToolset(skills=skills)
