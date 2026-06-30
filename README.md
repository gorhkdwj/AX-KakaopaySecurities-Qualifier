# OpenBell Guard

OpenBell Guard는 AX 해커톤 카카오페이증권 제출용 Codex 플러그인입니다.

이 플러그인은 합성 또는 익명화된 증권 서비스 사고 분석 번들을 읽고, 국내장 개장 직후 지연·오류와 외부 의존성 장애 가능성을 서비스 경로별로 분리해 분석합니다. 결과는 기계 검증용 `analysis.json`, 사람 검토용 `openbell-report.md`, 민감정보 처리 확인용 `sanitization-report.md`로 나뉩니다.

## 해결하려는 문제

카카오페이증권은 공개 보도와 회사 공개 자료에서 개장 직후 트래픽 집중, 시세·관심종목 지연, 외부 중개사 장애처럼 서로 다른 유형의 운영 리스크가 드러났습니다.

OpenBell Guard는 이런 상황을 무조건 “전체 주문 장애”로 뭉뚱그리지 않고 다음을 구분하는 데 초점을 둡니다.

- 시세 경로 `market_data`
- 관심종목·정보 경로 `watchlist_info`
- 주문·체결 경로 `order_execution`
- 외부 의존성 경로

이 플러그인은 실제 주문, 계좌 조작, 운영 시스템 변경, 보상 판단을 수행하지 않습니다. 읽기 전용 분석 도구이며, 최종 고객 공지와 사후 보고서는 사람이 검토해야 합니다.

## 제출물 구조

```text
submission.zip
├── README.md
├── src/
│   ├── .codex-plugin/plugin.json
│   ├── skills/openbell-guard/SKILL.md
│   ├── skills/openbell-guard/scripts/
│   ├── skills/openbell-guard/references/
│   └── tests/
└── logs/
```

`src/`가 실제 Codex 플러그인 루트입니다. `logs/`에는 플러그인을 만들면서 AI와 주고받은 원본 대화 로그가 들어갑니다.

## 실행 방법

프로젝트 루트 또는 제출 ZIP을 푼 폴더에서 다음 명령을 실행합니다.

```powershell
python .\src\skills\openbell-guard\scripts\run_openbell.py --bundle .\src\tests\fixtures\domestic-market-open-min\bundle --output .\out\openbell-demo
```

출력 검증만 다시 실행하려면 다음 명령을 사용합니다.

```powershell
python .\src\skills\openbell-guard\scripts\validate_bundle.py --output .\out\openbell-demo
```

성공하면 `out/openbell-demo/` 아래에 다음 파일이 생성됩니다.

- `openbell-cli-summary.json`
- `sanitization-report.md`
- `record-summary.json`
- `bucket-summary.json`
- `metric-summary.json`
- `state-summary.json`
- `evidence-summary.json`
- `analysis.json`
- `openbell-report.md`
- `output-validation.json`

## 동작 절차와 판단 기준

OpenBell Guard는 하나의 사고 분석 번들을 다음 순서로 처리합니다.

1. 입력 사전 검사
   - 번들은 `incident.json`, `logs.jsonl`, `metrics.csv`, `service-map.json`으로 구성됩니다.
   - 필수 파일 존재, 허용 파일, UTF-8 인코딩, 파일 크기, 사고 구간, 기준 구간, 시간대, `service-map` 구조를 먼저 확인합니다.
   - 이 단계에서 문제가 있으면 분석을 억지로 계속하지 않고 입력 오류로 중단합니다.
2. 민감정보 마스킹
   - 토큰, 이메일, 전화번호, 계좌번호 같은 민감정보 패턴을 탐지해 원본이 아닌 `sanitized-bundle/` 작업본에 마스킹합니다.
   - 마스킹 후에도 원값이 남아 있는지 다시 검사합니다.
   - 실제 고객정보, 실제 계좌정보, 실제 API 키나 토큰이 필요한 플러그인이 아닙니다.
3. 로그·메트릭 정규화
   - 마스킹된 `logs.jsonl`과 `metrics.csv`를 행 단위로 읽습니다.
   - 유효한 행은 UTC 기준 60초 bucket으로 묶고, 손상 행·구간 밖 행·선택 필드 오류는 원인을 기록해 분리합니다.
4. 지표 계산
   - 요청 수, 오류 수, 처리량, 오류율, p50·p95·p99 지연시간, 관측 지연, 기준 구간 대비 변화량, CPU·메모리 맥락 지표를 계산합니다.
   - 평균 지연시간, 실제 고객 수, 손실액, 실제 SLO 준수율처럼 정의하지 않은 지표는 만들지 않습니다.
5. 상태 판정
   - 상태는 입력 번들에 포함된 사용자 정의 임계치를 기준으로 판단합니다.
   - 계산 가능한 지표 중 하나라도 임계치보다 엄격하게 `>` 크면 해당 bucket은 `breach`입니다.
   - 모든 임계치가 계산 가능하고 각각 `<=` 임계치이면 `healthy`입니다.
   - 임계치가 없거나 필요한 데이터가 부족하면 `unknown`으로 남깁니다.
   - 사고 구간에서 `breach`가 2개 bucket 연속이면 첫 번째 breach bucket을 장애 시작으로 봅니다.
   - 장애 시작 후 `healthy`가 2개 bucket 연속이면 첫 번째 healthy bucket을 회복 시각으로 봅니다.
6. 근거와 보고서 생성
   - 확인된 사실, 원인 가설, 추가 확인 필요 문장을 각각 claim ID로 기록합니다.
   - 각 claim은 evidence ID와 연결되어야 하며, 근거 없는 사실 문장은 검증에서 실패합니다.
   - 최종적으로 `analysis.json`, `openbell-report.md`, `sanitization-report.md`, `output-validation.json`을 생성합니다.

