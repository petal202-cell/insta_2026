"""Candidate selection and separate publishing approval over Telegram."""
import datetime as dt
import json
import time
import urllib.parse
from free_bot import Bot, TAG
from worker import KST, request, fingerprint

FEED = "https://raw.githubusercontent.com/petal202-cell/kids-weekend-api/main/data/candidates.json"
FLOW = "candidate-selection-v1"

def selection(message, state, owner):
    if state.get("phase") != "choosing" or message.get("direction") != "incoming":
        return None
    if str(message.get("senderId")) != str(owner) or message.get("isEdited") or message.get("isDeleted"):
        return None
    try:
        stamp = dt.datetime.fromisoformat(message["createdAt"].replace("Z", "+00:00")).timestamp()
        if stamp <= state.get("choicesAt", float("inf")) or stamp > state["choiceExpiresAt"]:
            return None
        parts = message.get("message", "").strip().split()
        if len(parts) != 3 or parts[:2] != ["채택", state["batch"]]:
            return None
        index = int(parts[2]) - 1
        return index if 0 <= index < len(state["choices"]) else None
    except (KeyError, ValueError, TypeError):
        return None

def make_draft(candidate):
    # Deterministic copy of the official API fields; no invented sessions or activities.
    c = candidate
    lines = [
        "📝 신청 시작 전에 확인해두세요!",
        c["title"], "",
        "👧 대상: " + c["audience"],
        "📍 장소: " + c["place"],
        "💰 비용 안내: " + c["fee_label"],
        "🗓 접수 시작: " + c["registration_start"],
        "접수 종료: " + str(c.get("registration_end") or "공식 안내 확인"),
        "운영기간: " + str(c.get("event_start") or "미확인") + " ~ " + str(c.get("event_end") or "미확인"),
        "", "어떤 활동인가요?",
        c.get("summary", "구체적인 활동 내용은 공식 예약 페이지를 확인해주세요."),
        "", "⚠️ 운영기간은 개별 수업 날짜와 다를 수 있습니다. 토·일 회차, 대상 학년, 보호자 동반, 실제 금액과 예약 조건은 공식 페이지에서 확인해주세요.",
        "접수 시작 안내이며 잔여석이나 예약 성공을 보장하지 않습니다.",
        "대상 확인: " + ("초등 저학년과 겹치는 대상이 명시돼 있습니다." if c["grade_status"] == "explicit_match" else "초1~3 참여 가능 여부를 추가 확인해야 합니다."),
        "", "🔗 공식 예약 안내", c["booking_url"],
        "", "다음 체험 소식도 보고 싶다면 @sglide_h를 팔로우해주세요 🌿",
        "출처: 서울특별시 공공서비스예약 · " + c["checked_at"][:10],
        "이미지: 직접 제작한 정보 카드", "#초등체험 #초등저학년 #박물관교육 #서울아이와가볼만한곳"
    ]
    caption = "\n".join(lines)
    if len(caption) > 2100:
        raise ValueError("Caption too long")
    return {"event": c["title"][:45], "headline": "신청 오픈 예정 · 초등 체험 후보",
            "dates": "접수 시작 " + c["registration_start"][:16].replace("T", " "),
            "place": c["place"][:40],
            "activities": [("대상 " + c["audience"])[:30], ("비용 " + c["fee_label"])[:30]],
            "caption": caption}

