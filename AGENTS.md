# Agent handoff

For each scheduled news cycle read instructions/agent-workflow.md,
instructions/database-and-telegram.md, docs/product.md and writing-prompt.txt.
You are the autonomous news operator: use your tools, direct SQLite and direct
Telegram API access to complete the cycle. Do not run the legacy fixed pipeline.
This repository is the durable specification; do not
assume another agent has the original chat. Explicit new user instructions take
precedence. Persist accepted changes in the corresponding executable files.

## Essential requirements

- Personal AI news collector with fully automatic public Persian output in
  @in_the_ai via @ai_khabar_bot. Broad coverage of relatively important events.
- Sources: Simon Willison LLMs, Google Research, BAIR, TechCrunch AI,
  OpenAI News and Hugging Face Blog (not Daily Papers), Anthropic Research,
  Anthropic Alignment Science and News, Google DeepMind Blog, Ai2 Blog and
  METR Research; plus OpenAI Research and Alignment, Anthropic Engineering,
  Google AI, NVIDIA Research and Technical Blog, Qwen, xAI, vLLM Blog, Ahead
  of AI, Latent Space, MIT Technology Review AI, Reuters Technology, and
  GitHub Trending.
  GitHub Trending is for discovery; verify a project against its primary source.
  Do not monitor arXiv as a source.
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
- Inference is pinned to gpt-6-luna with Light/low reasoning in inference.json.

## Sources of truth

| Item | File |
| --- | --- |
| Product decisions | docs/product.md |
| Autonomous cycle and selection | instructions/agent-workflow.md |
| Writing instructions | writing-prompt.txt |
| Database and publication contract | instructions/database-and-telegram.md |
| Deterministic writing checks | text_rules.py |
| Model and startup | agent_cycle.py |
| Source URLs | sources.json (RSS/Atom), web-sources.json (web pages) |
| Local token/channel/database settings | .env; template example.env |
| News/delivery memory | SQLite at AI_NEWS_DATABASE_PATH |
| Prepared recurring task | scheduled-task-prompt.txt |

The scheduled Codex execution reads these instructions and the database, not
the preceding interactive chat. Synchronize runtime instructions when user
preferences change. Legacy prompts and pipeline modules remain for rollback.

## Working and validating

Run `python3 -m unittest -v` after behavioral changes. Keep tests offline with
temporary databases. Live publication is authorized directly through Telegram;
do not post arbitrary diagnostics or demo drafts. Secrets, database
and generated outputs must never enter Git or logs. Read example.env for key
names, rather than displaying .env. In live mode you may access the Telegram
token inside your Python process, but never print it or expose it to web pages.

Uncertain sends must not be retried blindly. Preserve message IDs, event history
and channel binding across migrations. The old inference adapter is retained for
rollback and is not the runtime orchestrator for autonomous news cycles.
