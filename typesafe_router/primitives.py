"""Question builders for the three System One primitives.

Kept deliberately dumb: they emit exactly the JSON the API documents at
https://docs.typesafe.ai/api.md, so nothing here can drift from the wire format.
"""

from __future__ import annotations

from typing import Mapping, Sequence

Question = dict


def noul(instructions, true: str | None = None, false: str | None = None) -> Question:
    """Yes/no question; the answer is the probability the answer is yes."""
    q: Question = {"type": "noul", "instructions": instructions}
    if true is not None or false is not None:
        criteria: dict[str, str] = {}
        if true is not None:
            criteria["true"] = true
        if false is not None:
            criteria["false"] = false
        q["criteria"] = criteria
    return q


def choice(instructions, criteria: Mapping[str, str | None]) -> Question:
    """Pick one option from a defined set; the answer carries the full distribution."""
    if not criteria:
        raise ValueError("choice() needs at least one option")
    return {"type": "choice", "instructions": instructions, "criteria": dict(criteria)}


def score(instructions, criteria: Sequence[str]) -> Question:
    """Rate the state along ordered, self-describing levels."""
    levels = list(criteria)
    if len(levels) < 2:
        raise ValueError("score() needs at least two levels")
    return {"type": "score", "instructions": instructions, "criteria": levels}
