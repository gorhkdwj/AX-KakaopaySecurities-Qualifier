---
name: openbell-guard
description: Analyze a synthetic or anonymized post-incident brokerage bundle for market-open and external-broker degradation; produce a machine-verifiable analysis and evidence-backed report.
---

# OpenBell Guard

OpenBell Guard는 카카오페이증권 AX 해커톤 제출물을 위한 Codex Skill입니다.

현재 구현 상태는 Phase 4의 P4-19 제출 패키징 검증 단계까지입니다. 플러그인 구조, 지표 계약 복사본, 최소 합성 fixture, `run_openbell.py --bundle --output` 실행 입구, 독립 출력 검증기 `validate_bundle.py --output`, `analysis.json` 기반 `openbell-report.md` 보고서 초안 생성 흐름, A~H 합성 시나리오 통합 테스트, `benchmark_openbell.py` 기반 M-016·M-017 benchmark, 그리고 `submission.zip` 생성·구조 검증 도구가 있습니다.

## 현재 사용 가능한 범위

- 분석 대상은 합성 또는 익명화된 사고 분석 번들로 제한합니다.
- 실제 고객정보, 계좌정보, API 키, 토큰, 비밀번호가 포함된 운영 원본 데이터는 받지 않습니다.
- CLI는 번들의 허용 파일, 필수 파일, UTF-8, 파일 크기, `incident.json` 시간 창과 선택 `service-map.json` 구조를 검사합니다.
- CLI는 7개 민감정보 패턴을 마스킹한 `sanitized-bundle/`과 `sanitization-report.md`를 생성합니다.
- CLI는 마스킹된 `logs.jsonl`과 `metrics.csv`를 행 단위로 검증해 M-014 기준 `record-summary.json`을 생성합니다.
- CLI는 유효한 구간 내 행을 UTC 60초 버킷으로 정렬해 `bucket-summary.json`을 생성합니다.
- CLI는 M-001~M-007 기본 지표, M-008~M-009 관측 지연 지표, M-010~M-013 기준 구간 대비 비교 지표, M-015 CPU·메모리 맥락 지표를 계산해 `metric-summary.json`을 생성합니다.
- CLI는 설정된 임계치로 버킷 상태, 서비스 경로 상태, 장애 시작과 회복 시각을 판정해 `state-summary.json`을 생성합니다.
- CLI는 확인된 사실, 원인 가설, 판단 불가 항목을 근거 ID와 연결해 `evidence-summary.json`을 생성합니다.
- CLI는 중간 산출물을 병합해 최종 기계 검증용 `analysis.json`을 생성합니다.
- CLI는 검증 가능한 `analysis.json`만 사용해 사람용 Markdown 초안인 `openbell-report.md`를 생성합니다. 이 초안은 원본 로그를 다시 읽지 않습니다.
- CLI는 `analysis.json` 구조, evidence 참조, confirmed_fact 근거, 보고서 claim marker, 민감정보 잔존 여부를 자체 검증해 `output-validation.json`을 생성합니다.
- benchmark CLI는 합성 지원 한도 번들을 생성하고 1회 준비 실행 후 5회 측정 실행으로 M-016 실행시간 중앙값과 M-017 Python 추적 메모리 최고값을 기록합니다.
- 제출 패키징 도구는 프로젝트 루트의 `README.md`, `src/`, `logs/`를 `submission.zip`으로 묶고, 필수 파일·금지 폴더·로그 형식을 검사합니다.

## 실행 예시

```bash
python src/skills/openbell-guard/scripts/run_openbell.py --bundle src/tests/fixtures/domestic-market-open-min/bundle --output out/domestic-market-open-min
```

생성된 출력만 다시 검증하려면 다음 명령을 사용합니다.

```bash
python src/skills/openbell-guard/scripts/validate_bundle.py --output out/domestic-market-open-min
```

지원 한도 합성 benchmark를 실행하려면 다음 명령을 사용합니다.

```bash
python src/skills/openbell-guard/scripts/benchmark_openbell.py --output out/p4-18-benchmark
```

성공하면 다음 파일과 폴더가 생성됩니다.

- `openbell-cli-summary.json`
- `sanitized-bundle/`
- `sanitization-report.md`
- `record-summary.json`
- `bucket-summary.json`
- `metric-summary.json`
- `state-summary.json`
- `evidence-summary.json`
- `analysis.json`
- `openbell-report.md`
- `output-validation.json`

`analysis.json`은 P4-18 기준 최종 기계 검증용 원장이며, `openbell-report.md`는 이 원장을 사람이 읽기 쉽게 옮긴 검토용 초안입니다. `output-validation.json`은 원장, 보고서 claim marker와 산출물의 자체 검증 결과입니다.
`benchmark-summary.json`과 `benchmark-report.md`는 P4-18 기준 로컬 합성 benchmark 결과이며, 운영환경 성능 보장을 의미하지 않습니다.

