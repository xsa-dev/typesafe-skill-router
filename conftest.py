"""Test bootstrap.

The repository root is itself an importable package (Hermes loads the directory as one, and
the catalog-admission probe does too), so pytest must not import ``__init__.py`` as a test
module — the tests load it by path instead, exactly as Hermes' loader does
(``hermes_cli/plugins_loader.py``).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

for entry in (REPO_ROOT / "tests", REPO_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

collect_ignore = ["__init__.py"]
