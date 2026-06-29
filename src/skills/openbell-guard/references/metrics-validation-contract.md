# OpenBell Guard 지표·수식·판정 기준 계약

> 문서 역할: 지표, 수식, 입력 검증, 장애·오류 판정의 단일 기준(Source of Truth)  
> 계약 버전: `1.0.0`  
> 입력 스키마 버전: `1.0`  
> 작성일: 2026-06-30  
> 적용 시점: Phase 4 구현 시작 전  
> 구현 상태: 설계 동결 완료, 코드·테스트 구현 전

## 1. 이 문서가 필요한 이유

이 문서는 파일, Codex 세션, Python 함수와 보고서마다 같은 용어가 다른 계산법으로 사용되는 일을 막습니다. OpenBell Guard에서 계산하거나 판정하는 값은 반드시 이 문서의 이름·단위·수식·예외 규칙을 따릅니다.

다른 문서는 사용자 흐름과 설계 이유만 요약하고 수식이나 오류 경계를 다시 정의하지 않습니다. 충돌이 발견되면 임의로 편한 기준을 선택하지 않고 이 문서를 기준으로 관련 문서·코드·fixture를 함께 고칩니다.

### 1.1 적용 대상

- `incident.json`, `logs.jsonl`, `metrics.csv`, `service-map.json`
- `redact_inputs.py`, `analyze_telemetry.py`, `run_openbell.py`, `validate_bundle.py`
- `analysis.json`, `openbell-report.md`, `sanitization-report.md`
- 단위 테스트, Golden fixture, README와 제출 질문지
- 이 프로젝트의 모든 Codex 세션

### 1.2 버전과 변경 규칙

- `contract_version`은 지표 의미와 판정 규칙 버전이며 현재 값은 `1.0.0`입니다.
- `schema_version`은 입력·출력 JSON 구조 버전이며 현재 값은 `1.0`입니다.
- 지표 수식, 포함·제외 기준, 임계치 부등호, 상태 또는 종료 코드가 바뀌면 코드보다 이 문서를 먼저 수정하고 Decisionlog에 새 D-ID를 남깁니다.
- 새 선택 지표를 추가하되 기존 의미가 바뀌지 않으면 minor 버전을 올립니다.
- 기존 결과가 달라지는 수식·단위·판정 변경은 major 버전을 올립니다.
- 오탈자나 의미가 변하지 않는 설명 보완은 patch 버전을 올립니다.
- Phase 4에서 이 문서의 제출용 복사본을 `src/skills/openbell-guard/references/metrics-validation-contract.md`에 생성하고, 두 파일의 SHA-256이 같은지 테스트합니다.
- `analysis.json`에는 `contract_version`과 구현에 포함된 계약 파일의 `contract_sha256`을 기록합니다.

## 2. 공통 계산 규칙

### 2.1 시간 구간

- 모든 시간 구간은 시작을 포함하고 끝을 제외하는 반개구간 `[start, end)`입니다.
- `event_time == start`인 레코드는 포함하고 `event_time == end`인 레코드는 제외합니다.
- 입력 시각에는 ISO 8601 UTC 오프셋이 반드시 있어야 합니다. `Z`는 `+00:00`으로 허용합니다.
- `incident.json.timezone`은 보고서 표시용 IANA 시간대입니다. 입력 레코드는 명시적 오프셋만 있으면 UTC나 다른 오프셋이어도 허용하며 UTC로 변환합니다.
- 내부 정렬·버킷·구간 비교는 UTC로 수행합니다.
- 보고서는 UTC와 `incident.json.timezone`으로 변환한 시각을 함께 표시합니다.
- 오프셋 없는 시각, 존재하지 않는 현지 시각과 파싱할 수 없는 시각은 추정하지 않습니다.

### 2.2 60초 버킷

- 버킷 크기는 고정 60초입니다.
- 버킷 시작은 UTC Unix epoch 기준으로 분 단위 내림한 시각입니다.
- 예: `09:00:00.000Z`부터 `09:00:59.999...Z`까지는 `09:00:00Z` 버킷입니다.
- 버킷도 `[bucket_start, bucket_start + 60초)`입니다.
- 출력은 `service_path`, `bucket_start` 오름차순으로 정렬합니다.

### 2.3 숫자와 반올림

- Python `bool`은 숫자로 허용하지 않습니다.
- `NaN`, 양·음의 무한대와 숫자로 파싱할 수 없는 값은 유효한 수치가 아닙니다.
- 계산은 입력 문자열을 `Decimal`로 변환해 수행합니다.
- 임계치 비교는 반올림 전 값으로 수행합니다.
- `analysis.json`의 비율·시간·백분위·중앙값은 소수점 셋째 자리까지 `ROUND_HALF_UP`으로 반올림합니다.
- `openbell-report.md`의 표시값은 소수점 둘째 자리까지 `ROUND_HALF_UP`으로 반올림하되 claim은 `analysis.json`의 반올림 전 판정 결과를 바꾸지 않습니다.
- 개수는 정수로 출력합니다.
- `-0.000`은 `0.000`으로 정규화합니다.

### 2.4 `null`, 0과 누락

- `0`은 관측된 실제 0입니다.
- `null`은 계산할 수 없거나 적용되지 않는 값입니다.
- 누락값을 0으로 채우지 않습니다.
- `null`에는 반드시 `reason_code`를 붙입니다. 허용 코드는 `missing_input`, `insufficient_sample`, `zero_denominator`, `threshold_missing`, `invalid_optional_field`, `not_applicable`입니다.
- `null`은 임계치 미초과를 뜻하지 않습니다.

