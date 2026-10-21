import copy
import datetime as dt
import time
import unittest
from unittest.mock import patch
from free_bot import Bot, TAG, approval, revision_request, GeminiTransientError
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
        self.fail_publish = False
        self.bot.telegram = lambda *args: None
        def api(path, method='GET', body=None):
            if path.startswith('/inbox/'):
                return {'messages': [self.message]}
            if method == 'PUT' and path == '/posts/ledger':
                return {'post': {'_id': 'ledger', **body}}
            if method == 'PUT':
                self.assertEqual(self.ledger['metadata'][TAG]['phase'], 'publishing')
                self.publish.append(body)
                if self.fail_publish:
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
        self.fail_publish = True
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

    def test_revision_request_bound_to_owner_and_current_preview(self):
        msg = {**self.message, 'message': '수정 post 체험을 더 자세히 써줘'}
        self.assertEqual(revision_request(msg, self.state, '42'), '체험을 더 자세히 써줘')
        for change in [{'senderId': 'other'}, {'message': '수정 wrong 요청'},
                       {'message': '수정 post '}, {'isEdited': True},
                       {'createdAt': '2000-01-01T00:00:00Z'}]:
            self.assertIsNone(revision_request({**msg, **change}, self.state, '42'))
        self.assertIsNone(revision_request(msg, {**self.state, 'phase': 'publishing'}, '42'))
        self.assertIsNone(revision_request(msg, {**self.state, 'lastCommandAt': time.time()+100}, '42'))
        self.assertIsNotNone(revision_request(msg, {**self.state, 'phase': 'held'}, '42'))

    def test_revision_failure_revokes_approval_and_does_not_repeat(self):
        self.bot.gemini = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('quota'))
        self.message['message'] = '수정 post 더 자세히'
        self.bot.check(self.ledger)
        self.assertEqual(self.ledger['metadata'][TAG]['phase'], 'revision_failed')
        self.bot.check(self.ledger)
        self.assertEqual(self.ledger['metadata'][TAG]['revision'], 1)
        self.message['message'] = '승인 post'
        self.bot.check(self.ledger)
        self.assertEqual(self.publish, [])

    def test_revision_changes_existing_draft_and_needs_new_approval(self):
        import json
        from worker import KST
        end = (dt.datetime.now(KST).date() + dt.timedelta(days=10)).isoformat()
        draft = {'available': True, 'event': '축제', 'eventEnd': end, 'dates': '이번 주말',
                 'place': '서울', 'activities': ['체험', '공연'], 'caption': '수정된 본문 ' * 100,
                 'sources': [{'url': 'https://example.go.kr/official', 'title': '공식 안내'}]}
        responses = iter([json.dumps(draft), '{"ok":true}'])
        self.bot.gemini = lambda *a, **kw: next(responses)
        updates = []
        def api(path, method='GET', body=None):
            if path == '/media/presign':
                return {'uploadUrl': 'https://upload.example', 'publicUrl': 'https://media.example/v2.png'}
            if path.startswith('/inbox/'):
                return {'messages': [self.message]}
            if path == '/posts/ledger' and method == 'PUT':
                return {'post': body}
            if method == 'PUT':
                updates.append(body)
                self.assertNotIn('publishNow', body)
                self.remote.update(content=body['content'], mediaItems=body['mediaItems'])
            return {'post': self.remote}
        self.bot.z = api
        self.message['message'] = '수정 post 체험을 자세히'
        with patch('free_bot.request'), patch('card.render_card', return_value=b'png'), patch.object(self.bot, 'review_draft', return_value=True):
            self.bot.check(self.ledger)
        state = self.ledger['metadata'][TAG]
        self.assertEqual(state['phase'], 'pending')
        self.assertEqual(state['postId'], 'post')
        self.assertEqual(state['revision'], 1)
        self.assertEqual(self.remote['content'], draft['caption'])
        self.assertEqual(len(updates), 1)
        # Approval sent before the new preview cannot publish the revised draft.
        self.message['message'] = '승인 post'
        self.bot.check(self.ledger)
        self.assertEqual(len(updates), 1)

    def test_transient_gemini_failure_is_retried_without_paid_fallback(self):
        import io
        import urllib.error
        response = b'{"candidates":[{"content":{"parts":[{"text":"ok"}]}}]}'
        self.bot.env['GEMINI_API_KEY'] = 'test-only'
        with patch('urllib.request.urlopen', side_effect=[
            urllib.error.HTTPError('https://example', 503, 'busy', {}, None), io.BytesIO(response)
        ]) as call, patch('free_bot.time.sleep'):
            self.assertEqual(self.bot.gemini('test'), 'ok')
            self.assertEqual(call.call_count, 2)
        with patch('urllib.request.urlopen', side_effect=urllib.error.HTTPError('https://example', 503, 'busy', {}, None)) as call, patch('free_bot.time.sleep'):
            with self.assertRaises(GeminiTransientError):
                self.bot.gemini('test')
            self.assertEqual(call.call_count, 3)

    def test_quota_failure_not_retried(self):
        import urllib.error
        self.bot.env['GEMINI_API_KEY'] = 'test-only'
        with patch('urllib.request.urlopen', side_effect=urllib.error.HTTPError('https://example', 429, 'quota', {}, None)) as call:
            with self.assertRaises(RuntimeError):
                self.bot.gemini('test')
            self.assertEqual(call.call_count, 1)

    def test_daily_transient_retries_reuse_ledger_and_stop_at_limit(self):
        now = dt.datetime(2026, 10, 21, 9, 7)
        ledger = {'_id': 'ledger', 'metadata': {TAG: {'day': '2026-10-21', 'phase': 'retry_wait', 'retryAt': 0, 'attempts': 1}}}
        def fail(*args):
            raise GeminiTransientError('503')
        self.bot.build = fail
        with self.assertRaises(GeminiTransientError):
            self.bot.make_daily(now, [ledger])
        self.assertEqual(ledger['metadata'][TAG]['phase'], 'retry_wait')
        self.assertEqual(ledger['metadata'][TAG]['attempts'], 2)
        ledger['metadata'][TAG]['retryAt'] = 0
        with self.assertRaises(GeminiTransientError):
            self.bot.make_daily(now, [ledger])
        self.assertEqual(ledger['metadata'][TAG]['phase'], 'error')
        self.assertEqual(ledger['metadata'][TAG]['attempts'], 3)
        self.bot.make_daily(now, [ledger])

    def test_recovery_never_retries_ambiguous_or_created_draft(self):
        now = dt.datetime(2026, 10, 21, 19, 0)
        for extra in ({'postId': 'exists'}, {'uncertainMutation': True}):
            ledger = {'_id': 'ledger', 'metadata': {TAG: {'day': '2026-10-21', 'phase': 'error', **extra}}}
            with patch.object(self.bot, 'build') as build:
                self.bot.make_daily(now, [ledger], recover=True)
                build.assert_not_called()

    def test_format_repair_retains_checks_and_uses_bounded_calls(self):
        import json
        good = {'event': '공식 행사', 'eventEnd': '2026-10-25', 'dates': '10.24~10.25',
                'place': '서울', 'caption': '확인된 내용 ' * 100, 'activities': ['체험', '공연'],
                'sources': [{'url': 'https://example.go.kr'}]}
        with patch.object(self.bot, 'gemini', return_value=json.dumps(good)) as gen:
            self.assertEqual(self.bot.complete_draft({'caption': '짧음'}), good)
            gen.assert_called_once()
        with patch.object(self.bot, 'gemini', return_value='{}') as gen:
            with self.assertRaises(RuntimeError):
                self.bot.complete_draft({})
            self.assertEqual(gen.call_count, 2)

    def test_official_review_requires_real_date_and_activity_quotes(self):
        import json
        url = 'https://example.go.kr/event'
        text = '2026년 10월 24일부터 25일까지 어린이 축제를 운영합니다. 어린이 만들기 체험과 가족 공연을 진행합니다. ' * 5
        evidence = [{'kind': 'date', 'url': url, 'quote': '2026년 10월 24일부터 25일까지 어린이 축제를 운영합니다.'},
                    {'kind': 'activity', 'url': url, 'quote': '어린이 만들기 체험과 가족 공연을 진행합니다.'}]
        self.bot.gemini = lambda *a, **kw: json.dumps({'ok': True, 'reason': '확인', 'evidence': evidence})
        with patch('free_bot.request', return_value=text.encode()):
            self.assertTrue(self.bot.review_draft({'sources': [{'url': url}]}, '2026-10-24~25'))
            evidence[1]['quote'] = '공식 본문에 존재하지 않는 근거 문장입니다.'
            self.assertFalse(self.bot.review_draft({'sources': [{'url': url}]}, '2026-10-24~25'))
        with patch('free_bot.request') as fetch:
            with self.assertRaises(RuntimeError):
                self.bot.review_draft({'sources': [{'url': 'https://untrusted.example/event'}]}, 'weekend')
            fetch.assert_not_called()

    def test_malformed_research_uses_structured_extraction(self):
        notes = '{"available": true, "caption": "unterminated'
        result = {'available': True, 'sources': [{'url': 'https://example.go.kr/event'}]}
        with patch.object(self.bot, 'gemini', return_value=notes), patch.object(self.bot, 'complete_draft', return_value=result) as repair:
            self.assertEqual(self.bot.research_draft('research'), result)
            repair.assert_called_once_with({'research_notes': notes})
        with patch.object(self.bot, 'gemini', return_value='{"available":false}'), patch.object(self.bot, 'complete_draft') as repair:
            self.assertEqual(self.bot.research_draft('research'), {'available': False})
            repair.assert_not_called()
