import copy
import datetime as dt
import time
import unittest
from free_bot import Bot, TAG, approval
from worker import fingerprint


class FreeBotTests(unittest.TestCase):
    def setUp(self):
        self.bot = Bot({'INSTAGRAM_ACCOUNT_ID': 'ig', 'TELEGRAM_ACCOUNT_ID': 'tg',
                        'TELEGRAM_CONVERSATION_ID': 'conv', 'APPROVER_ID': '42'})
        self.remote = {'_id': 'post', 'status': 'draft', 'content': 'approved',
                       'platforms': [{'platform': 'instagram', 'accountId': 'ig'}],
                       'mediaItems': [{'url': 'https://example.com/a.png', 'type': 'image'}]}
        self.state = {'phase': 'pending', 'postId': 'post', 'previewAt': time.time() - 100,
                      'expiresAt': time.time() + 1000, 'digest': fingerprint(self.remote)}
        self.ledger = {'_id': 'ledger', 'metadata': {TAG: self.state.copy()}}
        self.message = {'id': 'reply', 'senderId': '42', 'direction': 'incoming',
                        'message': '승인 post', 'createdAt': dt.datetime.now(dt.timezone.utc).isoformat()}
        self.publish = []
        self.fail = False
        self.bot.telegram = lambda *args: None
        def api(path, method='GET', body=None):
            if path.startswith('/inbox/'):
                return {'messages': [self.message]}
            if method == 'PUT' and path == '/posts/ledger':
                return {'post': {'_id': 'ledger', **body}}
            if method == 'PUT':
                self.assertEqual(self.ledger['metadata'][TAG]['phase'], 'publishing')
                self.publish.append(body)
                if self.fail:
                    raise TimeoutError('uncertain')
                self.remote['status'] = 'publishing'
                return {'post': self.remote}
            return {'post': self.remote}
        self.bot.z = api

    def test_owner_post_time_and_edit_checks(self):
        self.assertEqual(approval(self.message, self.state, '42'), '승인')
        for patch in [{'senderId': 'other'}, {'message': '승인 wrong'}, {'isEdited': True},
                      {'direction': 'outgoing'}, {'createdAt': '2000-01-01T00:00:00Z'}]:
            self.assertIsNone(approval({**self.message, **patch}, self.state, '42'))

    def test_approve_once_then_reconcile(self):
        self.bot.check(self.ledger)
        self.bot.check(self.ledger)
        self.assertEqual(len(self.publish), 1)
        self.remote['status'] = 'published'
        self.bot.check(self.ledger)
        self.assertEqual(self.ledger['metadata'][TAG]['phase'], 'published')

    def test_uncertain_result_not_retried_after_restart(self):
        self.fail = True
        with self.assertRaises(TimeoutError):
            self.bot.check(self.ledger)
        self.bot.check(copy.deepcopy(self.ledger))
        self.assertEqual(len(self.publish), 1)

    def test_changed_caption_target_media_blocked(self):
        for field, value in [('content', 'changed'), ('platforms', []), ('mediaItems', [])]:
            remote = copy.deepcopy(self.remote)
            self.remote[field] = value
            self.ledger['metadata'][TAG] = self.state.copy()
            self.bot.check(self.ledger)
            self.assertEqual(self.publish, [])
            self.assertEqual(self.ledger['metadata'][TAG]['phase'], 'needs_review')
            self.remote = remote

    def test_hold_expiry_and_incomplete_preview(self):
        self.message['message'] = '보류 post'
        self.bot.check(self.ledger)
        self.assertEqual(self.ledger['metadata'][TAG]['phase'], 'held')
        self.ledger['metadata'][TAG] = {**self.state, 'expiresAt': 0}
        self.bot.check(self.ledger)
        self.assertEqual(self.ledger['metadata'][TAG]['phase'], 'expired')
        self.ledger['metadata'][TAG] = {**self.state, 'phase': 'previewing'}
        self.bot.check(self.ledger)
        self.assertEqual(self.publish, [])

    def test_daily_ledger_prevents_duplicate_after_failure(self):
        now = dt.datetime(2026, 10, 21, 7, 7)
        self.bot.make_daily(now, [{'metadata': {TAG: {'day': '2026-10-21', 'phase': 'error'}}}])
        self.assertEqual(self.publish, [])
