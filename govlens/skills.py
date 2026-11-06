"""Agent skills: the instructions GovLens gives its language models, kept as SKILL.md files.

Each skill is a folder under skills/ with a SKILL.md file in the open Agent Skills format
(YAML front matter with name and description, then a Markdown body). The same files are
used in two ways:

* the CrewAI agents receive them through CrewAI's own skill loader (``crewai_skills``);
* the purchase-justification screen, which is one structured OpenAI call rather than a
  crew, reads its skill body directly as the system prompt (``read_skill``).

Keeping prompts as files means a reviewer can read, version and change the instructions
without touching the Python code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

import yaml

from .knowledge import APP_DIR

SKILLS_DIR = APP_DIR / "skills"
_CLOSING = re.compile(r"\r?\n---[ \t]*(?:\r?\n|$)")


@dataclass(frozen=True)
class SkillDoc:
    name: str
    description: str
    body: str
    path: Path
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def version(self) -> str:
        return str(self.metadata.get("version", ""))

    @property
    def used_by(self) -> str:
        return str(self.metadata.get("used-by", ""))


def parse_skill(text: str, path: Path) -> SkillDoc:
    """Split SKILL.md into front matter and body (same rules as CrewAI's parser)."""
    if not text.startswith("---"):
        raise ValueError(f"{path}: SKILL.md must start with '---'")
    match = _CLOSING.search(text, pos=3)
    if match is None:
        raise ValueError(f"{path}: missing closing '---'")
    front = yaml.safe_load(text[3:match.start()]) or {}
    name, description = str(front.get("name", "")), str(front.get("description", ""))
    if not name or not description:
        raise ValueError(f"{path}: front matter needs name and description")
    if path.parent.name != name:
        raise ValueError(f"{path}: folder name must match skill name {name!r}")
    metadata = {str(k): str(v) for k, v in (front.get("metadata") or {}).items()}
    return SkillDoc(name=name, description=description, body=text[match.end():].strip(),
                    path=path, metadata=metadata)


def read_skill(name: str, skills_dir: Path = SKILLS_DIR) -> SkillDoc:
    path = skills_dir / name / "SKILL.md"
    return parse_skill(path.read_text(encoding="utf-8"), path)


def list_skills(skills_dir: Path = SKILLS_DIR) -> list[SkillDoc]:
    return [read_skill(p.parent.name, skills_dir) for p in sorted(skills_dir.glob("*/SKILL.md"))]


def crewai_skills(names: list[str], skills_dir: Path = SKILLS_DIR) -> list:
    """CrewAI Skill objects, fully loaded.

    CrewAI's default is progressive disclosure: an agent first sees only each skill's
    description and may load the body if it judges the skill relevant. GovLens activates
    its skills up front instead, so every run follows the same instructions.
    """
    from crewai.skills import activate_skill
    from crewai.skills.parser import load_skill_metadata

    return [activate_skill(load_skill_metadata(skills_dir / name)) for name in names]
