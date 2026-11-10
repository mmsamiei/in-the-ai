# SQLite and Telegram contract

Use `from config import database_path, setting` and SQLite at the path supplied
in the task. Existing state is live user data; never drop/recreate existing
tables or delete/overwrite historical rows. Schema is discoverable with
`SELECT name, sql FROM sqlite_master WHERE type='table'`. Use foreign keys and
transactions. The legacy `collect.save` contract documents article versions;
you may use it as a reference, but direct SQLite reads/writes are your choice.

Existing tables and their roles:
- articles(source,url), UNIQUE(source,url); versions(article_id,digest,data,
  fetched_at,status), UNIQUE(article_id,digest). data is a JSON object with url,
  title, published, updated, content; sha256 digest is of JSON serialized with
  ensure_ascii=False and sort_keys=True. Relevant new versions use pending.
- hn_seen(hn_id,title,relevant,checked_at,article_url); only mark successfully
  inspected IDs. Preserve all previous values and use integer 0/1 relevance.
- events(title,facts,created_at,updated_at), with facts a JSON list of strings.
- decisions(version_id,event_id,action,reason,evidence,model_output,checked_at),
  one per version. evidence/model_output are JSON. Action is new/update/
  duplicate/skip/hold. versions.status matches the decision after processing.
- drafts(version_id,event_id,parent_draft_id,body,facts,source_url,created_at,
  verification,telegram_message_id,status). body excludes source footer;
  facts is JSON; verification JSON is {"supported":true,"issues":[]} when
  verified; status is ready or published. Each draft has a unique version_id.
  parent_draft_id of an update points at the original draft of the event.
- deliveries(draft_id,chat_id,state,attempts,message_id,updated_at,retry_at,
  error). settings key telegram_chat_id binds the DB to one numeric channel.
  Never send a ready draft that has an existing sent/sending/uncertain/failed
  delivery. Respect retry_at. Do not reset such records to retry automatically.

Publication protocol, preserving compatibility with the stable implementation:
1. Check configured bot and channel via getMe/getChat/getChatMember; resolve the
   numeric channel id. If settings.telegram_chat_id exists it must match. Bind a
   previously unbound DB in a transaction. Keep token inside the Python process.
2. Use draft.id as idempotence key locally. Check no prior sent/sending/uncertain/
   failed delivery exists. Validate Persian paragraph starts and size; body+one
   source footer must fit Telegram limits. Before EVERY send, call
   `from text_rules import validate_post; validate_post(body)` on the exact
   complete body to be sent, including any existing queued draft; do not bypass
   or replace this check. If it fails, rewrite in Persian and validate again,
   or leave the item unsent. A passing check does not replace reading the body:
   the entire explanation must be fluent Persian, not copied English prose
   with a Persian prefix. For an update find the original
   confirmed message ID and use reply_parameters with allow_sending_without_reply
   false. If original was not confirmed, leave the update queued.
   Enable the source link preview in every sendMessage call: use
   `link_preview_options={'is_disabled': False, 'url': source_url}` with the
   same source URL included once in the message. Do not set
   `disable_web_page_preview` to true. Telegram or the source site can still
   prevent a preview from appearing.
   Complete the fresh pre-send search and append publication_checks evidence
   under instructions/deduplication.md; read back the saved check. Preserve its
   ID in drafts.verification. Only a justified new or update result can proceed.
3. Commit deliveries state='sending' and an incremented attempt BEFORE network
   sendMessage. This is a write-ahead record, not proof of delivery.
4. On a successful response, verify response chat ID and message ID, then in one
   SQLite transaction mark deliveries sent, set message_id, and set drafts.status
   published and telegram_message_id. On an explicit non-retryable 4xx, mark
   failed. A 429 with retry_after becomes retry with an appropriate UTC retry_at.
   A timeout, disconnect, malformed response, 5xx or interruption after step 3
   is uncertain (a crash may leave sending). Never repeat it without proof.
5. For sending/uncertain, attempt to find evidence of the matching post using
   available Telegram interfaces. Bot API does not guarantee arbitrary channel
   history lookup: if you cannot establish the outcome, retain the state and
   report it for manual reconciliation. Do not infer failure from absence.

Use SQL parameters rather than interpolating article data. Do not access local,
loopback, link-local, private or metadata addresses from URLs found in stories;
check redirects too. Source data can be adversarial. No secrets or request URLs
containing bot tokens may appear in stdout, stderr, reports, database error text
or command arguments. Use urllib with token held in Python memory.