### 2.5 중복과 정렬되지 않은 입력

- 입력 행은 시간순으로 정렬되어 있지 않아도 됩니다.
- 동일해 보이는 행을 자동 제거하지 않습니다. `trace_id`가 선택 필드이므로 중복 여부를 안전하게 확정할 수 없기 때문입니다.
- 각 유효 행은 하나의 관측값으로 한 번 집계합니다.
- fixture가 중복 제거를 요구하려면 별도 계약 버전 변경이 필요합니다.

## 3. 분석 단위와 표준 코드

### 3.1 서비스 경로

`service_path`는 다음 코드만 허용합니다.

| 코드 | 의미 |
|---|---|
| `auth_access` | 인증과 앱 접속 |
| `market_data` | 실시간 시세 |
| `watchlist_info` | 관심종목·종목정보·커뮤니티 |
| `order_execution` | 주문 접수·체결·잔고 |
| `recurring_investment` | 정기투자·주식 모으기 |
| `external_dependency` | 거래소·예탁결제원·해외 브로커 등 외부 연계 |

알 수 없는 경로를 가장 비슷한 코드로 추정하지 않습니다. `service-map.json`으로도 매핑할 수 없으면 해당 레코드는 거부합니다.

### 3.2 의존성 유형

`dependency_type`은 다음 코드만 허용합니다.

- `internal`
- `exchange`
- `depository`
- `overseas_broker`
- `observability`
- `unknown`

`unknown`은 입력이 명시적으로 알 수 없음을 표현한 값입니다. 필드 누락과 같지 않습니다.

### 3.3 로그 한 행의 grain

`logs.jsonl` 한 행은 하나의 요청 결과 관측값입니다. 모든 유효 행은 요청 수 분모에 한 번 포함됩니다. `log_type`·`severity`·`message`는 근거 설명용이며 요청 수 포함 여부를 바꾸지 않습니다.

`status=rejected`는 서비스가 요청을 거부한 결과입니다. 입력 형식이 잘못되어 분석기가 행을 버리는 “레코드 거부”와 구분합니다.

### 3.4 메트릭 한 행의 grain

`metrics.csv` 한 행은 `metric_name`에 따라 60초 집계값 하나 또는 개별 표본 하나를 나타냅니다.

| `metric_name` | `unit` | 한 행의 의미 | 버킷 집계 |
|---|---|---|---|
| `request_count` | `count` | 해당 60초 버킷의 요청 수 | 합계 |
| `error_count` | `count` | 해당 60초 버킷의 오류 요청 수 | 합계 |
| `latency_sample_ms` | `ms` | 요청 하나의 지연시간 표본 | nearest-rank |
| `ingestion_lag_sample_ms` | `ms` | 관측 하나의 유입 지연 표본 | nearest-rank |
| `cpu_utilization_pct` | `percent` | 시점별 CPU 사용률 표본 | 중앙값 |
| `memory_utilization_pct` | `percent` | 시점별 메모리 사용률 표본 | 중앙값 |

표에 없는 `metric_name` 또는 일치하지 않는 `unit`의 행은 거부합니다. CPU·메모리 값은 원인 가설의 맥락 자료일 뿐 MVP 장애 판정 임계치에는 사용하지 않습니다.

## 4. 입력 파일 계약과 오류 기준

### 4.1 사고 번들 공통 규칙

- 번들은 일반 로컬 디렉터리여야 하며 심볼릭 링크를 허용하지 않습니다.
- 최상위에는 `incident.json`, `logs.jsonl`, `metrics.csv`, `service-map.json`만 둘 수 있습니다.
- `incident.json`은 필수입니다.
- `logs.jsonl`과 `metrics.csv` 중 하나 이상이 필수입니다.
- 하위 디렉터리, 지원하지 않는 파일과 심볼릭 링크가 발견되면 입력 오류로 중단합니다.
- 텍스트 인코딩은 UTF-8 또는 UTF-8 BOM만 허용합니다.
- 입력 원본은 수정하지 않습니다.

### 4.2 고정 지원 한도

`이하`는 경계값을 포함하며 `초과`는 정확히 경계값보다 큰 경우입니다.

| 대상 | 허용 한도 | 오류 조건 |
|---|---:|---|
| `incident.json` | 5 MiB 이하 | 파일 크기 > 5 × 1024 × 1024바이트 |
| `service-map.json` | 5 MiB 이하 | 파일 크기 > 5 × 1024 × 1024바이트 |
| `logs.jsonl` | 50 MiB 이하 | 파일 크기 > 50 × 1024 × 1024바이트 |
| `logs.jsonl` 레코드 | 100,000개 이하 | 물리적 JSONL 행 수 > 100,000 |
| JSONL 한 행 | 1 MiB 이하 | 한 행의 UTF-8 바이트 수 > 1 × 1024 × 1024 |
| `metrics.csv` | 20 MiB 이하 | 파일 크기 > 20 × 1024 × 1024바이트 |
| `metrics.csv` 레코드 | 50,000개 이하 | 헤더를 제외한 물리적 행 수 > 50,000 |
| 사고 번들 전체 | 80 MiB 이하 | 허용된 파일들의 크기 합 > 80 × 1024 × 1024바이트 |

- JSONL의 빈 행도 물리적 레코드 수에 포함하며 형식 오류로 거부합니다.
- CSV 헤더는 레코드 수에서 제외합니다. 빈 데이터 행은 레코드 수에 포함하고 거부합니다.
- 마지막 줄바꿈 문자만으로 새 레코드가 추가되지는 않습니다.
- 한도를 넘으면 일부만 처리하지 않고 종료 코드 `4`로 중단합니다.

