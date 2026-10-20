import copy
import datetime as dt
import json
import tempfile
import time
import unittest
from worker import Worker, approval, fingerprint


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.pending = {'postId': 'abc', 'status': 'pending', 'previewAt': 1000}
        self.msg = {'id': '1', 'message': '승인 abc', 'direction': 'incoming',
                    'senderId': '42', 'createdAt': '2026-10-20T12:00:00Z'}

    def test_only_matching_owner_and_post(self):
        self.assertEqual(approval(self.msg, self.pending, '42'), '승인')
        self.assertIsNone(approval(self.msg, self.pending, '43'))
        self.assertIsNone(approval({**self.msg, 'message': '승인 other'}, self.pending, '42'))
        self.assertIsNone(approval({**self.msg, 'direction': 'outgoing'}, self.pending, '42'))
        self.assertIsNone(approval({**self.msg, 'isEdited': True}, self.pending, '42'))

    def test_stale_preview_and_nonpending_blocked(self):
        self.assertIsNone(approval(self.msg, {**self.pending, 'previewAt': time.time() + 1000}, '42'))
        self.assertIsNone(approval(self.msg, {**self.pending, 'status': 'publishing'}, '42'))
        self.assertIsNone(approval(self.msg, {**self.pending, 'status': 'previewing'}, '42'))


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.worker = Worker({'DATA_DIR': self.temp.name, 'INSTAGRAM_ACCOUNT_ID': 'ig',
                              'TELEGRAM_ACCOUNT_ID': 'tg', 'TELEGRAM_CONVERSATION_ID': 'conv',
                              'APPROVER_ID': '42'})
        self.remote = {'content': 'Approved caption', 'status': 'draft',
                       'mediaItems': [{'url': 'https://example.com/a.png', 'type': 'image'}],
                       'platforms': [{'platform': 'instagram', 'accountId': {'_id': 'ig'}}]}
        self.pending = {'postId': 'abc', 'status': 'pending', 'previewAt': time.time() - 100,
                        'expiresAt': time.time() + 3600, 'digest': fingerprint(self.remote)}
        self.worker.put('post:abc', self.pending)
        self.calls = []
        self.messages = [{'id': '1', 'message': '승인 abc', 'senderId': '42', 'direction': 'incoming',
                          'createdAt': dt.datetime.now(dt.timezone.utc).isoformat()}]
        self.fail_publish = False
        def api(path, method='GET', body=None):
            if method == 'PUT':
                self.calls.append((path, body))
                self.assertEqual(self.worker.get('post:abc')['status'], 'publishing')
                if self.fail_publish:
                    raise TimeoutError('ambiguous')
                self.remote['status'] = 'publishing'
                return {'post': self.remote}
            if path.startswith('/inbox/'):
                return {'messages': self.messages}
            return {'post': self.remote}
        self.worker.z = api
        self.worker.telegram = lambda *args: None
        self.worker.notify_error = lambda *args: None

    def tearDown(self):
        self.worker.db.close()
        self.temp.cleanup()

    def test_approved_post_published_once_and_reconciled(self):
        self.worker.poll()
        self.worker.poll()
        self.assertEqual(len(self.calls), 1)
        self.remote['status'] = 'published'
        self.worker.poll()
        self.assertEqual(self.worker.get('post:abc')['status'], 'published')

    def test_caption_media_target_changes_block_publish(self):
        for field, value in [('content', 'Changed'), ('mediaItems', []), ('platforms', [])]:
            with self.subTest(field=field):
                remote = copy.deepcopy(self.remote)
                self.remote[field] = value
                self.worker.put('post:abc', self.pending)
                self.worker.poll()
                self.assertEqual(self.calls, [])
                self.assertEqual(self.worker.get('post:abc')['status'], 'needs_review')
                self.remote = remote

    def test_hold_and_expiry_never_publish(self):
        self.messages[0]['message'] = '보류 abc'
        self.worker.poll()
        self.assertEqual(self.worker.get('post:abc')['status'], 'held')
        self.worker.put('post:abc', {**self.pending, 'expiresAt': 0})
        self.worker.poll()
        self.assertEqual(self.worker.get('post:abc')['status'], 'expired')
        self.assertEqual(self.calls, [])

    def test_uncertain_publish_is_not_retried(self):
        self.fail_publish = True
        with self.assertRaises(TimeoutError):
            self.worker.poll()
        self.worker.poll()
        self.assertEqual(len(self.calls), 1)

    def test_preview_failure_is_not_approvable(self):
        self.worker.put('post:abc', {**self.pending, 'status': 'previewing'})
        self.worker.poll()
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