정보가 부족하거나 잘 안 풀리는 상황에서는 가장 그럴듯한 원인을 만들어내지 않습니다. 예를 들어 하위 의존성 오류 지표, trace 단위 인과관계, 외부 거래소·브로커 상태 정보가 없으면 근본 원인을 확정하지 않고 `unknown`, `null`, `reason_code`, `추가 확인 필요`로 남깁니다. 관측 지연만 큰 경우에도 서비스 장애로 단정하지 않고 로그 수집 지연 가능성을 분리합니다.

## 결과를 읽는 순서

처음 보는 사용자는 다음 순서로 보면 됩니다.

1. `openbell-cli-summary.json`: 실행이 성공했는지 확인합니다.
2. `state-summary.json`: 서비스 경로별 상태, 장애 시작, 회복 시각을 확인합니다.
3. `metric-summary.json`: 60초 bucket별 오류율, 지연, 관측 지연을 확인합니다.
4. `analysis.json`: claim, evidence, 지표와 판정을 기계 검증 원장으로 확인합니다.
5. `openbell-report.md`: 사람이 읽는 보고서 초안을 검토합니다.
6. `output-validation.json`: 산출물 검증과 민감정보 잔존 검사 결과를 확인합니다.

## 대표 검증 결과

P4-17에서는 A~H 통합 시나리오를 검증했습니다.

- 국내장 개장 피크와 경로별 부분 장애
- 외부 중개사 장애
- 불완전 데이터
- 비밀정보 포함 입력
- 서비스 정상·로그 유입 지연
- 타임아웃 증상과 원인 단정 방지
- 임계값 경계
- 손상 입력과 지원 한도

P4-18에서는 합성 지원 한도 benchmark를 실행했습니다.

- `logs.jsonl`: 100,000행
- `metrics.csv`: 50,000행
- M-016 실행시간 중앙값: 34.523738초
- M-017 Python 추적 메모리 최고값: 194.280592MiB
- 측정 5회 모두 exit code 0

이 benchmark는 로컬 합성 데이터 기준입니다. 실제 카카오페이증권 운영 성능이나 전체 프로세스 메모리를 보장하지 않습니다.

P4-19에서는 제출 패키징을 검증했습니다.

- `submission.zip` 생성 완료
- ZIP 내부 파일 수: 22개
- 원본 대화 로그 파일 수: 1개
- 공식 플러그인 manifest 검증 통과
- 공식 Skill 구조 검증 통과
- 제출 ZIP 구조 검증 통과
- 제출 ZIP 내부 경로 기준 대표 fixture 실행 통과
- 제출 ZIP 내부 실행 결과의 schema, evidence, claim marker, 민감정보 잔존 검사 통과
- 임시 로컬 marketplace `openbell-guard-local` 구성 및 `openbell-guard@openbell-guard-local` 설치 확인
- 새 Codex 비대화 세션에서 `openbell-guard` Skill 사용 가능 응답 확인

새 Codex UI 화면에서 사람이 직접 클릭해 확인하는 과정까지 자동화하지는 못했습니다. 대신 Codex CLI marketplace 설치, plugin list의 `installed, enabled` 상태, 새 Codex 비대화 세션의 Skill 인식 응답으로 재현 가능성을 확인했습니다.

## 수동 테스트 예제

개발 저장소에는 사람이 읽는 수동 테스트 보고서가 있습니다.

- `docs/manual-test-reports/case-001-market-open-watchlist-review.md`
- `docs/manual-test-reports/case-002-large-scenario.md`

단, `docs/`와 `out/`은 최종 제출 ZIP에 기본 포함하지 않습니다. 제출 ZIP은 플러그인 실행에 필요한 `src/`, 제출용 `README.md`, 원본 대화 로그 `logs/`만 포함합니다.

## 안전 경계

- 실제 고객정보, 실제 계좌정보, 실제 API 키, 비밀번호, 토큰을 입력하지 마십시오.
- 합성 테스트 데이터의 장애 원인을 카카오페이증권의 실제 내부 원인으로 단정하지 마십시오.
- `openbell-report.md`는 초안이며 고객 공지, 보상, 법적 판단, 운영 조치는 사람 검토가 필요합니다.
- 플러그인은 외부 API를 호출하지 않는 로컬 분석 도구로 설계되어 있습니다.

## 개발·검증 명령

저장소 루트에서 다음 검증을 실행할 수 있습니다.

```powershell
python -m pytest src\tests
python .\tools\preflight_check.py --quiet
python .\tools\build_submission.py
python .\tools\validate_submission.py .\submission.zip
python .\submission\src\skills\openbell-guard\scripts\run_openbell.py --bundle .\submission\src\tests\fixtures\domestic-market-open-min\bundle --output .\out\p4-19-submission-smoke
python .\submission\src\skills\openbell-guard\scripts\validate_bundle.py --output .\out\p4-19-submission-smoke
```

공식 플러그인·스킬 구조 검증은 개발 환경에 설치된 Codex `plugin-creator`와 `skill-creator` 검증 스크립트로 확인합니다. 검증 스크립트의 실제 위치는 사용자 환경마다 다를 수 있습니다.

이 프로젝트 개발 환경에서는 다음 두 검증을 수행했습니다.

- `validate_plugin.py .\src`
- `quick_validate.py .\src\skills\openbell-guard`

## 한계

- 본 제출물은 공개 자료와 합성 데이터 기반 검증물입니다.
- 카카오페이증권의 실제 내부 로그, 실제 장애 원인, 실제 운영 SLO는 포함하지 않습니다.
- 외부 중개사 장애와 내부 장애를 분리하는 분석 틀을 제공하지만, 최종 원인 확정에는 추가 운영 데이터와 사람 검토가 필요합니다.