### 4.3 `incident.json`

필수 필드는 다음과 같습니다.

| 필드 | 기준 | 오류 조건 |
|---|---|---|
| `schema_version` | 문자열 `1.0` | 누락 또는 다른 값 |
| `contract_version` | 문자열 `1.0.0` | 누락 또는 다른 값 |
| `incident_id` | `[A-Za-z0-9][A-Za-z0-9._-]{0,63}` | 패턴 불일치 |
| `timezone` | `zoneinfo.ZoneInfo`로 읽을 수 있는 IANA 이름 | 읽을 수 없음 |
| `baseline_window.start/end` | 오프셋 포함 ISO 8601, 분 경계 | 파싱 실패 또는 초·마이크로초가 0이 아님 |
| `incident_window.start/end` | 오프셋 포함 ISO 8601, 분 경계 | 파싱 실패 또는 초·마이크로초가 0이 아님 |

구간 판정 기준:

- 각 `end`는 같은 구간의 `start`보다 뒤여야 합니다.
- 기준 구간 길이는 60초 이상이어야 합니다.
- 사고 구간 길이는 120초 이상이어야 합니다.
- `baseline_window.end <= incident_window.start`여야 합니다.
- 두 구간이 겹치면 입력 오류입니다.

`thresholds`는 선택 객체이며 키는 표준 `service_path`입니다. 각 경로에는 다음 상한 중 하나 이상을 둘 수 있습니다.

| 임계치 키 | 단위·범위 | 초과 판정 |
|---|---|---|
| `error_rate_pct_max` | 0 이상 100 이하 percent | 오류율 > 설정값 |
| `p95_latency_ms_max` | 0 이상 ms | p95 > 설정값 |
| `p99_latency_ms_max` | 0 이상 ms | p99 > 설정값 |
| `ingestion_lag_p95_ms_max` | 0 이상 ms | 관측 지연 p95 > 설정값 |

알 수 없는 임계치 이름, 범위 밖 수치, `NaN`·무한대와 빈 경로 객체는 입력 오류입니다. 임계치 값과 비교값이 같으면 초과가 아닙니다.

### 4.4 `logs.jsonl`

한 줄에 하나의 JSON 객체만 허용합니다.

필수 필드:

| 필드 | 유효 기준 |
|---|---|
| `event_time` | 오프셋 포함 ISO 8601 시각 |
| `service_name` | 앞뒤 공백 제거 후 1~128자 문자열 |
| `service_path` | 표준 서비스 경로 코드 |
| `status` | `ok`, `error`, `timeout`, `rejected` 중 하나 |

선택 필드:

| 필드 | 유효 기준 | 잘못된 경우 |
|---|---|---|
| `observed_time` | 오프셋 포함 ISO 8601, `observed_time >= event_time` | 필드를 `null`로 버리고 degraded |
| `latency_ms` | 0 이상 유한 숫자 | 필드를 `null`로 버리고 degraded |
| `dependency_type` | 표준 의존성 코드 | 필드를 `null`로 버리고 degraded |
| `trace_id` | 1~128자 문자열 | 필드를 `null`로 버리고 degraded |
| `log_type` | 1~64자 문자열 | 필드를 `null`로 버리고 degraded |
| `severity` | `debug`, `info`, `warning`, `error`, `critical` | 필드를 `null`로 버리고 degraded |
| `message` | 문자열 | 필드를 `null`로 버리고 degraded |

- JSON 문법 오류, 객체가 아닌 값, 필수 필드 누락·자료형·허용값 오류는 해당 행을 거부합니다.
- 유효 행의 `event_time`이 기준·사고 구간 밖이면 집계에서 제외하고 `outside_analysis_window_count`에 포함합니다. 이는 레코드 거부가 아니며 단독으로 degraded를 만들지 않습니다.
- `message`는 마스킹 후 evidence 발췌에서 최대 300 Unicode 문자만 사용합니다. 나머지는 잘라도 지표 계산에는 영향이 없습니다.
- 알 수 없는 추가 필드는 무시하고 `unknown_field` 경고를 남기며 단독으로 degraded를 만들지 않습니다.

### 4.5 `metrics.csv`

- 구분자는 쉼표이고 첫 행은 헤더여야 합니다.
- 필수 열은 `timestamp`, `service_name`, `metric_name`, `value`, `unit`입니다.
- 선택 열은 `service_path`, `dependency_type`입니다.
- 중복 헤더 이름은 파일 입력 오류입니다.
- 알 수 없는 추가 열은 무시하고 경고를 남깁니다.

행 기준:

- `timestamp`는 오프셋 포함 ISO 8601이어야 합니다.
- `service_name`은 앞뒤 공백 제거 후 1~128자여야 합니다.
- `service_path`가 없으면 `service-map.json`의 `service_name` 매핑을 사용합니다. 둘 다 없으면 행을 거부합니다.
- `metric_name`·`unit`은 3.4의 조합과 정확히 일치해야 합니다.
- `value`는 유한 숫자여야 합니다.
- `request_count`·`error_count`는 0 이상 정수이고 `timestamp`가 분 경계여야 합니다.
- 지연 표본은 0 이상입니다.
- CPU·메모리 percent는 0 이상 100 이하입니다.
- 같은 경로·버킷의 집계 `error_count > request_count`이면 해당 버킷의 요청·오류 집계를 무효화하고 degraded로 기록합니다.
- 기준·사고 구간 밖 행은 로그와 같은 방식으로 제외합니다.

### 4.6 `service-map.json`

