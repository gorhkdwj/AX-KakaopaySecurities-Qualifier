# OpenBell Guard 예선 질문 5문항 최종 답변

> 이 문서는 제출폼에 복사하기 위한 답변 원본입니다. 로컬 제출용 TXT는 루트의 `submission-form-answers.txt`에 같은 내용으로 저장합니다.

## 문항 1. 무엇을, 누가, 어떤 상황에서 쓰나요?

OpenBell Guard는 카카오페이증권 운영·장애 분석 담당자가 장애 종료 후 익명화 또는 합성 사고 번들을 넣어 국내장 개장 직후 지연과 외부 의존성 장애를 서비스 경로별로 분리하고, 검증 가능한 보고서 초안을 만드는 Codex 플러그인입니다. 사용자는 SRE, DevOps, 백엔드, 사고 분석 담당자입니다. incident.json, logs.jsonl, metrics.csv, service-map.json은 있지만 “시세·관심종목만 느렸는지, 주문·체결도 영향받았는지, 로그 유입 지연인지, 외부 중개사 문제인지”를 빠르게 구분해야 할 때 로컬에서 씁니다. 원본 입력은 수정하지 않고 마스킹 작업본과 analysis.json, openbell-report.md, output-validation.json을 생성해 사후 보고와 재발 방지 검토에 활용합니다.

## 문항 2. 왜 이 문제를 선택했나요?

카카오페이증권은 2026년 2~3월 국내장 개장 직후 일부 서비스 지연을 반복 겪었고, 외부 중개사 장애로 미국주식 모으기 주문 일부 미체결 이슈도 공개 보도됐습니다. 회사의 주문장애 기준은 시세지연·외부 유관기관 장애와 주문장애를 구분하므로, 모든 지연을 “전체 주문장애”로 뭉뚱그리지 않는 분석이 중요합니다. 고객은 변동성이 큰 개장 직후 가격·관심종목 정보를 제때 보지 못하면 투자 판단이 막히고, 운영자는 내부 용량 문제, 외부 의존성, 로그 수집 지연을 분리해야 재발 방지와 고객 설명을 정확히 할 수 있습니다. 카카오페이증권 Techlog의 장 시작 트래픽 스파이크·대규모 로그 처리 문제도 이 주제가 기업 기술 관심사와 맞닿아 있음을 보여줍니다.

출처 URL

- https://www.ajunews.com/view/20260303180523370
- https://m.tf.co.kr/read/economy/2298511.htm
- https://www.kakaopaysec.com/portal/cstmnotice-obstc/dynamicPage.do
- https://tech.kakaopay.com/post/pallas-v2-log-platform/

## 문항 3. 플러그인은 어떻게 작동하나요?

사용자는 사고 번들 경로와 출력 폴더를 지정합니다. 플러그인은 먼저 필수 파일, 허용 파일, UTF-8, 파일 크기, 사고·기준 구간, 시간대, service-map 구조를 검사합니다. 다음으로 토큰·이메일·전화번호·계좌번호 등 민감정보 패턴을 마스킹한 작업본을 만들고 잔존 여부를 재검사합니다. 이후 logs.jsonl과 metrics.csv를 행 단위로 읽어 UTC 60초 bucket에 배정하고, 요청 수, 오류 수, 오류율, p50·p95·p99 지연, 관측 지연, 기준 구간 대비 변화, CPU·메모리 맥락 지표를 계산합니다. 상태 판정은 사용자 입력 임계치에 대해 `>`이면 breach, 모두 `<=`이면 healthy, 임계치나 표본이 부족하면 unknown으로 둡니다. 사고 구간에서 2개 연속 breach면 장애 시작, 이후 2개 연속 healthy면 회복으로 봅니다. 모든 사실·가설은 evidence ID와 claim ID로 연결됩니다. 정보가 부족하면 근본 원인을 만들지 않고 null, reason_code, 추가 확인 필요로 남깁니다. 최종 산출물은 analysis.json, openbell-report.md, sanitization-report.md, output-validation.json입니다.

## 문항 4. AI를 어떻게 썼나요?

AI에는 공개 자료 조사, 문제 후보 비교, 기획서·README·질문지 작성, 지표 계약 설계, Python 코드 구현, 테스트 시나리오 작성, 결과 해석 보고서 초안, 오류 원인 분석을 맡겼습니다. 직접 판단한 부분은 카카오페이증권 문제 선택, Skill+로컬 Python 중심 MVP 범위, 실제 주문·계좌 조작과 운영 자동화 제외, 합성 데이터 사용, 외부 중개사와 내부 장애 분리 원칙, case-003 보류, 불필요한 assets·.gitkeep 정리입니다. 받아들이지 않은 제안도 있습니다. 실시간 모니터링, MCP 서버, 대규모 백엔드 스택, 원인 자동 확정은 구현 비용과 안전 리스크가 커서 제외했습니다. 구현 중에는 defaultPrompt 128자 제한, PowerShell 한글 검색 문제, ZIP 파일 수 불일치 등을 AI와 함께 추적해 수정했습니다.

## 문항 5. 어떻게 검증했나요?

검증은 단위·통합 테스트, 수동 예제, 성능 benchmark, 제출 ZIP 검증으로 나눴습니다. `python -m pytest src\tests`에서 68개 테스트가 통과했고, 국내장 개장 피크, 외부 중개사 장애, 불완전 데이터, 비밀정보 포함 입력, 관측 지연, 근거 없는 원인 단정 방지, 임계값 경계를 확인했습니다. case-001은 작은 입문 예제, case-002는 80,000행 규모 합성 로그 예제입니다. case-002에서는 market_data·watchlist_info는 저하, order_execution은 정상으로 판정되어 “전체 주문장애”로 과장하지 않는지 확인했습니다. P4-18 benchmark는 logs 100,000행, metrics 50,000행에서 5회 모두 성공했습니다. 최종 submission.zip은 18개 파일, README.md·logs·src 구조, manifest·Skill 포함, .gitkeep 없음, 빈 assets 없음, ZIP 내부 대표 fixture 실행과 output-validation 검증 통과를 확인했습니다. 한계는 실제 운영 로그와 실제 내부 SLO가 아니라 합성 데이터 검증이라는 점입니다.
