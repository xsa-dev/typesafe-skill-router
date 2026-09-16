"""TypeSafe skill routing: roster, client, two-stage router.

Stdlib only. The plugin entry point lives in the repository root (``__init__.py``);
everything reusable lives here so it can be tested and reused without Hermes.
"""

from .cache import JsonCache, request_key
from .client import (
    MissingAPIKey,
    MissingCachedResponse,
    SystemOneClient,
    SystemOneError,
    Usage,
)
from .roster import (
    Skill,
    load_roster,
    render_index,
    skills_root,
    stats,
)
from .router import (
    FITS_THRESHOLD,
    GATE_THRESHOLD,
    Suggestion,
    suggest,
    suggestion_block,
)

__version__ = "1.0.0"

__all__ = [
    "JsonCache",
    "MissingAPIKey",
    "MissingCachedResponse",
    "SystemOneClient",
    "SystemOneError",
    "Usage",
    "Skill",
    "load_roster",
    "render_index",
    "skills_root",
    "stats",
    "Suggestion",
    "suggest",
    "suggestion_block",
    "GATE_THRESHOLD",
    "FITS_THRESHOLD",
    "request_key",
    "__version__",
]