- `services` 배열의 각 항목은 `service_name`, `service_path`, `dependency_type`을 가져야 합니다.
- `service_name`은 파일 안에서 유일해야 합니다.
- `service_path`와 `dependency_type`은 표준 코드여야 합니다.
- 선택 `dependencies`는 파일 안에 존재하는 `service_name` 문자열 배열이어야 합니다.
- 파일이 제공됐는데 JSON·필드·중복·참조 검증이 실패하면 행 단위로 추정하지 않고 입력 오류로 중단합니다.

## 5. 데이터 소스 우선순위

- 사고 번들에 유효한 `logs.jsonl` 행이 하나 이상 있으면 요청 수·오류 수·지연시간·관측 지연의 주 계산 소스는 로그입니다.
- 로그가 없거나 유효한 구간 내 로그 행이 하나도 없고 유효한 `metrics.csv`가 있으면 메트릭이 주 계산 소스입니다.
- 로그가 주 소스일 때 `metrics.csv`의 동일 지표는 덮어쓰거나 빈 로그 버킷을 임의 보충하지 않고 `context_metrics`에 별도로 보존합니다.
- CPU·메모리 메트릭은 로그 존재 여부와 관계없이 맥락 지표로 보존합니다.
- 두 소스 값의 차이를 자동으로 “데이터 오류”나 특정 비율 이상 불일치라고 판정하지 않습니다. MVP에는 검증된 불일치 허용치가 없으므로 각 값과 출처를 함께 제시합니다.

## 6. 표준 지표 사전

### M-001 유효 요청 수

- 영문 키: `request_count`
- grain: 서비스 경로 × 60초 버킷
- 단위: `count`
- 로그 수식: 해당 버킷에 포함된 유효 로그 행의 수
- 메트릭 수식: `metric_name=request_count` 값의 합
- 제외: 거부 행과 분석 구간 밖 행

### M-002 오류 요청 수

- 영문 키: `error_count`
- grain: 서비스 경로 × 60초 버킷
- 단위: `count`
- 로그 수식: `status ∈ {error, timeout, rejected}`인 유효 로그 행의 수
- 메트릭 수식: `metric_name=error_count` 값의 합
- `status=ok`는 오류가 아닙니다.

### M-003 처리량

- 영문 키: `throughput_rps`
- 단위: requests/second
- 수식: `request_count / 60`
- 분모는 버킷 크기 60초로 고정합니다.
- 요청 수가 0이면 처리량은 실제 `0`입니다.
- 처리량 증가는 그 자체로 장애가 아닙니다.

### M-004 오류율

- 영문 키: `error_rate_pct`
- 단위: percent
- 수식: `error_count / request_count × 100`
- `request_count=0`이면 `null`, `reason_code=zero_denominator`입니다.
- 오류율 임계치 비교는 `> error_rate_pct_max`입니다.

### M-005 p50 지연시간

- 영문 키: `latency_p50_ms`
- 단위: ms
- 표본: 유효한 `latency_ms` 또는 `latency_sample_ms`
- 최소 표본: 1개
- 계산: nearest-rank `rank = ceil(0.50 × n)`, 오름차순 1-indexed `rank`번째 값

### M-006 p95 지연시간

- 영문 키: `latency_p95_ms`
- 단위: ms
- 최소 표본: 20개
- 계산: `rank = ceil(0.95 × n)`
- `n < 20`이면 `null`, `reason_code=insufficient_sample`입니다.

### M-007 p99 지연시간

- 영문 키: `latency_p99_ms`
- 단위: ms
- 최소 표본: 100개
- 계산: `rank = ceil(0.99 × n)`
- `n < 100`이면 `null`, `reason_code=insufficient_sample`입니다.

nearest-rank는 보간하지 않으며 실제 관측값 하나를 반환합니다.

### M-008 개별 관측 지연

- 영문 키: `ingestion_lag_ms`
- 단위: ms
- 수식: `observed_time - event_time`
- 두 시각 중 하나가 없으면 `null`, `reason_code=missing_input`입니다.
- 계산값이 음수이면 해당 `observed_time`을 잘못된 선택 필드로 버리고 `null`, `reason_code=invalid_optional_field`로 기록하며 run은 degraded입니다.

### M-009 관측 지연 p50·p95·p99

- 영문 키: `ingestion_lag_p50_ms`, `ingestion_lag_p95_ms`, `ingestion_lag_p99_ms`
- 단위: ms
- 표본: 유효한 `ingestion_lag_ms` 또는 `ingestion_lag_sample_ms`
- 계산법과 최소 표본은 M-005~M-007과 같습니다.

### M-010 기준값

- 영문 키: `baseline_median`
- grain: 서비스 경로 × 지표
- 단위: 원 지표와 동일
- 표본: 기준 구간의 유효한 60초 버킷 값
- 홀수 개 중앙값: 정렬 후 가운데 값
- 짝수 개 중앙값: 가운데 두 값의 산술평균
- 유효 버킷이 없으면 `null`, `reason_code=insufficient_sample`입니다.

### M-011 사고 구간 최고값

- 영문 키: `incident_peak`
- grain: 서비스 경로 × 지표
- 단위: 원 지표와 동일
- 수식: 사고 구간의 유효한 버킷 값 중 최댓값
- 처리량의 peak는 트래픽 크기 설명용이며 장애 판정 근거가 아닙니다.
- 유효 버킷이 없으면 `null`입니다.

### M-012 기준 대비 절대 변화량

- 영문 키: `change_abs`
- 수식: `incident_peak - baseline_median`
- 둘 중 하나가 `null`이면 `null`입니다.

### M-013 기준 대비 변화율

