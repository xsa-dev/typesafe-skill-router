# TypeSafe skill router

A Hermes Agent plugin that names **the one skill worth loading** — before the model call.

Hermes shows the model a one-line description of every installed skill. With a few hundred of
them, the model reads past the one that would have done the job. This plugin sends the request
to [TypeSafe](https://typesafe.ai) (model `jev-latest`) first and, when a skill genuinely fits,
appends a single line to the **user message**:

```
<skill_relevance>
Relevant to the current request: gmail-inbox-cleanup. Ignore this if it does not fit what the
user actually asked for.
</skill_relevance>
```

It is **opt-in** (`enabled: false` by default), injects **nothing** when nothing fits, and every
failure path — no API key, no roster, timeout, transport error — logs one line and returns
`None`. A routing problem can never break a turn.

## Requirements

- Hermes Agent `>= 0.21`
- A TypeSafe API key (`TYPESAFE_API_KEY`) — create one at <https://console.typesafe.ai/settings/keys>
- Python 3.10+. Standard library only: no dependencies to install.

## Install

From the catalog:

```bash
hermes plugins install typesafe-skill-router   # then follow the prompt to enable it
```

Or straight from this repo:

```bash
git clone https://github.com/DECRUX9812/typesafe-skill-router ~/.hermes/plugins/typesafe-skill-router
hermes plugins enable typesafe-skill-router
hermes typesafe-skill-router on
```

Put the key where Hermes keeps its other secrets:

```bash
echo 'TYPESAFE_API_KEY=ts_...' >> ~/.hermes/.env     # chmod 600
```

If Hermes was already running when you installed the plugin, restart that process once so the
hook is loaded (`hermes gateway restart`, or the service that runs your chat backend). Switching
it on and off afterwards takes effect immediately.

## Settings

Under `plugins.entries.typesafe-skill-router.settings` in `config.yaml` (all optional):

| Setting | Default | What it does |
|---|---|---|
| `enabled` | `false` | Master switch. Nothing is sent anywhere until this is true. |
| `gate` | `0.30` | Mean of the three request judgments. Below it, nothing is suggested and no second request is spent. |
| `fits` | `0.40` | The winner's own "does this skill do the specific thing asked for" judgment. Below it, nothing is injected. |
| `shortlist` | `3` | Candidates carried into the second request. |
| `chunk` | `240` | Skills per request. The API caps a question at 255 options. |
| `excerpt` | `700` | Characters of `SKILL.md` shown per shortlisted candidate. |
| `timeout` | `10.0` | Wall-clock budget for one routing decision. |
| `suggest_chars` | `4000` | Requests longer than this are left alone. |
| `model` / `base_url` | `jev-latest` / TypeSafe API | Endpoint overrides. |
| `roster_dir` | `<hermes home>/skills` | Where the roster is read from. |
| `cache_path` | `<hermes home>/plugins/typesafe-skill-router/cache.json` | Answers are cached by request. |
| `log_path` | `<hermes home>/logs/typesafe-skill-router.log` | One line per routed turn. |

Thresholds live in code, and the answers are cached, so re-tuning them costs nothing: change a
number, replay the same requests, compare. Slash commands are never routed, and multi-part
(multimodal) messages are left alone.

## What leaves your machine

Routing is a network call to a third-party service, so here is the whole of it:

- **Sent:** the request text of the current turn, the names and one-line descriptions of your
  installed skills (in chunks of `chunk`), plus — for the top few candidates only — their full
  description and the first `excerpt` characters of `SKILL.md`.
- **Never sent:** conversation history, files, memory, credentials, tool output, the system
  prompt, or anything from previous turns. `recent_context` is sent empty.
- **Kept locally:** the roster scan, the thresholds, the shortlist, the cache, the log.

Turn it off at any time with `hermes typesafe-skill-router off` (or `enabled: false`).

## Cost and latency

Measured on one machine with a 292-skill roster: **~0.6–1.2 s per routed turn**, **~$0.001 per
request**, 3 API calls (2 chunks + the shortlist). Output tokens are not negligible — a
240-option `Choice` returns a 240-number distribution, so budget for them.

The vendor publishes an agent-level effect for the same idea (315 graded turns, block placed in
the system prompt): wrong skill loads 16.8% → 7.3%, needless loads 9.8% → 4.0%, 37 turns fixed
against 7 broken. Treat that as direction from *their* roster, not as a result from yours.

## How it works

Two requests, thresholds in code:

1. **Wide.** One `Choice` per chunk of `chunk` skills over the same 60-character index lines the
   model sees, each chunk also offering `none_of_these`; plus three `Noul` judgments on the
   request (does it act on the user's own material / does it follow a documented procedure /
   would prose alone satisfy it). The gate is the mean of those three, with the third inverted.
2. **Narrow.** One `Choice` over the top `shortlist` plus `none_of_these`, and one `Noul` per
   candidate: *does this skill do the specific thing the request asks for?*

A chunk cut off by `P(none_of_these) >= 0.50` nominates nobody, except the best chunk, so a
shortlist is never empty when something fits. Candidates are ranked by `(-probability, name)`,
which keeps replays and cache keys bit-stable when the probabilities tie at `0.0`. Stages are
told apart by the payload state, never by question names, because with a chunked roster the gate
judgments ride the first chunk only.

## Commands

```
hermes typesafe-skill-router on        # enable routing
hermes typesafe-skill-router off       # stop (the hook stays loaded, it just stays quiet)
hermes typesafe-skill-router status    # settings, roster, cache, key presence
hermes typesafe-skill-router suggest "queue the new Burial record on the kitchen speaker"
hermes typesafe-skill-router check [--live]
```

## Development

```bash
python -m pytest              # offline: no key, no network, no writes to your real log
hermes plugins validate .     # the same gate catalog admission runs
```

The tests drive the real router with a scripted client that returns real `Response` objects, so
chunk filtering, tie-breaking and the thresholds are exercised exactly as they run live.

MIT — see `LICENSE`.
