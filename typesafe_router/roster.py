"""Build a TypeSafe roster from the skills actually installed on this machine.

The published cookbook pins a JSON snapshot of Nous Research's 182-skill catalog. This
reads `~/.hermes/skills/**/SKILL.md` instead, so the router ranks the roster the agent
really sees — including everything the user has written since.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Sequence

try:  # pyyaml is in the lab venv; the fallback keeps this importable anywhere
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

INDEX_WIDTH = 60  # Hermes truncates index descriptions at 60 chars
DEFAULT_EXCERPT_CHARS = 700
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def skills_root() -> Path:
    home = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
    return home / "skills"


@dataclass(frozen=True)
class Skill:
    name: str
    category: str
    description: str
    index_description: str
    excerpt: str
    path: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _fallback_frontmatter(block: str) -> dict[str, str]:
    """Parse the two fields we need when PyYAML is missing (block scalars included)."""
    meta: dict[str, str] = {}
    lines = block.splitlines()
    for i, line in enumerate(lines):
        if ":" not in line or line.startswith((" ", "\t")):
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if key not in {"name", "description"}:
            continue
        if value in {">", "|", ">-", "|-"}:
            chunk = []
            for follow in lines[i + 1:]:
                if follow.strip() and not follow.startswith((" ", "\t")):
                    break
                chunk.append(follow.strip())
            value = " ".join(part for part in chunk if part)
        meta[key] = value.strip('"').strip("'")
    return meta


def parse_skill(
    path: Path,
    *,
    root: str | Path | None = None,
    excerpt_chars: int = DEFAULT_EXCERPT_CHARS,
) -> Skill | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = FRONTMATTER_RE.match(text)
    meta: dict[str, str] = {}
    body = text
    if match:
        block = match.group(1)
        body = text[match.end():]
        if yaml is not None:
            try:
                loaded = yaml.safe_load(block)
            except yaml.YAMLError:
                loaded = None  # some hand-written frontmatter is not valid YAML
            if isinstance(loaded, dict):
                meta = {str(k): str(v) for k, v in loaded.items() if v is not None}
        if not meta:
            meta = _fallback_frontmatter(block)

    name = (meta.get("name") or path.parent.name).strip()
    description = " ".join((meta.get("description") or "").split())
    if not description:
        for line in body.splitlines():
            if line.strip() and not line.startswith("#"):
                description = line.strip()
                break

    base = Path(root) if root else skills_root()
    try:
        relative = path.parent.relative_to(base)
    except ValueError:
        relative = None
    parts = relative.parts if relative is not None else (path.parent.name,)
    category = parts[0] if len(parts) > 1 else "root"

    return Skill(
        name=name,
        category=category,
        description=description,
        index_description=description if len(description) <= INDEX_WIDTH else description[:INDEX_WIDTH - 3] + "...",
        excerpt=" ".join(body[:excerpt_chars].split()),
        path=str(path),
    )


def load_roster(
    root: str | Path | None = None,
    *,
    excerpt_chars: int = DEFAULT_EXCERPT_CHARS,
    include: Sequence[str] | None = None,
) -> list[Skill]:
    base = Path(root) if root else skills_root()
    skills: list[Skill] = []
    for path in sorted(base.rglob("SKILL.md")):
        try:
            relative_parts = path.relative_to(base).parts
        except ValueError:
            relative_parts = path.parts
        if any(part.startswith(".") for part in relative_parts):
            continue
        skill = parse_skill(path, root=base, excerpt_chars=excerpt_chars)
        if skill is None:
            continue
        if include is not None and skill.name not in include:
            continue
        skills.append(skill)
    by_name: dict[str, Skill] = {}
    for skill in skills:  # later paths win, matching Hermes' discovery order closely enough
        by_name[skill.name] = skill
    return sorted(by_name.values(), key=lambda s: (s.category, s.name))


def render_index(skills: Iterable[Skill]) -> str:
    """The roster body as Hermes shows it: category headings, `- name: description`."""
    grouped: dict[str, list[Skill]] = {}
    for skill in skills:
        grouped.setdefault(skill.category, []).append(skill)
    lines: list[str] = []
    for category in sorted(grouped):
        lines.append(f"  {category}:")
        for skill in sorted(grouped[category], key=lambda s: s.name):
            lines.append(f"    - {skill.name}: {skill.index_description}")
    return "\n".join(lines)


def index_criteria(skills: Iterable[Skill]) -> dict[str, str]:
    """Stage-1 Choice criteria: every skill -> the same one line the agent's index shows."""
    return {skill.name: skill.index_description for skill in skills}


def shortlist_criteria(skills: Iterable[Skill], excerpt_chars: int = DEFAULT_EXCERPT_CHARS) -> dict[str, str]:
    """Stage-2 Choice criteria: full description plus the opening of SKILL.md."""
    criteria: dict[str, str] = {}
    for skill in skills:
        excerpt = skill.excerpt[:excerpt_chars]
        criteria[skill.name] = f"{skill.description}\n\nSKILL.md: {excerpt}" if excerpt else skill.description
    return criteria


def stats(skills: Sequence[Skill]) -> dict[str, object]:
    widths = [len(s.index_description) for s in skills]
    per_category = Counter(s.category for s in skills)
    return {
        "skills": len(skills),
        "categories": len(per_category),
        "avg_index_width": round(sum(widths) / len(widths), 1) if widths else 0,
        "max_index_width": max(widths) if widths else 0,
        "per_category": dict(sorted(per_category.items(), key=lambda kv: (-kv[1], kv[0]))),
        "root": str(skills_root()),
    }