class CandidateBot(Bot):
    def messages(self):
        query = urllib.parse.urlencode({"accountId": self.env["TELEGRAM_ACCOUNT_ID"], "limit": 100, "sortOrder": "desc"})
        return self.z("/inbox/conversations/" + self.env["TELEGRAM_CONVERSATION_ID"] + "/messages?" + query).get("messages", [])

    def offer(self, ledgers, now):
        day = now.date().isoformat()
        existing = [p for p in ledgers if p.get("metadata", {}).get(TAG, {}).get("flow") == FLOW
                    and p["metadata"][TAG].get("day") == day]
        if existing:
            return
        feed = request(FEED)
        checked = dt.datetime.fromisoformat(feed["checked_at"]).timestamp()
        if not -300 <= time.time() - checked < 30*3600 or feed.get("sample_is_not_complete", True):
            raise RuntimeError("Full candidate feed is missing or stale")
        choices = []
        for c in feed.get("candidates", []):
            begin = dt.datetime.fromisoformat(c["registration_start"]).timestamp()
            if time.time() < begin <= time.time() + 7*86400 and c.get("candidate") and c.get("booking_url"):
                choices.append(c)
        choices.sort(key=lambda c: (c["registration_start"], c["id"]))
        choices = choices[:8]
        batch = day.replace("-", "")
        expires = min(time.time()+24*3600, min((dt.datetime.fromisoformat(c["registration_start"]).timestamp() for c in choices), default=time.time()+24*3600))
        state = {"flow": FLOW, "day": day, "batch": batch, "phase": "offering", "choices": choices,
                 "choiceExpiresAt": expires}
        ledger = self.z("/posts", "POST", {"isDraft": True, "tags": [TAG],
            "content": "후보 선택 상태 기록 " + day + " — 게시 대상 아님", "metadata": {TAG: state}})["post"]
        if not choices:
            self.telegram("📋 " + day + " · 앞으로 7일 내 신청 시작 조건에 맞는 후보가 없습니다. 초안을 자동 작성하지 않습니다.")
            self.save(ledger, phase="no_candidates")
            return
        self.telegram("📋 " + day + " · 신청 오픈 예정 후보 " + str(len(choices)) + "곳\n초1~3 대상 여부가 불명확한 후보는 표시했습니다. 채택 후 초안을 만들고, 별도 승인 후 게시합니다.")
        for index, c in enumerate(choices, 1):
            self.telegram(f"{index}. {c['title']}\n대상: {c['audience']}\n대상 검증: {c['grade_status']}\n장소: {c['place']}\n비용: {c['fee_label']}\n신청 시작: {c['registration_start']}\n운영기간: {c.get('event_start')} ~ {c.get('event_end')}\n{c['booking_url']}\n\n이 후보 채택:\n채택 {batch} {index}")
        self.telegram(f"선택 예시: 채택 {batch} 1\n하루 한 후보를 채택할 수 있습니다. 채택은 게시 승인이 아닙니다. 주말 회차·예약 조건은 원문 확인이 필요해요.")
        self.save(ledger, phase="choosing", choicesAt=time.time())

    def draft_selected(self, ledger, c):
        state = ledger["metadata"][TAG]
        from card import render_card
        draft = make_draft(c)
        image = render_card(draft, self.env.get("FONT_PATH", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"))
        upload = self.z("/media/presign", "POST", {"filename": state["batch"]+"-selection.png", "contentType": "image/png", "size": len(image)})
        request(upload["uploadUrl"], "PUT", image, raw=True)
        self.save(ledger, phase="creating_draft")
        post = self.z("/posts", "POST", {"isDraft": True, "content": draft["caption"],
            "mediaItems": [{"type": "image", "url": upload["publicUrl"]}],
            "platforms": [{"platform": "instagram", "accountId": self.env["INSTAGRAM_ACCOUNT_ID"]}]})["post"]
        self.save(ledger, phase="previewing", postId=post["_id"], draftData=draft,
                  expiresAt=min(time.time()+36*3600, dt.datetime.fromisoformat(c["registration_start"]).timestamp()))
        post = self.z("/posts/"+post["_id"])["post"]
        if post["status"] != "draft":
            raise RuntimeError("Unexpected draft state")
        self.telegram("📝 채택한 후보 초안 · " + c["title"], post["mediaItems"][0]["url"])
        self.telegram(post["content"])
        self.telegram(f"내용과 신청 조건을 검토한 뒤 게시하려면:\n승인 {post['_id']}\n\n보류:\n보류 {post['_id']}\n\n채택만으로 게시하지 않습니다. 신청 시작 전에 승인이 필요합니다.")
        self.save(ledger, phase="pending", digest=fingerprint(post), previewAt=time.time())

    def revise(self, ledger, message, instructions):
        # Do not route new API candidates into the legacy festival web-search rewriter.
        self.save(ledger, lastCommandAt=dt.datetime.fromisoformat(message["createdAt"].replace("Z", "+00:00")).timestamp())
        self.telegram("이 API 초안은 공식 자료 기반 고정 형식입니다. 현재 텔레그램 자동 수정은 지원하지 않아요. 여기서는 보류하고 Codex에서 수정해 새 미리보기를 받아주세요. 승인 없이 게시하지 않습니다.")

    def run(self, mode="daily"):
        for key in ("ZERNIO_API_KEY", "INSTAGRAM_ACCOUNT_ID", "TELEGRAM_ACCOUNT_ID", "TELEGRAM_CONVERSATION_ID", "APPROVER_ID"):
            if not self.env.get(key):
                raise RuntimeError("Missing configuration: " + key)
        ledgers = self.ledgers()
        for ledger in ledgers:
            state = ledger.get("metadata", {}).get(TAG, {})
            if state.get("flow") != FLOW:
                # Reconcile an already-started publication only; legacy pending approvals stay inactive.
                if state.get("phase") == "publishing":
                    Bot.check(self, ledger)
                continue
            if state.get("phase") == "choosing":
                if time.time() > state["choiceExpiresAt"]:
                    self.save(ledger, phase="selection_expired")
                    continue
                for message in sorted(self.messages(), key=lambda m: m.get("createdAt", ""), reverse=True):
                    index = selection(message, state, self.env["APPROVER_ID"])
                    if index is not None:
                        candidate = state["choices"][index]
                        # Claim first. Any uncertain draft/send failure requires manual review, never retry.
                        self.save(ledger, phase="selected", selectedIndex=index, selectionMessageId=message["id"])
                        try:
                            self.draft_selected(ledger, candidate)
                        except Exception:
                            self.save(ledger, phase="selection_failed")
                            self.telegram("⚠️ 채택한 후보의 초안 작성이 중단됐습니다. 중복 생성·게시를 막기 위해 자동 재시도하지 않아요. Codex에서 확인해주세요.")
                            raise
                        break
            else:
                self.check(ledger)
        now = dt.datetime.now(KST)
        if mode == "offer" or (mode == "daily" and 7 <= now.hour < 23):
            self.offer(ledgers, now)

if __name__ == "__main__":
    import sys
    CandidateBot().run(sys.argv[1] if len(sys.argv)>1 else "daily")
