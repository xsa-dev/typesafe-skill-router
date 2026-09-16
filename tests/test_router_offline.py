"""The router itself, offline: chunking, the no-match option, tie-breaking, thresholds.

Payload shapes asserted here are the ones the live API receives (criteria are
``name -> line`` mappings; with a chunked roster the gate judgments ride the first chunk only).
"""

from __future__ import annotations

import pytest

from helpers import NONE, roster, scripted_client, skill
from typesafe_router.router import (
    CHOICE_INSTRUCTIONS,
    CHUNK_CHOICES,
    MAX_CHOICES,
    chunk_roster,
    rerank_questions,
    suggest,
    suggestion_block,
)


def _criteria(call) -> dict:
    return call["questions"]["which"]["criteria"]


def _gate_keys(call) -> list:
    return [k for k in call["questions"] if k.startswith("gate::")]


# ─── chunking: the 255-choice cap found live ─────────────────────────────────
def test_small_roster_is_a_single_chunk_without_a_no_match_option():
    client = scripted_client(stage1="skill-000", stage2="skill-000", fits={"skill-000": 0.9})
    result = suggest(client, "do the thing", roster(5))

    assert result.skill == "skill-000"
    assert len(client.stage1_calls) == 1
    assert len(_gate_keys(client.stage1_calls[0])) == 3
    # Unchunked, the choice is the bare roster: no option to nominate nobody is needed.
    assert NONE not in _criteria(client.stage1_calls[0])


def test_large_roster_is_chunked_with_none_of_these_in_every_chunk():
    client = scripted_client(stage1="skill-000", stage2="skill-000", fits={"skill-000": 0.9})
    result = suggest(client, "do the thing", roster(292))

    assert len(client.stage1_calls) == 2
    assert result.chunks == 2
    for call in client.stage1_calls:
        assert NONE in _criteria(call)
    # The three gate judgments are asked once, on the first chunk.
    assert [_gate_keys(call) for call in client.stage1_calls] == [
        ["gate::acts_on_user_system", "gate::would_follow_documented_procedure", "gate::prose_suffices"],
        [],
    ]


def test_chunk_size_above_the_api_cap_is_refused():
    with pytest.raises(ValueError):
        chunk_roster(roster(600), MAX_CHOICES + 1)
    assert len(chunk_roster(roster(600), CHUNK_CHOICES)) == 3


# ─── a chunk with nothing relevant must not nominate noise ───────────────────
def test_chunk_saying_none_of_these_is_not_shortlisted():
    """The measured 12.5% -> 29.2% regression when an irrelevant chunk may name noise."""
    client = scripted_client(stage1="skill-001", stage2="skill-001", fits={"skill-001": 0.9})
    result = suggest(client, "something only skill-001 covers", roster(292))

    assert len(client.stage1_calls) == 2          # the roster really was chunked
    assert result.names == ("skill-001",)
    # Only the nominating chunk's candidates, ordered by (-probability, name): the empty
    # chunk contributes nobody, and the 0.0 ties around the winner are stable, not arbitrary.
    assert result.shortlist == ("skill-001", "skill-000", "skill-002")


def test_ties_break_by_name_not_dict_order():
    client = scripted_client(stage1=None, tie_to=0.0)
    result = suggest(client, "ambiguous", [skill("zeta"), skill("alpha"), skill("mike")])
    assert result.shortlist == ("alpha", "mike", "zeta")


# ─── thresholds ──────────────────────────────────────────────────────────────
def test_low_gate_suggests_nothing_and_spends_no_second_request():
    # prose_suffices high -> inverted low -> mean well under 0.30
    client = scripted_client(stage1="skill-000", gate=(0.10, 0.10, 0.95))
    result = suggest(client, "why is the sky blue?", roster(30))

    assert result.names == ()
    assert "gate" in result.reason
    assert client.stage2_calls == []


def test_winner_none_of_these_suggests_nothing():
    client = scripted_client(stage1="skill-000", stage2=NONE, fits={"skill-000": 0.9})
    assert suggest(client, "do the thing", roster(30)).names == ()


def test_winner_below_fits_threshold_suggests_nothing():
    client = scripted_client(stage1="skill-000", stage2="skill-000", fits={"skill-000": 0.39})
    result = suggest(client, "do the thing", roster(30))

    assert result.names == ()
    assert "fits" in result.reason


def test_fits_threshold_is_configurable():
    client = scripted_client(stage1="skill-000", stage2="skill-000", fits={"skill-000": 0.39})
    result = suggest(client, "do the thing", roster(30), fits_threshold=0.30)
    assert result.names == ("skill-000",)


def test_gate_averages_oriented_values():
    """prose_suffices counts inverted: (0.95 + 0.56 + (1 - 0.27)) / 3 = 0.7467."""
    client = scripted_client(stage1="skill-000", gate=(0.95, 0.56, 0.27),
                             stage2="skill-000", fits={"skill-000": 0.96})
    result = suggest(client, "clear the spam out of my gmail inbox", roster(30))
    assert result.gate == pytest.approx(0.7467, abs=0.0001)


def test_shortlist_is_capped_by_the_setting():
    client = scripted_client(stage1="skill-000", stage2="skill-000",
                             fits={f"skill-{i:03d}": 0.5 for i in range(9)})
    result = suggest(client, "do the thing", roster(30), shortlist=2)
    assert len(result.shortlist) == 2


# ─── the injected block ──────────────────────────────────────────────────────
def test_block_text_is_exactly_the_measured_string():
    block = suggestion_block(("gmail-inbox-cleanup",))
    assert block == (
        "\n\n<skill_relevance>\n"
        "Relevant to the current request: gmail-inbox-cleanup. Ignore this if it does not "
        "fit what the user actually asked for.\n</skill_relevance>"
    )


def test_no_suggestion_means_no_injection_at_all():
    """The empty-case block is never injected: it would cost tokens on every unrelated turn."""
    client = scripted_client(stage1=None, tie_to=0.0)
    result = suggest(client, "nothing matches", roster(10))

    assert result.names == ()
    assert result.skill is None


# ─── stage-2 question shape ──────────────────────────────────────────────────
def test_rerank_asks_one_absolute_question_per_candidate():
    by_name = {"a": skill("a"), "b": skill("b")}
    questions = rerank_questions(["a", "b"], by_name)

    assert set(questions) == {"which", "fits::a", "fits::b"}
    assert NONE in questions["which"]["criteria"]
    assert "Does the skill 'a' do the specific thing" in questions["fits::a"]["instructions"]
    assert questions["which"]["instructions"] != CHOICE_INSTRUCTIONS


def test_stage_two_sees_full_descriptions_not_index_lines():
    long_description = "x" * 400
    client = scripted_client(stage1="long", stage2="long", fits={"long": 0.8})
    suggest(client, "do the thing", [skill("long", description=long_description)])

    call = client.stage2_calls[0]
    assert long_description in _criteria(call)["long"]
    # Stage 2 always offers the no-match option; every *candidate* is a shortlist member,
    # never the whole roster.
    assert set(_criteria(call)) - {NONE} == {"long"}


def test_shortlist_survives_a_chunked_roster():
    """A fitting skill in the *second* chunk is still shortlisted and wins."""
    client = scripted_client(stage1="skill-260", stage2="skill-260", fits={"skill-260": 0.8})
    result = suggest(client, "do the thing", roster(292))

    assert result.skill == "skill-260"
    assert result.names == ("skill-260",)
    assert "skill-260" in result.shortlist
