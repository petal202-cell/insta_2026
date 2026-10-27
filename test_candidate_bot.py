import datetime as dt
import unittest
import time
import copy
import json
from candidate_bot import selection, make_draft, CandidateBot, FLOW, TAG, display_date, display_period
from worker import KST, fingerprint
from unittest.mock import patch

class CandidateTests(unittest.TestCase):
    def test_readable_dates_and_period_semantics(self):
        self.assertEqual(display_date("2026-10-22T01:00:00Z"), "2026년 10월 22일(목) 10:00")
        self.assertEqual(display_date("2026-11-01T00:00:00+09:00", False), "2026년 11월 1일(일)")
        self.assertEqual(display_period("2026-11-02","2026-11-01"), "기간 정보 확인 필요")
        self.assertEqual(display_date("invalid"), "공식 안내 확인")
        c={"summary":"숲의 식물을 관찰하는 체험입니다.","title":"체험","audience":"초1~3","place":"서울","fee_label":"무료","grade_status":"explicit_match",
           "registration_start":"2026-10-22T10:00:00+09:00","registration_end":"2026-10-23T17:00:00+09:00",
           "event_start":"2026-11-01T00:00:00+09:00","event_end":"2026-11-30T00:00:00+09:00","checked_at":"2026-10-21","booking_url":"https://example.go.kr/book"}
        caption=make_draft(c)["caption"]
        self.assertNotIn("T10:",caption)
        self.assertNotIn("+09:00",caption)
        self.assertIn("개별 체험 날짜·시간",caption)

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

class ActivityTests(unittest.TestCase):
    def test_draft_rejects_placeholder(self):
        with self.assertRaisesRegex(ValueError,"activity description"):
            make_draft({})

    def test_activity_requires_exact_official_quotes(self):
        source="나뭇잎의 모양을 관찰하고 서로 다른 특징을 비교합니다. 겨울을 준비하는 나무의 변화를 알아보고 숲을 탐방합니다."
        quotes=["나뭇잎의 모양을 관찰하고 서로 다른 특징을 비교합니다.","겨울을 준비하는 나무의 변화를 알아보고 숲을 탐방합니다."]
        bot=CandidateBot({})
        bot.gemini=lambda *a,**kw:json.dumps({"quotes":quotes})
        result=bot.prepare_activity({"description":source})
        self.assertIn(quotes[0],result["summary"])
        bot.gemini=lambda *a,**kw:json.dumps({"quotes":[quotes[0],"나만의 나무 목걸이를 만드는 활동입니다."]})
        with self.assertRaises(ValueError):
            bot.prepare_activity({"description":source})

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
        with patch("candidate_bot.request"), patch.object(bot,"carousel_media",return_value=[{"type":"image","url":f"https://example.go.kr/{i}.png"} for i in range(5)]):
            bot.revise(ledger,message,"더 친근하게")
        self.assertEqual(len(updates),1)
        self.assertEqual(len(sent),7)
        self.assertEqual(len(remote["mediaItems"]),5)
        state=ledger["metadata"][TAG]
        self.assertEqual(state["phase"],"pending")
        self.assertIn(candidate["booking_url"],remote["content"])
        self.assertNotIn("팔로우하지 않아도",remote["content"])
        self.assertNotIn("게시물 댓글에",remote["content"])
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


class ProductionRegressionTests(unittest.TestCase):
    def test_image_only_details_are_rejected_before_selection(self):
        from candidate_bot import activity_source
        for detail in ("3. 상세내용 4. 주의사항", "3. 상세내용 ↵ ↵ 4. 주의사항 ► 주의문"):
            self.assertLess(len(activity_source({"description":detail})),40)

    def test_registration_open_does_not_expire_selection(self):
        stamp = dt.datetime.now(dt.timezone.utc)
        c = {"registration_start":(stamp-dt.timedelta(hours=2)).isoformat(),
             "registration_end":(stamp+dt.timedelta(days=2)).isoformat()}
        state={"phase":"choosing","batch":"test","choices":[c],
               "choicesAt":stamp.timestamp()-200,"choiceExpiresAt":stamp.timestamp()+3600}
        msg={"direction":"incoming","senderId":"42","message":"채택 test 1","createdAt":stamp.isoformat()}
        self.assertEqual(selection(msg,state,"42"),0)
        c["registration_end"]=(stamp-dt.timedelta(seconds=1)).isoformat()
        self.assertIsNone(selection(msg,state,"42"))

    def test_telegram_uses_inbox_not_publishing_quota(self):
        bot=CandidateBot({"TELEGRAM_ACCOUNT_ID":"tg","TELEGRAM_CONVERSATION_ID":"chat"})
        with patch.object(bot,"z",return_value={"success":True,"data":{"messageId":"m"}}) as api:
            bot.telegram("preview","https://example.go.kr/a.png")
        path,method,body=api.call_args.args
        self.assertEqual(path,"/inbox/conversations/chat/messages")
        self.assertEqual(body["attachmentType"],"image")

    def test_direct_link_does_not_create_dm_automation(self):
        bot=CandidateBot({})
        ledger={"metadata":{TAG:{"bookingDelivery":"direct_link"}}}
        with patch.object(bot,"z") as api:
            bot.ensure_dm(ledger,{})
        api.assert_not_called()