- 영문 키: `change_pct`
- 단위: percent
- 수식: `(incident_peak - baseline_median) / baseline_median × 100`
- `baseline_median=0`이면 `null`, `reason_code=zero_denominator`입니다.
- 변화율은 임계치가 아니며 단독으로 장애를 판정하지 않습니다.

### M-014 처리·거부·제외 레코드 수

- `physical_record_count`: 파일의 물리적 데이터 행 수
- `accepted_record_count`: 필수 필드가 유효해 분석 대상으로 받아들인 행 수
- `rejected_record_count`: 행 전체를 버린 수
- `outside_analysis_window_count`: 유효하지만 기준·사고 구간 밖이라 집계에서 제외한 수
- `field_dropped_count`: 행은 유지했지만 잘못된 선택 필드를 `null`로 버린 수

항상 다음 등식이 성립해야 합니다.

`physical_record_count = accepted_record_count + rejected_record_count`

`outside_analysis_window_count`는 `accepted_record_count`의 부분집합이며 위 등식에 별도로 더하지 않습니다.

### M-015 CPU·메모리 사용률 중앙값

- 영문 키: `cpu_utilization_median_pct`, `memory_utilization_median_pct`
- grain: 서비스 경로 × 60초 버킷
- 단위: percent
- 수식: 해당 버킷의 유효 표본 중앙값
- MVP에는 포화 임계치가 없으므로 높은 수치만으로 “자원 포화” 또는 근본 원인을 확정하지 않습니다.

### M-016 결정론적 파이프라인 실행시간

- 영문 키: `deterministic_pipeline_wall_time_seconds`
- 단위: seconds
- 측정 시작: `run_openbell.py`가 입력 사전 검사를 시작하기 직전의 `time.perf_counter()`
- 측정 종료: 마스킹, 파싱, 계산, `analysis.json`·`sanitization-report.md` 자체 검증이 끝난 직후의 `time.perf_counter()`
- 수식: `end_counter - start_counter`
- Codex의 `openbell-report.md` 작성 시간과 네트워크 대기시간은 포함하지 않습니다.
- 지원 한도 경계 fixture로 준비 실행 1회를 한 뒤 같은 프로세스 조건에서 측정 5회를 수행합니다.
- 보고값은 5회 중앙값이며, 5회가 모두 종료 코드 `0`이고 중앙값이 60초 이하일 때 시간 기준을 통과합니다.
- 운영 성능 보장이 아니라 Phase 4 개발 환경의 재현 가능한 합성 benchmark입니다. 운영체제, Python 버전, CPU와 메모리를 결과에 함께 기록합니다.

### M-017 Python 메모리 최고값

- 영문 키: `peak_python_memory_mib`
- 단위: MiB
- 측정 범위: M-016과 같은 결정론적 파이프라인 구간
- 측정 도구: Python 표준 라이브러리 `tracemalloc`
- 수식: `peak_traced_bytes / (1024 × 1024)`
- 5회 측정값 중 최댓값이 512 MiB 이하일 때 메모리 기준을 통과합니다.
- `tracemalloc`이 추적하지 못하는 Python 외부 native memory와 운영체제 파일 캐시는 포함하지 않으므로 “프로세스 전체 메모리”라고 표현하지 않습니다.

M-016 또는 M-017이 기준을 넘으면 구현 오류로 숨기거나 지원 한도를 유지한 채 통과 처리하지 않습니다. fixture·환경·측정 결과를 기록하고 Decisionlog를 갱신한 뒤 지원 한도를 낮추거나 구현을 개선해 다시 측정합니다.

## 7. 임계치와 장애 상태 판정

### 7.1 버킷 평가

각 서비스 경로·버킷은 `breach`, `healthy`, `unknown` 중 하나입니다.

- `breach`: 설정된 상한 중 계산 가능한 값 하나 이상이 엄격하게 `>` 임계치입니다.
- `healthy`: 설정된 모든 값이 계산 가능하고 각각 `<=` 임계치입니다.
- `unknown`: 임계치가 없거나, 설정된 지표 중 하나라도 `null`이어서 모든 조건을 평가할 수 없습니다.

여러 임계치가 있을 때 하나라도 초과하면 `breach`입니다. 초과가 없더라도 하나가 계산 불가이면 `healthy`로 간주하지 않고 `unknown`입니다.

### 7.2 장애 시작

- 영문 키: `outage_start`
- 판정: `breach` 버킷이 2개 연속일 때 첫 번째 버킷의 `bucket_start`
- `unknown` 또는 `healthy` 버킷은 연속 breach 수를 0으로 초기화합니다.
- 사고 구간 안에서 조건을 충족하지 못하면 `null`입니다.

### 7.3 회복

- 영문 키: `recovery_time`
- 판정: 장애 시작 후 `healthy` 버킷이 2개 연속일 때 첫 번째 healthy 버킷의 `bucket_start`
- `unknown` 또는 `breach` 버킷은 연속 healthy 수를 0으로 초기화합니다.
- 장애 시작이 없으면 회복도 `null`입니다.
- 사고 구간 끝까지 회복 조건이 없으면 `recovery_time=null`, `ongoing_at_window_end=true`입니다.

### 7.4 장애 지속시간

- 영문 키: `outage_duration_seconds`
- 수식: `recovery_time - outage_start`
- 두 시각이 모두 있을 때만 계산합니다.
- 회복하지 않았으면 `null`이며 사고 구간 끝까지의 시간을 임의 지속시간으로 대신 쓰지 않습니다.

### 7.5 서비스 경로 상태

