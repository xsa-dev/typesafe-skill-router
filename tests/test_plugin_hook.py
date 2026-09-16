"""The hook contract: what reaches the turn, what never does, and what gets logged."""

from __future__ import annotations

import time

import pytest

from helpers import NONE, scripted_client, skill, plugin_module
from typesafe_router.roster import Skill

PLUGIN = "typesafe-skill-router"


@pytest.fixture
def env(tmp_path, monkeypatch, skills_dir):
    """A throwaway Hermes home: no ambient key, no operator log, roster from the fixture."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    return {
        "enabled": True,
        "roster_dir": str(skills_dir),
        "cache_path": str(tmp_path / "cache.json"),
        "log_path": str(tmp_path / "router.log"),
    }


def _ok_client(*, skill_name="gmail-cleanup", gate=(0.95, 0.56, 0.27), fits=None):
    fits = fits or {skill_name: 0.96}
    return scripted_client(stage1=skill_name, gate=gate, stage2=skill_name, fits=fits)


# ─── registration ────────────────────────────────────────────────────────────
def test_register_wires_the_hook_and_the_cli_command():
    module = plugin_module()
    ctx = type("Ctx", (), {
        "hooks": {}, "commands": {},
        "register_hook": lambda self, name, cb: self.hooks.__setitem__(name, cb),
        "register_cli_command": lambda self, name, help, setup_fn, handler_fn=None, description="": self.commands.__setitem__(name, handler_fn),
    })()
    module.register(ctx)
    assert set(ctx.hooks) == {"pre_llm_call"}
    assert set(ctx.commands) == {PLUGIN}


def test_register_stays_off_the_network_and_disk(tmp_path, monkeypatch):
    """The admission probe imports and calls register() with a scratch home; it must be inert."""
    home = tmp_path / "probe-home"
    monkeypatch.setenv("HERMES_HOME", str(home))
    module = plugin_module()
    ctx = type("Ctx", (), {
        "register_hook": lambda self, name, cb: None,
        "register_cli_command": lambda self, name, help, setup_fn, handler_fn=None, description="": None,
        "get_config": lambda self, key, default=None: default,
    })()
    module.register(ctx)
    assert not home.exists()


# ─── silence cases ───────────────────────────────────────────────────────────
def test_disabled_injects_nothing(env, monkeypatch):
    module = plugin_module()
    ctx = _ctx(module, {**env, "enabled": False})
    monkeypatch.setattr(module, "_client", lambda *a, **k: _ok_client())
    assert module.pre_llm_call(_typesafe_ctx=ctx, user_message="clear my gmail spam") is None


def test_slash_commands_are_left_alone(env, monkeypatch):
    module = plugin_module()
    ctx = _ctx(module, env)
    monkeypatch.setattr(module, "_client", lambda *a, **k: _ok_client())
    assert module.pre_llm_call(_typesafe_ctx=ctx, user_message="/voice on") is None


def test_oversized_messages_are_skipped(env, monkeypatch):
    module = plugin_module()
    ctx = _ctx(module, {**env, "suggest_chars": 50})
    monkeypatch.setattr(module, "_client", lambda *a, **k: _ok_client())
    assert module.pre_llm_call(_typesafe_ctx=ctx, user_message="x" * 51) is None


def test_multimodal_content_parts_are_skipped(env, monkeypatch):
    module = plugin_module()
    ctx = _ctx(module, env)
    monkeypatch.setattr(module, "_client", lambda *a, **k: _ok_client())
    assert module.pre_llm_call(_typesafe_ctx=ctx, user_message=[{"type": "text", "text": "hi"}]) is None


def test_missing_key_logs_once_and_stays_quiet(tmp_path, monkeypatch, skills_dir):
    module = plugin_module()
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    log = tmp_path / "router.log"
    ctx = _ctx(module, {"enabled": True, "roster_dir": str(skills_dir), "log_path": str(log)})
    for _ in range(3):
        assert module.pre_llm_call(_typesafe_ctx=ctx, user_message="clear my gmail spam") is None
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and "TYPESAFE_API_KEY" in lines[0]


def test_empty_roster_logs_once_and_stays_quiet(tmp_path, monkeypatch):
    module = plugin_module()
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    log = tmp_path / "router.log"
    ctx = _ctx(module, {"enabled": True, "roster_dir": str(tmp_path / "empty"),
                        "log_path": str(log)})
    assert module.pre_llm_call(_typesafe_ctx=ctx, user_message="clear my gmail spam") is None
    assert "no skills found" in log.read_text(encoding="utf-8")


# ─── the injection ───────────────────────────────────────────────────────────
def test_suggests_the_fitting_skill_and_logs_one_line(env, monkeypatch):
    module = plugin_module()
    ctx = _ctx(module, env)
    monkeypatch.setattr(module, "_client", lambda *a, **k: _ok_client())
    out = module.pre_llm_call(_typesafe_ctx=ctx, user_message="clear the spam out of my gmail inbox")
    assert out == {"context":
                   "\n\n<skill_relevance>\nRelevant to the current request: gmail-cleanup. "
                   "Ignore this if it does not fit what the user actually asked for.\n"
                   "</skill_relevance>"}
    lines = (env["log_path"] and open(env["log_path"], encoding="utf-8").read().splitlines())
    assert len(lines) == 1
    assert lines[0].split("\t")[1] == "suggest"
    assert "gmail-cleanup" in lines[0]


def test_nothing_fitting_injects_nothing_but_still_logs(env, monkeypatch):
    """Silence is a result, not an error: one line either way, on the operator's terms."""
    module = plugin_module()
    ctx = _ctx(module, env)
    monkeypatch.setattr(module, "_client", lambda *a, **k: _ok_client(gate=(0.10, 0.10, 0.95)))
    assert module.pre_llm_call(_typesafe_ctx=ctx, user_message="why is the sky blue?") is None
    assert "suggest\t- gate=" in open(env["log_path"], encoding="utf-8").read()