class SeongnamSwitchTests(unittest.TestCase):
    def candidate(self, **changes):
        from candidate_bot import ACTIVE_SOURCE, SELECTION_POLICY
        c={"id":"seongnam-1","source":ACTIVE_SOURCE,"selection_policy":SELECTION_POLICY,
           "candidate":True,"registration_mode":"required","registration_start":"2026-10-28T09:00:00+09:00",
           "registration_end":"2026-10-30T18:00:00+09:00","event_start":"2026-11-01","event_end":"2026-11-02",
           "source_url":"https://www.seongnam.go.kr/pm010201/1","booking_url":None,
           "description":"나뭇잎의 모양을 관찰하고 서로 다른 특징을 비교합니다. 겨울을 준비하는 나무의 변화를 알아보고 숲을 탐방합니다.",
           "summary":"나뭇잎의 모양을 관찰하고 서로 다른 특징을 비교합니다.",
           "title":"성남 체험","audience":"누구나","grade_status":"needs_review",
           "place":"성남시청","fee_label":"무료","checked_at":"2026-10-27T12:00:00+09:00"}
        return {**c,**changes}
    def test_only_tomorrow_registration(self):
        from candidate_bot import active_candidate
        now=dt.datetime(2026,10,27,12,tzinfo=KST)
        self.assertTrue(active_candidate(self.candidate(),now))
        for changes in ({"registration_start":"2026-10-27T09:00:00+09:00"},{"registration_start":"2026-10-29T09:00:00+09:00"},{"source":"seoul"},{"source_url":"https://example.com"}):
            self.assertFalse(active_candidate(self.candidate(**changes),now))
    def test_weekend_to_next_month_window(self):
        from candidate_bot import active_candidate,seongnam_window
        now=dt.datetime(2026,10,27,12,tzinfo=KST)
        self.assertEqual(seongnam_window(now),(dt.date(2026,10,31),dt.date(2026,11,30)))
        for day,expected in (("2026-10-30",False),("2026-10-31",True),("2026-11-30",True),("2026-12-01",False)):
            c=self.candidate(registration_mode="not_listed",registration_start=None,registration_end=None,event_start=day,event_end=day)
            self.assertEqual(active_candidate(c,now),expected)
    def test_no_registration_draft_has_event_source_not_seoul_or_signup_dates(self):
        c=self.candidate(registration_mode="not_listed",registration_start=None,registration_end=None)
        caption=make_draft(c)["caption"]
        self.assertIn(c["source_url"],caption)
        self.assertIn("성남시청",caption)
        for word in ("신청 시작:","신청 마감:","서울시 공공서비스예약","하트","댓글"):
            self.assertNotIn(word,caption)
    def test_seoul_pending_draft_is_paused(self):
        bot=CandidateBot({"ZERNIO_API_KEY":"test","INSTAGRAM_ACCOUNT_ID":"ig","TELEGRAM_ACCOUNT_ID":"tg","TELEGRAM_CONVERSATION_ID":"c","APPROVER_ID":"42"})
        bot.ledgers=lambda:[{"metadata":{TAG:{"flow":FLOW,"phase":"pending","choices":[{"id":"S1"}]}}}]
        with patch.object(bot,"check") as check,patch.object(bot,"z") as api:
            bot.run("poll")
            check.assert_not_called()
            api.assert_not_called()
    def test_day_only_selection_deadline_includes_last_day(self):
        from candidate_bot import selection_deadline
        expected=dt.datetime(2026,11,1,23,59,59,tzinfo=KST).timestamp()
        self.assertEqual(selection_deadline({"event_end":"2026-11-01"}),expected)

if __name__=="__main__":
    unittest.main()
