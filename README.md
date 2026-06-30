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

새 Codex 앱 세션에서 UI 기반 설치와 신뢰 승인까지 자동화해 확인하지는 못했습니다. 현재 제출물은 공식 구조 검증과 패키지 내부 실행 검증으로 재현 가능성을 확인했습니다.

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
