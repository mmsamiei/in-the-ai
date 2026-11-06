import json
import unittest
from unittest.mock import Mock

from test_process import EventFixture
from publish import DeliveryError, bind_channel, initialize_delivery, payload_for, publish_one


class DeliveryTests(EventFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        initialize_delivery(self.db)

    def draft(self, action='new', event_id=None):
        from process import process_one
        process_one(self.db, self.row(str(self.db.total_changes)), self.model(self.decision(action, event_id)))
        return self.db.execute('SELECT id,parent_draft_id,body,source_url,verification FROM drafts ORDER BY id DESC LIMIT 1').fetchone()

    def test_reply_uses_original_telegram_message_and_resend_is_skipped(self):
        root = self.draft()
        api = Mock()
        api.call.return_value = {'message_id': 90, 'chat': {'id': -100123}}
        self.assertEqual(publish_one(self.db, root, -100123, api), 'sent')
        self.assertEqual(publish_one(self.db, root, -100123, api), 'sent')
        self.assertEqual(api.call.call_count, 1)
        update = self.draft('update', 1)
        api.call.return_value = {'message_id': 91, 'chat': {'id': -100123}}
        publish_one(self.db, update, -100123, api)
        self.assertEqual(api.call.call_args.args[1]['reply_parameters'],
                         {'message_id': 90, 'allow_sending_without_reply': False})

    def test_source_link_preview_is_enabled(self):
        draft = self.draft()
        payload = payload_for(self.db, draft, -100123)
        self.assertEqual(payload['link_preview_options'],
                         {'is_disabled': False, 'url': draft[3]})

    def test_unknown_outcome_is_not_retried(self):
        draft = self.draft()
        api = Mock()
        api.call.side_effect = DeliveryError('Timeout', uncertain=True)
        with self.assertRaises(DeliveryError):
            publish_one(self.db, draft, -100123, api)
        self.assertEqual(publish_one(self.db, draft, -100123, api), 'uncertain')
        self.assertEqual(api.call.call_count, 1)
        self.assertIsNone(self.db.execute('SELECT telegram_message_id FROM drafts').fetchone()[0])

    def test_unpublished_parent_blocks_update(self):
        self.draft()
        update = self.draft('update', 1)
        with self.assertRaises(ValueError):
            publish_one(self.db, update, -100123, Mock())
        self.assertEqual(self.db.execute('SELECT count(*) FROM deliveries').fetchone()[0], 0)

    def test_rate_limit_is_deferred_without_blocking_sleep(self):
        draft = self.draft()
        api = Mock()
        api.call.side_effect = DeliveryError('Too many requests', retry_after=60)
        with self.assertRaises(DeliveryError):
            publish_one(self.db, draft, -100123, api)
        self.assertEqual(publish_one(self.db, draft, -100123, api), 'deferred')
        self.assertEqual(api.call.call_count, 1)

    def test_database_cannot_switch_channel(self):
        bind_channel(self.db, -100123)
        with self.assertRaises(ValueError):
            bind_channel(self.db, -100999)

    def test_unverified_draft_is_not_sent(self):
        draft = list(self.draft())
        draft[-1] = json.dumps({'supported': False, 'issues': ['bad claim']})
        with self.assertRaises(ValueError):
            payload_for(self.db, draft, -100123)
