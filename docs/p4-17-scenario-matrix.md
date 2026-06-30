# P4-17 통합 시나리오 매트릭스

이 문서는 Phase 4 P4-17에서 추가한 A~H 합성 시나리오 테스트가 무엇을 검증하는지 정리합니다.
실제 테스트 구현은 `src/tests/test_integration_scenarios.py`에 있으며, 모든 입력은 임시 디렉터리에 생성되는 합성 데이터입니다.

## 목적

P4-16까지는 대표 fixture 하나가 `analysis.json`, `openbell-report.md`, `output-validation.json`을 생성하고 검증하는 흐름을 완성했습니다.
P4-17은 같은 흐름이 대표 성공·실패·경계 상황에서도 유지되는지 확인합니다.

핵심 확인 질문은 다음과 같습니다.

- 서비스 경로별 부분 장애를 전체 주문 장애로 과장하지 않는가?
- 외부 중개사 장애와 내부 서비스 정상 상태를 분리하는가?
- 데이터가 불완전하면 가능한 계산만 수행하고 `degraded`·`unknown`으로 남기는가?
- 합성 비밀정보 원값이 파생 산출물에 남지 않는가?
- 서비스는 정상인데 관측 지연만 큰 상황을 서비스 장애로 단정하지 않는가?
- 오류 메시지를 근본 원인으로 승격하지 않는가?
- 임계치 경계와 연속 breach·recovery 규칙이 계약대로 동작하는가?
- 손상 행과 파일 한도 초과를 서로 다른 방식으로 처리하는가?

## 시나리오별 검증 내용

| ID | 이름 | 핵심 입력 | 기대 결과 |
|---|---|---|---|
| A | 국내장 개장 피크와 경로별 부분 장애 | `market_data`, `watchlist_info`는 breach, `order_execution`은 healthy | 주문 경로를 전체 주문장애로 표현하지 않고 정상 경로로 보존 |
| B | 외부 중개사 장애 | `recurring_investment` 경로가 `overseas_broker` 의존성 timeout을 가짐 | 외부 의존성 evidence를 보존하고 내부 `auth_access` 경로는 healthy |
| C | 불완전 데이터 | 임계치 없음, `metrics.csv` 없음 | 실행은 성공하되 `run.status=degraded`, 서비스 경로는 `unknown`, 보고서 claim 검증 통과 |
| D | 비밀정보 포함 입력 | Bearer token, API key, 이메일, 전화번호, 계좌번호 패턴 | 마스킹 후 모든 생성 산출물에서 원값 잔존 0건 |
| E | 서비스 정상·로그 유입 지연 | 오류율은 정상, `observed_time - event_time`만 180초 | 서비스 경로는 healthy, ingestion lag 지표는 보존, degradation 가설은 생성하지 않음 |
| F | 타임아웃 증상과 경쟁 가설 | 로그 메시지에 `DB connection timeout` 포함 | 분석과 보고서가 DB·JVM 근본 원인을 단정하지 않음 |
| G | 통계 경계와 임계치 | 오류율 50.0% 경계, 이후 2개 breach, 2개 healthy | `>` 비교로 50.0%는 healthy, 두 번째 breach에서 outage start, 첫 번째 healthy에서 recovery time |
| H | 손상 입력과 지원 한도 | 손상 JSONL 행, 별도 파일 크기 초과 입력 | 손상 행은 degraded로 기록, 파일 한도 초과는 exit 4와 `LIM001_FILE_BYTES` |

## 실행 명령

```bash
python -m unittest .\src\tests\test_integration_scenarios.py -v
```

전체 회귀 검증은 다음 명령으로 실행합니다.

```bash
python -m unittest discover .\src\tests -v
```

## 현재 한계

- A~H 시나리오는 실제 카카오페이증권 운영 데이터가 아니라 합성 데이터입니다.
- P4-17은 실제 운영 성능 보장을 하지 않습니다. 실행시간과 메모리 한도 검증은 P4-18에서 별도로 수행합니다.
- 시나리오 fixture는 테스트 실행 중 임시 디렉터리에 생성되므로, 제출용 예시 입력은 기존 `domestic-market-open-min` fixture를 계속 대표로 사용합니다.