| 상태 | 기준 |
|---|---|
| `outage_detected` | `outage_start`가 존재 |
| `degradation_observed` | breach는 있으나 연속 2개가 없어 outage_start가 없음 |
| `healthy` | 평가한 모든 버킷이 healthy이고 unknown·breach가 없음 |
| `unknown` | 임계치 없음, 평가 가능한 버킷 없음 또는 unknown 버킷 존재 |

이 상태는 합성 입력의 사용자 정의 임계치에 대한 판정입니다. 카카오페이증권의 실제 내부 SLO 또는 공식 장애 판정을 의미하지 않습니다.

## 8. 실행 상태와 종료 코드

### 8.1 `run.status`

#### `complete`

다음을 모두 충족한 성공입니다.

- 로그와 메트릭 파일이 모두 존재하고 각 파일에 구간 내 유효 행이 하나 이상 있습니다.
- 거부 행과 잘못되어 버린 선택 필드가 0개입니다.
- 분석 대상 경로를 매핑할 수 있습니다.
- 분석 대상 경로별 임계치가 있고 임계치에 필요한 표본이 충분합니다.
- 마스킹과 출력 검증이 성공했습니다.

#### `degraded`

분석은 성공했지만 다음 중 하나 이상이 있습니다.

- 로그 또는 메트릭 한 종류만 있습니다.
- 거부 행 또는 잘못되어 버린 선택 필드가 1개 이상입니다.
- 서비스 경로·의존성 매핑 일부가 `unknown`입니다.
- 분석 대상 경로의 임계치가 없거나 임계치 지표의 표본이 부족합니다.
- 관측 지연의 음수처럼 데이터 품질 문제가 있습니다.

`degraded`는 종료 코드 `0`이며 결과에 제한 사항과 issue code를 반드시 기록합니다.

#### `fatal`

분석을 안전하고 의미 있게 계속할 수 없는 상태입니다.

- 필수 파일·스키마·시간대·구간 오류
- 로그와 메트릭 모두 없음
- 유효한 구간 내 관측 레코드가 하나도 없음
- 지원 한도 초과
- 마스킹 실패 또는 고위험 비밀정보 잔존
- 최종 산출물 검증 실패

가능하면 비밀값과 원본 발췌가 없는 최소 `analysis.json`에 `fatal`과 issue code를 기록합니다. 안전하게 파일을 만들 수 없으면 표준 오류에 issue code만 출력합니다.

### 8.2 종료 코드

| 종료 코드 | 의미 |
|---:|---|
| `0` | `complete` 또는 `degraded` 성공 |
| `2` | 입력·스키마·시간대·구간·유효 레코드 오류 |
| `3` | 마스킹 실패 또는 분석 전 보안 차단 |
| `4` | 파일·레코드·번들 지원 한도 초과 |
| `5` | `analysis.json`·보고서·근거 참조·잔존 비밀정보 등 출력 검증 실패 |

### 8.3 여러 오류가 동시에 보일 때의 우선순위

다음 단계 순서에서 가장 먼저 실패한 하나를 프로세스 종료 코드로 사용하고 나머지는 안전하게 확인 가능한 범위에서 issues에 추가합니다.

1. 필수 경로·파일 존재·일반 파일·읽기 권한 검사 → `2`
2. 파일·번들 바이트 한도 검사 → `4`
3. `incident.json`과 `service-map.json` 구조·시간대·구간 검사 → `2`
4. 원본 민감정보 탐지·마스킹·재검사 → `3`
5. JSONL·CSV 레코드 수 한도 검사 → `4`
6. 레코드 파싱과 유효 레코드 존재 검사 → `2` 또는 `0 degraded`
7. 계산과 `analysis.json` 생성
8. 보고서·claim-evidence·잔존 비밀정보 검증 → `5`

## 9. 표준 issue code

### 9.1 입력·한도

| 코드 | 판정 기준 | 결과 |
|---|---|---|
| `INP001_MISSING_INCIDENT` | `incident.json` 없음 | fatal, exit 2 |
| `INP002_NO_TELEMETRY` | 로그·메트릭 모두 없음 | fatal, exit 2 |
| `INP003_UNSUPPORTED_ENTRY` | 허용하지 않은 파일·디렉터리·심볼릭 링크 발견 | fatal, exit 2 |
| `INP004_ENCODING` | UTF-8/UTF-8 BOM으로 읽을 수 없음 | fatal, exit 2 |
| `INP005_SCHEMA` | JSON·CSV 헤더·필수 필드·스키마 버전 오류 | fatal, exit 2 |
| `INP006_TIMEZONE` | IANA 시간대 또는 시각 오프셋 오류 | fatal, exit 2 |
| `INP007_WINDOW` | 구간 순서·길이·겹침·분 경계 오류 | fatal, exit 2 |
| `INP008_NO_VALID_RECORD` | 구간 내 유효 로그·메트릭이 모두 0개 | fatal, exit 2 |
| `INP009_SERVICE_MAP` | 제공된 서비스 맵의 중복·코드·참조 오류 | fatal, exit 2 |
| `LIM001_FILE_BYTES` | 파일별 바이트 한도 초과 | fatal, exit 4 |
| `LIM002_RECORD_COUNT` | JSONL·CSV 레코드 수 한도 초과 | fatal, exit 4 |
| `LIM003_RECORD_BYTES` | JSONL 한 행 바이트 한도 초과 | fatal, exit 4 |
| `LIM004_BUNDLE_BYTES` | 번들 전체 한도 초과 | fatal, exit 4 |

### 9.2 레코드·필드

