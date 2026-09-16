"""Roster loading: the live skills tree, including the shapes that broke the first build."""

from __future__ import annotations

from helpers import ROOT  # noqa: F401  (import side effect: repo root on sys.path)

from typesafe_router.roster import (
    INDEX_WIDTH,
    index_criteria,
    load_roster,
    parse_skill,
    render_index,
    skills_root,
    stats,
)


def test_loads_skills_and_skips_dot_directories(skills_dir):
    """Regression: filtering dot-parts on the *absolute* path deleted the whole roster."""
    roster = load_roster(skills_dir)
    names = [s.name for s in roster]
    assert names == ["gmail-cleanup", "spam-sweep", "plain"] or set(names) == {
        "gmail-cleanup", "spam-sweep", "plain"
    }
    assert "old-skill" not in names


def test_invalid_yaml_frontmatter_falls_back_instead_of_losing_the_skill(skills_dir):
    """`description: Sweep spam: keep what matters` is not valid YAML; the skill must survive."""
    skill = parse_skill(skills_dir / "email" / "spam-sweep" / "SKILL.md", root=skills_dir)
    assert skill is not None
    assert skill.name == "spam-sweep"
    assert skill.description == "Sweep spam: keep what matters"


def test_missing_frontmatter_falls_back_to_the_first_prose_line(skills_dir):
    skill = parse_skill(skills_dir / "plain" / "SKILL.md", root=skills_dir)
    assert skill is not None
    assert skill.description == "A skill with no frontmatter at all."


def test_index_lines_respect_the_sixty_character_budget(skills_dir):
    for skill in load_roster(skills_dir):
        assert len(skill.index_description) <= INDEX_WIDTH


def test_categories_come_from_the_first_path_segment(skills_dir):
    by_name = {s.name: s.category for s in load_roster(skills_dir)}
    assert by_name["gmail-cleanup"] == "software-development"
    assert by_name["spam-sweep"] == "email"
    assert by_name["plain"] == "root"


def test_render_index_groups_by_category(skills_dir):
    rendered = render_index(load_roster(skills_dir))
    assert "  software-development:" in rendered
    assert "    - gmail-cleanup: " in rendered


def test_index_criteria_is_one_line_per_skill(skills_dir):
    criteria = index_criteria(load_roster(skills_dir))
    assert set(criteria) == {"gmail-cleanup", "spam-sweep", "plain"}


def test_stats_reports_the_roster_shape(skills_dir):
    info = stats(load_roster(skills_dir))
    assert info["skills"] == 3
    assert info["categories"] == 3
    assert info["max_index_width"] <= INDEX_WIDTH


def test_roster_root_follows_hermes_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    assert skills_root() == tmp_path / "skills"


def test_loading_a_missing_directory_is_empty_not_an_error(tmp_path):
    assert load_roster(tmp_path / "nope") == []
