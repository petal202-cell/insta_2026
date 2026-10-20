# 주말 아이들과 나들이 Instagram 승인 자동화

Render의 단일 Background Worker와 1GB 영구 디스크로 실행합니다. 맥북에 의존하지 않습니다.

## 동작

- 매일 한국 시간 오전 7시대 첫 실행에 이번 주말 서울·경기 축제 한 곳을 공식 출처로 검색합니다.
- 어린이 체험·공연·놀이, 비용·예약, 방문 팁을 담은 본문과 4:5 AI 일러스트를 생성하고 별도로 검토합니다.
- Zernio에 Instagram 초안으로 저장하고 텔레그램에 동일한 이미지와 본문을 보냅니다.
- 등록한 사용자만 `승인 게시물ID` 또는 `보류 게시물ID`로 결정합니다. 약 1분 간격으로 확인합니다.
- 승인 전 초안과 게시 시점의 계정·문구·이미지를 비교하고 다르면 게시하지 않습니다.
- 승인 유효기간은 최대 36시간, 행사 종료 시각 이전입니다. 날짜가 지난 초안은 새 검토가 필요합니다.
- 재시작·통신 오류로 게시 결과가 불분명하면 조회만 하며 자동 재시도하지 않습니다.
- 오전 7시대 내내 서버가 중단됐다면 해당 날짜 초안 생성은 건너뜁니다. 추후 수동 검토가 필요합니다.

## 배포 전 준비

`render.yaml`은 초기 `AUTOMATION_ENABLED=false`로 생성되며 실제 게시가 비활성 상태입니다.
Blueprint를 Render에 적용하고 아래 값을 Environment에 등록합니다. API 키는 채팅이나 GitHub에 넣지 마세요.

| 변수 | 용도 |
|---|---|
| OPENAI_API_KEY | 검색·본문·이미지 생성 및 검토, API 별도 과금 |
| ZERNIO_API_KEY | 기존 계정의 posts·media·messages 읽기/쓰기 권한 |
| INSTAGRAM_ACCOUNT_ID | 승인 대상 Instagram 계정 |
| TELEGRAM_ACCOUNT_ID | 알림을 받을 연결된 텔레그램 그룹 계정 |
| TELEGRAM_CONVERSATION_ID | 승인 메시지를 읽을 대화 ID |
| APPROVER_ID | 게시를 승인할 텔레그램 사용자 ID |

API 연결·초안 알림·승인 수신을 검증한 뒤 기존 로컬 작업을 중지하고 `AUTOMATION_ENABLED=true`로 전환합니다.
기존 로컬 초안·승인 파일은 자동 이관하지 않습니다. 기존 게시물을 재게시하지 않도록 제외 행사 기록을 확인해야 합니다.
기존 Zernio 초안이 있으면 이를 검토한 뒤 수동 처리하고 신규 클라우드 초안과 혼동하지 마세요.

## 비용과 운영

유료 `0.5c-512mb` worker 1개, 영구 디스크 1GB가 필요합니다. OpenAI 및 Zernio 비용은 별도입니다.
배포 적용 전에 Render Dashboard의 최신 요금을 확인하세요. 이 저장소를 올리는 것만으로 서버가 생성되지는 않습니다.
단일 인스턴스만 실행하세요. 같은 앱을 여러 서비스로 복제하면 중복 생성 위험이 있습니다.
장애는 Render 로그와 텔레그램을 확인합니다. 초안 생성 실패는 같은 날 자동 반복하지 않으므로 불필요한 API 비용을 막습니다.
계정 연결이 만료되면 Zernio에서 재연결이 필요합니다.

## 검증

Python 3.12+ 표준 라이브러리만 사용합니다. `python -m unittest -v`는 실제 게시 없이 가짜 API로 승인·보류·만료·변경·중복·불명확한 결과를 검사합니다.
실제 클라우드 API 및 이미지 생성은 유효한 키로 별도 확인해야 합니다. 공식 정보와 이미지 검토는 AI 기반이므로 최종 게시 전 사용자가 초안을 확인합니다.

## 참고 문서

- https://docs.zernio.com/posts/update-post
- https://docs.zernio.com/guides/media-uploads
- https://docs.zernio.com/messages/get-inbox-conversation-messages
- https://developers.openai.com/api/docs/guides/tools-web-search
- https://developers.openai.com/api/docs/guides/image-generation
- https://render.com/docs/blueprint-spec
