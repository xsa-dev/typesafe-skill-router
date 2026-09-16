"""Fixtures only — helpers live in ``helpers.py`` so pytest's conftest loading stays simple.

The plugin directory is itself a package (Hermes imports the directory as one, and the
admission probe does the same), so the tests run in ``importlib`` mode with the repo root and
``tests/`` on ``sys.path`` (see ``pyproject.toml``).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    """A miniature skills tree, including the shapes that used to break the loader."""
    root = tmp_path / "skills"

    def write(relative: str, body: str) -> None:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")

    write("software-development/gmail-cleanup/SKILL.md",
          '---\nname: gmail-cleanup\ndescription: "Clear spam and bulk mail from Gmail."\n---\n\nSteps here.')
    # Hand-written frontmatter that is not valid YAML (unquoted ": " inside the value).
    write("email/spam-sweep/SKILL.md",
          "---\nname: spam-sweep\ndescription: Sweep spam: keep what matters\n---\n\nBody line.\n")
    # No frontmatter at all: the description falls back to the first prose line.
    write("plain/SKILL.md", "# Plain\n\nA skill with no frontmatter at all.\n")
    # Dot-directories must be skipped *relative to the root* (the absolute path holds .hermes).
    write(".archive-shadow/old-skill/SKILL.md",
          "---\nname: old-skill\ndescription: Archived copy.\n---\n")
    return root
