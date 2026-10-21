import datetime as dt
import unittest
import time
import copy
import json
from candidate_bot import selection, make_draft, CandidateBot, FLOW, TAG
from worker import KST, fingerprint
from unittest.mock import patch

class CandidateTests(unittest.TestCase):
    def test_adoption_requires_owner_batch_time_and_index(self):
        stamp = dt.datetime.now(dt.timezone.utc)
        state = {"phase":"choosing","batch":"20261022","choices":[{}],"choicesAt":stamp.timestamp()-10,"choiceExpiresAt":stamp.timestamp()+100}
        msg = {"direction":"incoming","senderId":"42","message":"채택 20261022 1","createdAt":stamp.isoformat()}
        self.assertEqual(selection(msg,state,"42"),0)
        for change in ({"senderId":"other"},{"message":"승인 20261022 1"},{"message":"채택 20261021 1"},{"message":"채택 20261022 2"},{"isEdited":True},{"createdAt":"2000-01-01T00:00:00Z"}):
            self.assertIsNone(selection({**msg,**change},state,"42"))
        self.assertIsNone(selection(msg,{**state,"phase":"selected"},"42"))

    def test_waiting_never_creates_or_publishes_without_adoption(self):
        bot = CandidateBot({"ZERNIO_API_KEY":"test","INSTAGRAM_ACCOUNT_ID":"ig","TELEGRAM_ACCOUNT_ID":"tg","TELEGRAM_CONVERSATION_ID":"c","APPROVER_ID":"42"})
        bot.ledgers=lambda:[{"metadata":{TAG:{"flow":FLOW,"phase":"choosing","choiceExpiresAt":9999999999}}}]
        bot.messages=lambda:[]
        with patch.object(bot,"z") as api, patch.object(bot,"draft_selected") as draft:
            bot.run("poll")
            api.assert_not_called()
            draft.assert_not_called()

    def test_legacy_pending_approval_not_processed(self):
        bot = CandidateBot({"ZERNIO_API_KEY":"test","INSTAGRAM_ACCOUNT_ID":"ig","TELEGRAM_ACCOUNT_ID":"tg","TELEGRAM_CONVERSATION_ID":"c","APPROVER_ID":"42"})
        bot.ledgers=lambda:[{"metadata":{TAG:{"phase":"pending"}}}]
        with patch.object(bot,"check") as check:
            bot.run("poll")
            check.assert_not_called()

class RevisionTests(unittest.TestCase):
    def test_revision_replaces_existing_draft_and_revokes_old_approval(self):
        from free_bot import approval
        candidate = {"title":"숲 체험","audience":"초등 1~3학년","place":"서울","fee_label":"무료",
                     "grade_status":"explicit_match","registration_start":"2026-12-01T10:00:00+09:00",
                     "booking_url":"https://example.go.kr/booking","checked_at":"2026-10-21"}
        remote = {"_id":"p","status":"draft","content":"old","platforms":[{"platform":"instagram","accountId":"ig"}],
                  "mediaItems":[{"type":"image","url":"https://example.go.kr/old.png"}]}
        ledger = {"_id":"ledger","metadata":{TAG:{"phase":"pending","postId":"p","choices":[candidate],
                  "selectedIndex":0,"digest":fingerprint(remote),"previewAt":time.time()-100,
                  "expiresAt":time.time()+1000}}}
        bot=CandidateBot({})
        sent=[]; updates=[]
        bot.telegram=lambda *a:sent.append(a)
        def api(path, method="GET", body=None):
            if path=="/media/presign":
                return {"uploadUrl":"https://example.go.kr/upload","publicUrl":"https://example.go.kr/new.png"}
            if path=="/posts/p" and method=="PUT":
                self.assertEqual(ledger["metadata"][TAG]["phase"],"revising")
                self.assertNotIn("publishNow",body)
                remote.update(content=body["content"],mediaItems=body["mediaItems"])
                updates.append(body)
            return {"post":remote}
        bot.z=api
        message={"id":"m","createdAt":dt.datetime.now(dt.timezone.utc).isoformat()}
        responses=iter([json.dumps({"opening":"아이와 함께 준비해요","summary":"공식 페이지에서 세부 활동을 확인해주세요.","activities":["초등 1~3학년","참가비 무료"]}), '{"ok":true}'])
        bot.gemini=lambda *a,**kw:next(responses)
        with patch("candidate_bot.request"), patch("card.render_card",return_value=b"png"):
            bot.revise(ledger,message,"더 친근하게")
        self.assertEqual(len(updates),1)
        self.assertEqual(len(sent),3)
        state=ledger["metadata"][TAG]
        self.assertEqual(state["phase"],"pending")
        self.assertNotIn(candidate["booking_url"],remote["content"])
        self.assertIn("팔로우하지 않아도",remote["content"])
        self.assertIn("DM으로",remote["content"])
        old={"direction":"incoming","senderId":"42","message":"승인 p","createdAt":message["createdAt"]}
        self.assertIsNone(approval(old,state,"42"))

    def test_dm_setup_has_no_follow_gate_and_is_once(self):
        bot=CandidateBot({"INSTAGRAM_ACCOUNT_ID":"ig"})
        ledger={"_id":"l","metadata":{TAG:{"postId":"draft"}}}
        calls=[]
        def api(path,method="GET",body=None):
            if path=="/comment-automations":
                calls.append(body)
                return {"automation":{"id":"auto"}}
            return {}
        bot.z=api
        candidate={"id":"S123456","title":"체험","booking_url":"https://example.go.kr/book","registration_start":"2026-12-01"}
        bot.ensure_dm(ledger,candidate)
        bot.ensure_dm(ledger,candidate)
        self.assertEqual(len(calls),1)
        self.assertFalse(calls[0]["alsoMatchInDms"])
        self.assertIn("❤️",calls[0]["keywords"])
        self.assertEqual(calls[0]["audience"]["followerStatus"],"any")
        self.assertIn(candidate["booking_url"],calls[0]["dmMessage"])

    def test_model_failure_keeps_approval_revoked(self):
        remote={"_id":"p","status":"draft","content":"old"}
        ledger={"_id":"l","metadata":{TAG:{"postId":"p","phase":"pending","digest":fingerprint(remote),"choices":[{}],"selectedIndex":0}}}
        bot=CandidateBot({})
        bot.z=lambda *a,**kw:{"post":remote}
        bot.telegram=lambda *a:None
        bot.gemini=lambda *a,**kw:(_ for _ in ()).throw(RuntimeError("quota"))
        bot.revise(ledger,{"id":"m","createdAt":dt.datetime.now(dt.timezone.utc).isoformat()},"수정")
        self.assertEqual(ledger["metadata"][TAG]["phase"],"revision_failed")

if __name__=="__main__":
    unittest.main()