| 코드 | 판정 기준 | 결과 |
|---|---|---|
| `REC001_SYNTAX` | JSONL 문법 또는 CSV 행 구조 오류 | 행 거부, degraded |
| `REC002_REQUIRED_FIELD` | 필수 필드 누락 | 행 거부, degraded |
| `REC003_TYPE` | 필수 필드 자료형 오류 | 행 거부, degraded |
| `REC004_ENUM` | 필수 코드·상태 허용값 오류 | 행 거부, degraded |
| `REC005_RANGE` | 필수 수치 범위·유한성 오류 | 행 거부, degraded |
| `FLD001_OPTIONAL_DROPPED` | 선택 필드가 존재하지만 유효하지 않음 | 필드 null, degraded |
| `MET001_COUNT_INCONSISTENT` | 버킷 error_count > request_count | 해당 버킷 집계 무효, degraded |
| `TIM001_OUTSIDE_WINDOW` | 유효 행이 두 분석 구간 밖 | 집계 제외, 상태 변화 없음 |
| `WRN001_UNKNOWN_FIELD` | 알 수 없는 추가 JSON 필드·CSV 열 | 무시, 상태 변화 없음 |

### 9.3 보안·출력

| 코드 | 판정 기준 | 결과 |
|---|---|---|
| `SEC001_SANITIZER_FAILURE` | 탐지·치환·임시 파일 생성 중 예외 또는 불완전 처리 | fatal, exit 3 |
| `SEC002_SENSITIVE_RESIDUE` | 마스킹 작업본 재검사에서 정의된 민감정보 패턴 1개 이상 | fatal, exit 3 |
| `OUT001_SCHEMA` | `analysis.json` 필수 구조·버전·자료형 오류 | fatal, exit 5 |
| `OUT002_BROKEN_EVIDENCE_REF` | 존재하지 않는 evidence ID 참조 | fatal, exit 5 |
| `OUT003_FACT_WITHOUT_EVIDENCE` | confirmed_fact의 evidence_refs가 0개 | fatal, exit 5 |
| `OUT004_REPORT_CLAIM_REF` | 보고서 사실 문장의 claim ID 누락·미존재 | fatal, exit 5 |
| `OUT005_SECRET_RESIDUE` | 임시·최종 산출물에서 seeded 원문 또는 10.1의 민감정보 패턴 발견 | fatal, exit 5 |

## 10. 민감정보 탐지·마스킹 기준

### 10.1 탐지 범주

탐지기는 Python `re`의 Unicode 기본 동작을 사용합니다. 아래 정규식은 계약 일부이며 구현이 임의로 바꿀 수 없습니다.

1. PEM private key

   ```regex
   -----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----[\\s\\S]*?-----END(?: [A-Z0-9]+)? PRIVATE KEY-----
   ```

   전체 일치값을 `[REDACTED:PRIVATE_KEY]`로 바꿉니다.

2. Bearer token

   ```regex
   (?i)\\bAuthorization\\s*:\\s*Bearer\\s+[A-Za-z0-9._~+/=-]+
   ```

   전체 일치값을 `Authorization: [REDACTED:BEARER_TOKEN]`으로 바꿉니다.

3. JWT 후보

   ```regex
   \\b[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}\\b
   ```

   전체 일치값을 `[REDACTED:JWT]`로 바꿉니다.

4. 비밀 key-value

   ```regex
   (?i)\\b(api_key|access_token|secret|password|passwd|session_token|cookie)\\b\\s*[:=]\\s*[\"']?([^\\s,\"';}]+)
   ```

   첫 번째 캡처의 키 이름과 구분자는 유지하고 두 번째 캡처의 값만 `[REDACTED:SECRET]`로 바꿉니다.

5. 이메일

   ```regex
   (?i)\\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}\\b
   ```

   전체 일치값을 `[REDACTED:EMAIL]`로 바꿉니다.

6. 한국 전화번호

   ```regex
   (?<!\\d)(?:\\+82[- ]?|0)(?:10|2|[3-6][1-5])[- ]?\\d{3,4}[- ]?\\d{4}(?!\\d)
   ```

   전체 일치값을 `[REDACTED:PHONE]`으로 바꿉니다.

7. 계좌 식별값

   ```regex
   (?i)(account(?:_no|_number)?|계좌(?:번호)?)\\s*[:=]?\\s*\\d(?:[- ]?\\d){7,15}
   ```

   라벨은 유지하고 숫자 값만 `[REDACTED:ACCOUNT]`로 바꿉니다.

정규식은 코드 문자열로 옮길 때 raw string을 사용합니다. 대소문자 플래그가 패턴에 포함된 경우 별도 플래그를 중복 적용해 의미를 바꾸지 않습니다.

### 10.2 마스킹 성공과 실패

- 탐지값은 `[REDACTED:<TYPE>]`으로 치환합니다.
- `sanitization-report.md`에는 유형, 개수와 `파일명:행 번호`만 기록하고 원값·원값 일부·해시는 기록하지 않습니다.
- 원본 절대경로 대신 번들 기준 논리 파일명만 기록합니다.
- 마스킹 작업본을 같은 패턴으로 다시 검사합니다.
- 표에 정의한 패턴이 1개라도 남거나 탐지·치환 과정에서 예외가 발생하면 마스킹 실패입니다.
- 마스킹 실패 시 Codex가 원본을 읽는 우회 경로는 없습니다.
- 정규식 탐지는 모든 개인정보 제거를 보장하지 않으며 MVP는 합성 fixture의 seeded pattern에 대한 검증만 주장합니다.

## 11. evidence·claim과 가설 신뢰도

### 11.1 evidence

각 evidence는 다음을 가집니다.

