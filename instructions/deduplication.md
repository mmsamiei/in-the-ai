# Mandatory database check immediately before each publication

Read this contract on every cycle. Perform it for EVERY proposed send, including
old queued drafts and replies, after writing the final text and before committing
its delivery as sending. Earlier decisions, session memory, HN seen IDs and a
claim that the database was checked are not substitutes for fresh SQL queries.
Repeat after any material revision and after any other message is sent.

## Search the complete history

1. Query drafts LEFT JOIN deliveries and events across the WHOLE database, not
   only recent events or the last N rows. Include source URLs, event titles and
   facts, draft bodies, parent draft IDs and both recorded Telegram message IDs.
   A confirmed delivery or draft.telegram_message_id is publication evidence.
   Inspect sending/uncertain deliveries too; unresolved related sends block a
   potentially duplicate send. An article in the inbox alone is not a publication.
2. Normalize the candidate and stored source URLs consistently for comparison:
   lowercase hostname, ignore http/https and a leading www., remove fragments
   and trailing path slash, remove only known tracking keys (utm_*, fbclid,
   gclid); retain semantic parameters such as id and v and sort remaining query
   pairs. Keep path case and meaningful parameters. Check the original URL and
   safely resolved redirect/canonical aliases when available; domain lookalikes
   are not aliases. Compare against all historical draft URLs, not just articles
   with the same source ID. An exact normalized published URL blocks a NEW post.
3. Independently search for the same story under DIFFERENT links and languages.
   Extract the organization, model/project name and version, paper/study name,
   specific event or claim, dates and distinctive numbers. Run parameterized SQL
   searches over event titles/facts, draft bodies and article/version metadata
   using multiple English and Persian name variants and discriminative terms.
   Normalize Persian ی/ک variants and spacing in memory when useful. Read the
   bodies and facts of matching published posts; lexical similarity alone is not
   a decision. Search all history without an age cutoff, and record queries and
   actual results even when no match exists. New wording, a different title,
   article hash, source domain or observation date does not make a new event.

## Decide using the prior messages

- No related published or unresolved send, and genuinely distinct event: new.
- Same event and no material new facts: duplicate; do not send. Link the decision
  to the existing event. Do not create another event just to reintroduce it.
- Same event with material new source-supported facts: update, reply to the
  earliest confirmed post for that event. Record the exact added facts AND why
  they are absent from prior posts. A new source or extra explanation alone is
  not an update. Same-URL updates require this evidence too.
- If history is inconsistent (multiple events/posts already represent the same
  story), consider ALL of them and use the earliest confirmed original for a
  valid update. Preserve previous rows/message IDs; do not silently merge or
  delete history. If unsure or search fails, hold and do not send.

## Persist evidence BEFORE the send

Create this additive audit table if absent, using SQLite transactions:

```sql
CREATE TABLE IF NOT EXISTS publication_checks (
  id INTEGER PRIMARY KEY,
  draft_id INTEGER NOT NULL REFERENCES drafts(id),
  checked_at TEXT NOT NULL,
  result TEXT NOT NULL CHECK(result IN ('new','update','duplicate','hold')),
  details TEXT NOT NULL
);
```

Append a row for every checked candidate; never overwrite previous checks.
Use UTC checked_at and JSON details with these fields:
- candidate_url and normalized_url;
- url_matches: actual draft_id, event_id, message_id, source_url, delivery_state;
- similarity_searches: actual SQL query text, bound parameters and returned IDs;
- similar_posts: actual draft/event/message IDs, relationship and comparison
  against the stored body/facts for each plausible match;
- new_facts: supported facts absent from prior coverage (empty for duplicates);
- reply_to_message_id (null for new posts);
- reason explaining the final classification.

Empty results must be stored as empty lists, not skipped steps. Never fabricate
queries or matches. Also persist the editorial decision in decisions as usual;
record publication_check_id in drafts.verification JSON, preserving supported
and issues. Commit the audit row before the write-ahead delivery record. If the
check is missing, failed, stale, duplicate or hold, DO NOT call sendMessage.
Immediately before sending, recheck publication/delivery state and use the same
final body and source URL evaluated above. Read back the audit row to verify it
was saved. A factual verification does not replace this duplicate check.

The run report must list check IDs, classification and related message IDs for
published items and duplicate candidates, alongside source and send failures.
This is an instruction contract executed by the autonomous agent; it does not
provide an external enforcement barrier against direct Telegram API access.