## 기본 지표 계산 기준

- M-001 `request_count`: 서비스 경로 × 60초 버킷의 요청 수입니다.
- M-002 `error_count`: `error`, `timeout`, `rejected` 상태의 요청 수입니다.
- M-003 `throughput_rps`: `request_count / 60`입니다.
- M-004 `error_rate_pct`: `error_count / request_count × 100`입니다. 분모가 0이면 `null`과 `reason_code=zero_denominator`를 기록합니다.
- M-005 `latency_p50_ms`: latency 표본의 nearest-rank p50입니다.
- M-006 `latency_p95_ms`: latency 표본이 20개 미만이면 `null`과 `reason_code=insufficient_sample`을 기록합니다.
- M-007 `latency_p99_ms`: latency 표본이 100개 미만이면 `null`과 `reason_code=insufficient_sample`을 기록합니다.

로그가 하나 이상 유효한 분석 구간 안에 있으면 M-001~M-007의 주 계산 소스는 `logs.jsonl`입니다. 로그가 없고 유효한 `metrics.csv`만 있으면 `metrics.csv`를 주 계산 소스로 사용합니다.

메트릭 fallback에서 같은 서비스 경로·60초 버킷의 `error_count`가 `request_count`보다 크면 해당 버킷의 요청 수, 오류 수, 처리량과 오류율을 `null`로 두고 `MET001_COUNT_INCONSISTENT`를 기록합니다.

## 관측 지연과 기준 비교 계산 기준

- M-008 `ingestion_lag_ms`: 로그 입력에서는 `observed_time - event_time`으로 내부 계산합니다. 개별 값 목록은 산출물에 쓰지 않고 표본 수와 누락 수만 남깁니다.
- M-009 `ingestion_lag_p50_ms`, `ingestion_lag_p95_ms`, `ingestion_lag_p99_ms`: 유효한 관측 지연 표본의 nearest-rank 백분위수입니다.
- `metrics.csv`만 유효한 경우에는 `ingestion_lag_sample_ms`를 관측 지연 표본으로 사용합니다.
- M-010 `baseline_median`: 기준 구간의 유효한 60초 버킷 값 중앙값입니다.
- M-011 `incident_peak`: 사고 구간의 유효한 60초 버킷 값 최댓값입니다.
- M-012 `change_abs`: `incident_peak - baseline_median`입니다.
- M-013 `change_pct`: `(incident_peak - baseline_median) / baseline_median × 100`입니다. 기준값이 0이면 `null`과 `reason_code=zero_denominator`를 기록합니다.

## CPU·메모리 맥락 지표 기준

- M-015 `cpu_utilization_median_pct`, `memory_utilization_median_pct`: `metrics.csv`의 CPU·메모리 percent 표본을 서비스 경로 × 60초 버킷별 중앙값으로 계산합니다.
- CPU·메모리 표본은 로그 존재 여부와 관계없이 `context_metrics`에 보존합니다.
- CPU·메모리 값은 맥락 근거로만 사용하며, 높은 수치만으로 자원 포화나 근본 원인을 확정하지 않습니다.

## P4-18 benchmark 기준

- M-016 `deterministic_pipeline_wall_time_seconds`: `run_openbell.py`의 결정론적 로컬 파이프라인을 같은 프로세스 조건에서 5회 측정한 실행시간 중앙값입니다.
- M-017 `peak_python_memory_mib`: 같은 측정 구간에서 Python 표준 라이브러리 `tracemalloc`으로 추적한 최고 Python 할당 메모리입니다.
- 기본 benchmark 입력은 `logs.jsonl` 100,000행, `metrics.csv` 50,000행의 합성 지원 한도 번들입니다.
- 통과 기준은 5회 모두 exit 0, M-016 중앙값 60초 이하, M-017 최고값 512 MiB 이하입니다.
- 이 값은 로컬 합성 benchmark 결과이며 운영환경 처리 성능, 전체 프로세스 메모리, OS 파일 캐시 또는 native memory를 보장하지 않습니다.

## 상태 판정 기준

- 버킷 상태는 `breach`, `healthy`, `unknown` 중 하나입니다.
- 설정된 임계치 중 하나라도 계산 가능한 값이 엄격하게 `>` 임계치이면 `breach`입니다.
- 설정된 모든 임계치가 계산 가능하고 각각 `<=` 임계치이면 `healthy`입니다.
- 임계치가 없거나 필요한 지표가 `null`이면 `unknown`입니다.
- 사고 구간에서 `breach` 버킷이 2개 연속이면 첫 번째 breach 버킷을 `outage_start`로 기록합니다.
- 장애 시작 후 `healthy` 버킷이 2개 연속이면 첫 번째 healthy 버킷을 `recovery_time`으로 기록합니다.
- 이 판정은 입력 번들에 사용자가 정의한 임계치 기준이며, 카카오페이증권의 실제 내부 SLO나 공식 장애 판정을 의미하지 않습니다.

