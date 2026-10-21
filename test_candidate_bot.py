import datetime as dt
import unittest
from candidate_bot import selection, make_draft, CandidateBot, FLOW, TAG
from worker import KST
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

if __name__=="__main__":
    unittest.main()
