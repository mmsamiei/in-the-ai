# Agent handoff

Read README.md, docs/product.md, docs/architecture.md and docs/operations.md
before changing behavior. This repository is the durable specification; do not
assume another agent has the original chat. Explicit new user instructions take
precedence. Persist accepted changes in the corresponding executable files.

## Essential requirements

- Personal AI news collector with fully automatic public Persian output in
  @in_the_ai via @ai_khabar_bot. Broad coverage of relatively important events.
- Sources: Simon Willison LLMs, Google Research, BAIR, TechCrunch AI,
  OpenAI News and Hugging Face Blog (not Daily Papers).
- Discover the 50 top-ranked Hacker News stories on each cycle using its official
  API. Classify unseen IDs for AI relevance, ingest relevant links or self-posts,
  and persist seen IDs; use the existing event deduplication before publishing.
- Fluent conversational Persian with as many paragraphs as needed for clarity.
  Readability and narrative flow take priority over imitation.
  Natural literary devices/humor, without a mandatory narrative template or
  fabricated personal experiences.
- Every paragraph MUST begin with a Persian word for Telegram RTL: no initial
  English name, number, emoji or punctuation. Example: «شرکت Airbnb».
- Keep sources, times and uncertainty. Updates reply to the original event;
  duplicates do not create new posts. Validate before publication.
- The user approved systemd scheduling every fifteen minutes. Use ai-news.timer
  and ai-news.service (templates in deploy/). Do not add a second scheduler.
- Inference is pinned to gpt-6.1-terra with Light/low reasoning in inference.json.

## Sources of truth

| Item | File |
| --- | --- |
| Product decisions | docs/product.md |
| Selection instructions | prompts/selection.txt |
| Writing instructions | writing-prompt.txt |
| Factual check instructions | prompts/verification.txt |
| Deterministic writing checks | text_rules.py |
| Provider routing | inference.json, inference.py |
| Source URLs | sources.json |
| Local token/channel/database settings | .env; template example.env |
| News/delivery memory | SQLite at AI_NEWS_DATABASE_PATH |
| Prepared recurring task | scheduled-task-prompt.txt |

Inference receives assembled prompts/database context, not this file or the
whole chat. Documentation alone does not change runtime behavior. Synchronize
actual prompts and configuration whenever a requirement changes.

## Working and validating

Run `python3 -m unittest -v` after behavioral changes. Keep tests offline with
temporary databases. Live publication is authorized through the application
publisher; do not post arbitrary diagnostics or demo drafts. Secrets, database
and generated outputs must never enter Git or logs. Read example.env for key
names, rather than displaying .env. Never pass Telegram credentials to inference.

Uncertain sends must not be retried blindly. Preserve message IDs, event history
and channel binding across migrations. Use the provider-neutral generate(prompt,
schema) contract. Switching the development agent needs this handoff; switching
the inference backend additionally requires the documented adapter protocol.