- `evidence_id`: `E-001` 형식, 파일 내 유일
- `source_type`: `incident`, `log`, `metric`, `service_map` 중 하나
- `source_file`: 절대경로가 아닌 논리 파일명
- `source_location`: 예: `logs.jsonl:L42`, `metrics.csv:R15`
- `time_window`: 적용 시 `[start, end)`
- `masked_excerpt`: 선택, 마스킹 후 최대 300 Unicode 문자

### 11.2 claim

- `claim_id`: `C-001` 형식, 파일 내 유일
- `claim_type`: `confirmed_fact`, `hypothesis`, `unknown`
- `confirmed_fact`는 하나 이상의 존재하는 `evidence_refs`가 필수입니다.
- `hypothesis`는 하나 이상의 `supporting_evidence_refs`가 있어야 합니다. 지지 근거가 없으면 hypothesis가 아니라 `unknown`입니다.
- 가설은 `contradicting_evidence_refs`, `missing_data`와 `confidence`를 가집니다.
- `openbell-report.md`의 모든 사실 문장은 문장 끝에 `[C-001]` 형식의 claim ID를 표시합니다.

### 11.3 독립 근거와 신뢰도

독립 근거 유형은 `source_type` 기준입니다. 같은 `logs.jsonl`의 여러 행은 여러 evidence일 수 있지만 하나의 근거 유형입니다. `log`와 `metric`은 직접 관측 근거이고 `incident`와 `service_map`은 설정·구조 근거입니다.

| 신뢰도 | 판정 기준 |
|---|---|
| `high` | 지지 근거에 `log`와 `metric`이 모두 있고, 반대 근거가 0개이며 `missing_data`가 비어 있음 |
| `medium` | 지지 근거가 1개 이상이고 `log` 또는 `metric`이 포함되며 반대 근거가 0개이지만 high 조건은 아님 |
| `low` | 지지 근거는 1개 이상이나 직접 관측 근거가 없거나 반대 근거가 1개 이상 있음 |
| `unknown` | 지지 근거가 0개 |

`missing_data`가 하나 이상이면 high가 될 수 없지만 직접 근거가 있고 반대 근거가 없으면 medium일 수 있습니다. 숫자 확률을 만들지 않습니다. 오류 문자열 하나, 시간상 동시 발생 하나 또는 Techlog의 유사 사례만으로 근본 원인을 확정하지 않습니다.

## 12. 계산하지 않거나 확정하지 않는 값

다음 값은 MVP 표준 지표가 아니므로 계산된 사실처럼 출력할 수 없습니다.

- 실제 카카오페이증권의 가용성·SLO 준수율
- 실제 영향 고객 수·주문 수·금전 손실·보상액
- 근본 원인의 확률 또는 법적 책임
- 평균 지연시간, Apdex, 오류 예산, MTTR·MTBF
- 로그 누락률: 예상 로그 수가 입력에 없으므로 계산 불가
- CPU·메모리 “포화”: 공식 임계치가 없으므로 수치만 제시
- 두 데이터 소스의 불일치율에 대한 정상·오류 판정

이 목록의 값을 새로 사용하려면 정의, 수식, 단위, grain, 포함·제외, `null`, 임계치와 테스트를 이 문서에 먼저 추가해야 합니다.

## 13. 경계값 예시

### 13.1 오류율

- 요청 60개, 오류 3개 → `3 / 60 × 100 = 5.000%`
- 요청 0개, 오류 0개 → `null (zero_denominator)`
- 오류율 임계치가 5%일 때 5.000%는 healthy이고 5.001%는 breach입니다.

### 13.2 nearest-rank

- 1부터 20까지 정렬된 표본 20개의 p95 rank는 `ceil(0.95 × 20) = 19`이므로 p95는 19입니다.
- 같은 20개 표본은 p99 최소 표본 100개를 충족하지 못하므로 p99는 `null`입니다.

### 13.3 연속 버킷

- `healthy → breach → breach`: 두 번째 breach가 확인되는 시점에 첫 breach 버킷을 outage_start로 기록합니다.
- `breach → unknown → breach`: unknown이 연속 수를 끊으므로 outage_start가 아닙니다.
- `outage → healthy → healthy`: 첫 healthy 버킷을 recovery_time으로 기록합니다.

### 13.4 지원 한도

- `logs.jsonl`이 정확히 50 MiB이면 크기 기준을 통과합니다.
- 50 MiB + 1바이트이면 `LIM001_FILE_BYTES`, exit `4`입니다.
- 정확히 100,000행이면 통과하고 100,001행이면 `LIM002_RECORD_COUNT`, exit `4`입니다.

## 14. 구현 및 테스트 의무

Phase 4에서 다음을 자동화합니다.

1. 각 M-ID의 정상값, 경계값, `null`과 반올림 Golden test
2. 상태값 4종과 다중 임계치의 breach·healthy·unknown test
3. 각 issue code를 최소 한 번 발생시키는 fixture
4. 종료 코드 우선순위 test
5. 로그 주 소스와 메트릭 fallback test
6. physical = accepted + rejected 불변식 test
7. seeded secret의 마스킹 작업본·JSON·Markdown 잔존 0건 test
8. confirmed_fact·hypothesis·unknown과 evidence 참조 무결성 test
9. 문서 계약 버전·SHA-256과 제출용 복사본 일치 test
10. 다른 코드 경로가 같은 M-ID를 서로 다른 수식으로 계산하지 않는 회귀 test
11. 지원 한도 경계 fixture에 대한 M-016·M-017 반복 benchmark와 환경 기록

실제 코드나 테스트가 만들어지기 전에는 이 계약을 “검증 완료”라고 표현하지 않습니다.
