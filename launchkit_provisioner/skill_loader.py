"""Load the SKILL.md files in launchkit_provisioner/skills and build the skill toolset.

Written against the few stable pieces of the ADK skills API (the Skill and Frontmatter models and SkillToolset). If the ADK
that is installed (for example an older one on Agent Engine) cannot load them, ``build_toolset`` returns None and the agent
puts the same skill text straight into its prompt instead (``skills_as_text``), so the flow is the same either way.
"""
import logging
from pathlib import Path

import yaml

log = logging.getLogger(__name__)


def _read(skills_dir: Path):
    out = []
    for md in sorted(Path(skills_dir).glob("*/SKILL.md")):
        _, header, body = md.read_text(encoding="utf-8").split("---", 2)
        out.append((yaml.safe_load(header), body.strip()))
    return out


def load_skills(skills_dir: Path) -> list:
    from google.adk.skills import models
    return [models.Skill(frontmatter=models.Frontmatter.model_validate(meta), instructions=body) for meta, body in _read(skills_dir)]


def build_toolset(skills_dir: Path):
    """The skill toolset, or None when this ADK cannot provide it."""
    try:
        from google.adk.tools.skill_toolset import SkillToolset
        skills = load_skills(skills_dir)
        try:
            from google.adk.tools.skill_toolset import SkillDiscoveryMode
            return SkillToolset(skills=skills, discovery_mode=SkillDiscoveryMode.EAGER, tool_filter=["load_skill"])
        except (ImportError, TypeError):
            return SkillToolset(skills=skills)
    except Exception as exc:  # noqa: BLE001 - an older ADK: fall back to the prompt
        log.warning("skills are not available in this ADK (%s); using the prompt instead", exc)
        return None


def skills_as_text(skills_dir: Path) -> str:
    """Every skill written out in full, for the prompt of an agent that cannot load skills."""
    parts = ["", "The detailed instructions for each phase follow. Use the one that matches what the user is doing, exactly:"]
    for meta, body in _read(skills_dir):
        parts += ["", f"=== {meta['name']}: {meta['description']}", body]
    return "\n".join(parts)
