# 주말 아이들과 나들이 — 무료 클라우드 자동화

Render 서버나 OpenAI API를 쓰지 않습니다. GitHub Actions 표준 Linux runner + Gemini 2.5 Flash 무료 등급 + Pillow 정보 카드 + 기존 Zernio 연결을 사용합니다.

## 설정

Repository Secrets에 `GEMINI_API_KEY`, `ZERNIO_API_KEY`, `BOT_CONFIG`를 등록합니다. BOT_CONFIG는 INSTAGRAM_ACCOUNT_ID, TELEGRAM_ACCOUNT_ID, TELEGRAM_CONVERSATION_ID, APPROVER_ID를 담은 JSON 객체입니다. 사용자별 ID와 키는 공개 코드에 저장하지 않습니다.

Gemini 키는 **결제 계정이 연결되지 않은 무료 프로젝트**에서 발급해야 합니다. 무료 한도를 넘으면 중단하며 유료 모델로 우회하지 않습니다. 결제 프로젝트 키를 쓰면 이 코드도 과금될 수 있습니다. Google 무료 등급의 입력은 서비스 개선에 사용될 수 있으므로 공개 행사 정보만 전송합니다.

무료 프로젝트임을 확인한 뒤 Repository Variable `FREE_TIER_CONFIRMED=true`를 등록합니다.
Actions → Free family weekend bot → Run workflow → `check`로 연결 테스트를 실행합니다. 이 모드는 텔레그램 테스트 메시지와 Gemini 짧은 응답을 확인하며 인스타그램 글을 만들지 않습니다.

연결 테스트 성공 후 클라우드 예약을 활성화했습니다. 기존 맥 로컬 작업은 중지했습니다. 예약을 중지하려면 Repository Variable `BOT_ENABLED=false`로 설정하고, 재개하려면 `true`로 바꾸세요. `FREE_TIER_CONFIRMED=true`와 필수 Secrets는 계속 필요합니다.

## 실행 흐름

- 오전 7시 7분(한국 시간)부터 이번 주말 서울·경기 어린이 체험·공연·놀이 중심 축제 한 곳을 공식 자료로 조사합니다. 오전 10시 전까지 지연을 보완합니다.
- 공식 근거가 부족하면 초안을 만들지 않습니다. 다른 지역이나 일반 관광지로 임의 확대하지 않습니다.
- 본문은 즐길거리·연령·비용·예약·주차 등 확인된 정보를 담습니다. 독립적인 추가 검색으로 검토합니다.
- 1080×1350 고정 디자인 카드를 만들고 동일 이미지·본문을 텔레그램에 보냅니다.
- `승인 게시물ID`만 게시를 허용합니다. `보류 게시물ID`는 보류합니다.
- 등록한 사용자·대화의 새 답장만 인정하며, 편집된 메시지·오타·과거 답장·다른 게시물은 처리하지 않습니다.
- 승인 후 계정·문구·이미지가 달라지면 게시하지 않습니다. 최대 36시간 또는 행사 종료 전까지 승인할 수 있습니다.
- 승인 확인은 대략 15분 간격입니다. GitHub 예약은 지연·누락될 수 있으며 정각 실행을 보장하지 않습니다.

## 저장과 중복 방지

승인 상태는 별도의 플랫폼 없는 Zernio 초안에 저장합니다. 이 초안은 `family-weekend-free-v1` 태그와 '자동화 상태 기록 — 게시 대상 아님' 문구를 가지며 절대 게시하지 않습니다. 실제 Instagram 초안 ID와 해시만 이 상태 기록에 연결합니다. GitHub 캐시나 공개 저장소에 미게시 문구·개인 메시지를 저장하지 않습니다.

동시 실행은 GitHub concurrency로 차단합니다. 게시 직전 상태를 먼저 저장하며 결과가 불명확한 게시 요청을 자동 재시도하지 않습니다. 생성 도중 실패한 날은 자동 재생성하지 않으므로 수동 확인이 필요합니다. 초안만 중복되는 경우에도 자동 게시 권한은 생기지 않습니다.

이전 Render용 `worker.py`는 공유 검증 함수와 기존 회귀 테스트용으로 남아 있으며 무료 workflow는 해당 파일의 유료 API 메서드를 실행하지 않습니다. 유료 Render Blueprint는 제거했습니다.

## 검증과 운영

`pip install -r requirements.txt && python -m unittest -v`

GitHub 공개 저장소 표준 runner 무료 범위, Zernio 연결 계정 2개·월 무료 메시지 범위를 유지하세요. 60일간 저장소 활동이 없으면 GitHub 예약이 꺼질 수 있으므로 상태 확인이 필요합니다. Gemini 무료 한도와 이용 가능 모델은 변경될 수 있습니다. 연결 테스트 없이 완전 작동한다고 간주하지 마세요.

카드는 사진이나 AI 일러스트가 아닌 디자인 정보 카드입니다. 최종 게시 전에 사용자가 내용과 이미지를 검토합니다.

공식 문서: [GitHub Actions](https://docs.github.com/en/billing/concepts/product-billing/github-actions), [Gemini 가격](https://ai.google.dev/gemini-api/docs/pricing), [Zernio 가격](https://docs.zernio.com/pricing).