def test_roster_comes_from_the_configured_directory(env, monkeypatch):
    module = plugin_module()
    ctx = _ctx(module, env)
    client = _ok_client(skill_name="spam-sweep", fits={"spam-sweep": 0.9})
    monkeypatch.setattr(module, "_client", lambda *a, **k: client)
    module.pre_llm_call(_typesafe_ctx=ctx, user_message="sweep the spam: keep what matters")
    names = set(client.stage1_calls[0]["questions"]["which"]["criteria"])
    assert {"gmail-cleanup", "spam-sweep"} <= names
    assert "old-skill" not in names  # dot-directory is not part of the roster


# ─── failure containment ─────────────────────────────────────────────────────
def test_api_failure_returns_none_and_logs_one_error(env, monkeypatch):
    module = plugin_module()

    def boom(*args, **kwargs):
        raise RuntimeError("TypeSafe API 500")

    monkeypatch.setattr(module, "suggest", boom)
    ctx = _ctx(module, env)
    assert module.pre_llm_call(_typesafe_ctx=ctx, user_message="clear my gmail spam") is None
    text = open(env["log_path"], encoding="utf-8").read()
    assert "error" in text and "TypeSafe API 500" in text


def test_slow_routing_is_cut_off_by_the_budget(env, monkeypatch):
    module = plugin_module()

    def slow(*args, **kwargs):
        time.sleep(3)
        raise AssertionError("must not be reached")

    monkeypatch.setattr(module, "suggest", slow)
    ctx = _ctx(module, {**env, "timeout": 1.0})
    started = time.perf_counter()
    assert module.pre_llm_call(_typesafe_ctx=ctx, user_message="clear my gmail spam") is None
    assert time.perf_counter() - started < 2.5
    assert "budget" in open(env["log_path"], encoding="utf-8").read()


def test_log_path_is_a_setting_so_tests_never_touch_the_operator_log(tmp_path, env, monkeypatch):
    module = plugin_module()
    module.pre_llm_call(_typesafe_ctx=_ctx(module, {**env, "enabled": False}), user_message="hi")
    assert not (tmp_path / "home" / "logs" / f"{PLUGIN}.log").exists()


# ─── CLI ─────────────────────────────────────────────────────────────────────
def test_cli_on_off_toggles_the_setting(env, capsys):
    module = plugin_module()
    ctx = _ctx(module, {**env, "enabled": False})
    handler = module.register.__globals__["_cli_handler"](ctx)
    handler(type("A", (), {"action": "on"})())
    assert ctx.settings["enabled"] is True
    handler(type("A", (), {"action": "off"})())
    assert ctx.settings["enabled"] is False


def test_cli_status_reports_the_essentials(env, capsys):
    module = plugin_module()
    ctx = _ctx(module, env)
    handler = module.register.__globals__["_cli_handler"](ctx)
    assert handler(type("A", (), {"action": "status"})()) == 0
    out = capsys.readouterr().out
    assert "enabled" in out and "roster" in out and "api key" in out


def test_cli_check_flags_a_missing_key(tmp_path, monkeypatch, capsys):
    module = plugin_module()
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    ctx = _ctx(module, {"roster_dir": str(tmp_path / "empty")})
    handler = module.register.__globals__["_cli_handler"](ctx)
    assert handler(type("A", (), {"action": "check"})()) == 1
    out = capsys.readouterr().out
    assert "MISSING" in out and "no skills found" in out


def _ctx(module, settings):
    """A stub ctx with the plugin's own defaults semantics (missing key -> default)."""
    from helpers import StubContext

    ctx = StubContext(settings)
    return ctx