## evidence·claim 기준

- `evidence-summary.json`은 `incident`, `log`, `metric`, `service_map` 근거를 `E-001` 형식 ID로 기록합니다.
- `confirmed_fact` claim은 하나 이상의 존재하는 evidence ID를 참조합니다.
- `hypothesis` claim은 지지 근거, 반대 근거, 추가 필요 데이터와 `high`, `medium`, `low`, `unknown` 중 하나의 질적 신뢰도를 가집니다.
- `unknown` claim은 현재 입력만으로 확정할 수 없는 내용을 `missing_data`와 함께 기록합니다.
- 로그 원문 메시지를 그대로 쓰지 않고, 계산 요약과 원래 위치만 근거로 남깁니다.
- CPU·메모리 값은 맥락 근거로 사용할 수 있지만, 단독으로 자원 포화나 근본 원인을 확정하지 않습니다.

## analysis.json, openbell-report.md와 output-validation.json 기준

- `analysis.json`은 `record-summary.json`, `metric-summary.json`, `state-summary.json`, `evidence-summary.json`을 병합한 기계 검증용 기준 산출물입니다.
- `contract_version`, 계약 파일 SHA-256, 사고 구간, 처리 레코드 수, 서비스 경로 상태, bucket 지표, 비교 지표, 맥락 지표, evidence와 claim을 포함합니다.
- `analysis.json`에는 원본 번들의 절대경로와 원문 로그 메시지를 넣지 않습니다.
- `openbell-report.md`는 `analysis.json`을 바탕으로 분석 기준, 사고 구간, 서비스 경로 영향, 60초 버킷 요약, 확인된 사실, 원인 가설, 추가 확인 필요를 나눠 작성합니다.
- `openbell-report.md`의 확인된 사실·원인 가설·추가 확인 필요 문장은 `[C-001]` 형식의 claim ID로 끝나야 합니다.
- `output-validation.json`은 `analysis.json` 구조, 끊어진 evidence 참조, 근거 없는 `confirmed_fact`, 보고서 claim marker 누락·미존재, 민감정보 잔존 여부를 기록합니다.
- `OUT004_REPORT_CLAIM_REF`는 P4-16부터 활성화되어, 보고서 claim 문장에 없는 claim ID가 붙거나 필요한 claim ID가 빠지면 fatal 오류로 처리합니다.

## P4-17 통합 시나리오 검증 범위

- A. 국내장 개장 피크와 경로별 부분 장애: 시세·관심종목 경로가 느려져도 주문 경로가 정상일 수 있음을 분리합니다.
- B. 외부 중개사 장애: `overseas_broker` 의존성과 내부 정상 경로를 분리합니다.
- C. 불완전 데이터: 임계치나 보조 telemetry가 부족하면 가능한 계산만 수행하고 `degraded`·`unknown`으로 남깁니다.
- D. 비밀정보 포함 입력: 합성 secret 원값이 마스킹 작업본과 최종 산출물에 남지 않는지 확인합니다.
- E. 서비스 정상·로그 유입 지연: 서비스 오류율은 정상인데 관측 지연만 큰 경우 서비스 장애로 단정하지 않습니다.
- F. 타임아웃 증상과 경쟁 가설: `DB connection timeout` 같은 메시지를 DB 또는 JVM 근본 원인으로 승격하지 않습니다.
- G. 통계 경계와 임계치: `>` 임계치 비교, 2개 연속 breach, 2개 연속 healthy 회복 규칙을 검증합니다.
- H. 손상 입력과 지원 한도: 손상 행은 degraded로 기록하고 파일 한도 초과는 exit 4로 중단합니다.

## 안전 원칙

- OpenBell Guard는 읽기 전용 분석 도구입니다.
- 실제 주문, 주문 취소, 계좌 조작, 고객 데이터 변경 기능을 구현하거나 실행하지 않습니다.
- 합성 데이터 분석 결과를 카카오페이증권의 실제 내부 원인으로 단정하지 않습니다.
- 데이터가 부족하면 추정하지 않고 `null`, `reason_code`, 또는 후속 단계의 `판단 불가`로 표시합니다.

## Phase 4 완료 상태와 다음 범위

P4-19 기준으로 자동화 가능한 제출 패키징 검증은 완료됐습니다. 별도 새 Codex 앱 세션에서 UI 기반 설치와 신뢰 승인을 직접 확인하는 절차는 최종 제출 전 수동 확인 후보입니다.

다음 개발 후보는 Phase 5 합성 시나리오·자동 검증 확장 또는 Phase 6 최종 제출 점검입니다.
