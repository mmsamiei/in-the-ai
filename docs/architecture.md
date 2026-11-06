# Architecture and inference portability

The application owns persistence, validation, event links and Telegram delivery.
The model owns selection, event matching, drafting and a separate factual check.
Changing providers must not bypass application checks.

## Modules

| Module | Responsibility |
| --- | --- |
| config.py | Literal .env, environment overrides, SQLite path |
| collect.py, sources.json | RSS/Atom intake, versions, first-fetch baseline |
| content.py | Basic HTML extraction/feed fallback; records truncation/errors |
| process.py | Prompt assembly, output schemas, event/draft persistence |
| inference.py, inference.json | Provider-neutral generate(prompt, schema) |
| codex_runner.py | Existing isolated Codex subprocess adapter |
| text_rules.py | Nonempty text, size, Persian initials in each paragraph |
| publish.py | Footer, permission check, replies and delivery state |
| cycle.py | One complete run; no resident scheduler |

## Instructions in each inference

Selection uses `prompts/selection.txt` + `writing-prompt.txt` + JSON containing
article metadata, evidence and event history. Verification separately uses
`prompts/verification.txt` + metadata, evidence, draft and facts. Output contracts
are `DECISION_SCHEMA` and `CHECK_SCHEMA` in process.py.

Inference does not receive the full chat, AGENTS.md, .env or Telegram token.
AGENTS.md guides repository development/operation; it is not the inference prompt.
Durable product requirements are in docs/product.md.

## Switching the development agent

Give the new agent the repository and ask it to read AGENTS.md and the linked
documents. No transcript is required. If tooling does not auto-read AGENTS.md,
include that instruction explicitly. Transfer runtime state/credentials separately.

## Switching inference away from Codex

Default inference.json selects `codex`, model `gpt-6.1-terra`, reasoning_effort
`low` (Light in the UI), and a 240-second timeout. The adapter forwards explicit
--model and model_reasoning_effort options while ignoring user config. Both
drafting and factual checking use this configuration. Per-inference historical
model metadata is not recorded yet. The account login is unchanged.

Implement a small adapter and change configuration:

```json
{
  "backend": "command",
  "command": ["python3", "/absolute/path/to/your_adapter.py"],
  "timeout_seconds": 240,
  "pass_env": ["YOUR_PROVIDER_API_KEY"]
}
```

The command runs from the repository without a shell. Key values belong in .env
or process environment, never tracked configuration. Only explicit pass_env names
and basic runtime environment are passed. Never include TELEGRAM_BOT_TOKEN.
The generic interface is implemented; a specific OpenRouter/other-agent adapter
is not. A development-agent switch alone does not change the inference backend.

The adapter reads one stdin JSON object:

```json
{"protocol_version": 1, "prompt": "assembled prompt", "schema": {"type": "object"}}
```

Return one JSON object matching the supplied schema on stdout, without fences or
logs. Use stderr for diagnostics, nonzero exit for failure. Never log credentials.
Raw stderr of failing custom commands is not persisted. Existing application
validation and factual checks still run. General-purpose JSON Schema validation
is not implemented; expected decision/check fields have application validation.
Use structured generation when supported. Do not give tools/publication access
to inference. Run offline tests and a local sample before publishing with a new backend.

## Persistence and limits

Tables separate articles/versions, fetch logs, events, decisions, drafts, errors,
delivery attempts and channel binding. The opening message was separately tracked
in announcements. Sending/sent/uncertain/failed/retry states prevent blind retries.

Context includes the 200 most recently updated events. HTML extraction is basic.
Factual checking is a separate call to the same model and can miss mistakes.
Formatting failures leave items for retry; automatic corrective rewriting is not
implemented. SQLite state, including message IDs, must survive provider changes.
