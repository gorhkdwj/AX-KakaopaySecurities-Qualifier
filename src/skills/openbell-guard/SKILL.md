---
name: openbell-guard
description: Analyze a synthetic or anonymized post-incident brokerage bundle for market-open and external-broker degradation; produce a machine-verifiable analysis and evidence-backed report.
---

# OpenBell Guard

OpenBell Guard는 카카오페이증권 AX 해커톤 제출물을 위한 Codex Skill입니다.

현재 구현 상태는 Phase 4의 P4-14 analysis/sanitization 출력 단계입니다. 플러그인 구조, 지표 계약 복사본, 최소 합성 fixture와 `run_openbell.py --bundle --output` 실행 입구가 있습니다.

## 현재 사용 가능한 범위

- 분석 대상은 합성 또는 익명화된 사고 분석 번들로 제한합니다.
- 실제 고객정보, 계좌정보, API 키, 토큰, 비밀번호가 포함된 운영 원본 데이터는 받지 않습니다.
- CLI는 번들의 허용 파일, 필수 파일, UTF-8, 파일 크기, `incident.json` 시간 창과 선택 `service-map.json` 구조를 검사합니다.
- CLI는 7개 민감정보 패턴을 마스킹한 `sanitized-bundle/`과 `sanitization-report.md`를 생성합니다.
- CLI는 마스킹된 `logs.jsonl`과 `metrics.csv`를 행 단위로 검증해 M-014 기준 `record-summary.json`을 생성합니다.
- CLI는 유효한 구간 내 행을 UTC 60초 버킷으로 정렬해 `bucket-summary.json`을 생성합니다.
- CLI는 M-001~M-007 기본 지표, M-008~M-009 관측 지연 지표, M-010~M-013 기준 구간 대비 비교 지표를 계산해 `metric-summary.json`을 생성합니다.
- CLI는 로그가 유효하면 로그를 주 계산 소스로 사용하고, 로그가 없고 유효한 `metrics.csv`만 있으면 메트릭 fallback으로 M-001~M-009를 계산합니다.
- CLI는 `metrics.csv`의 CPU·메모리 percent 표본을 M-015 맥락 지표로 집계해 `metric-summary.json`의 `context_metrics`에 보존합니다.
- CLI는 메트릭 fallback에서 같은 버킷의 `error_count > request_count`가 발견되면 `MET001_COUNT_INCONSISTENT`로 기록하고 해당 요청·오류 집계를 무효화합니다.
- CLI는 설정된 임계치로 버킷 상태, 서비스 경로 상태, 장애 시작과 회복 시각을 판정해 `state-summary.json`을 생성합니다.
- CLI는 확인된 사실, 원인 가설과 판단 불가 항목을 근거 ID와 연결해 `evidence-summary.json`을 생성합니다.
- CLI는 중간 산출물을 병합해 최종 기계 검증용 `analysis.json`을 생성합니다.
- 아직 사람용 Markdown 보고서인 `openbell-report.md`는 생성하지 않습니다.

## 실행 예시

```bash
python src/skills/openbell-guard/scripts/run_openbell.py --bundle src/tests/fixtures/domestic-market-open-min/bundle --output out/domestic-market-open-min
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

`analysis.json`은 P4-14 기준 최종 기계 검증용 원장입니다. 아직 사람용 Markdown 보고서인 `openbell-report.md`는 생성하지 않습니다.

## 기본 지표 계산 기준

- M-001 `request_count`: 서비스 경로 × 60초 버킷의 요청 수입니다.
- M-002 `error_count`: `error`, `timeout`, `rejected` 상태의 요청 수입니다.
- M-003 `throughput_rps`: `request_count / 60`입니다.
- M-004 `error_rate_pct`: `error_count / request_count × 100`입니다. 분모가 0이면 `null`과 `reason_code=zero_denominator`를 기록합니다.
- M-005 `latency_p50_ms`: latency 표본의 nearest-rank p50입니다.
- M-006 `latency_p95_ms`: latency 표본이 20개 미만이면 `null`과 `reason_code=insufficient_sample`을 기록합니다.
- M-007 `latency_p99_ms`: latency 표본이 100개 미만이면 `null`과 `reason_code=insufficient_sample`을 기록합니다.

로그가 하나 이상 유효한 분석 구간 안에 있으면 M-001~M-007의 주 계산 소스는 `logs.jsonl`입니다. 로그가 없고 유효한 `metrics.csv`만 있으면 `metrics.csv`를 주 계산 소스로 사용합니다.
메트릭 fallback에서 같은 서비스 경로·60초 버킷의 `error_count`가 `request_count`보다 크면 해당 버킷의 요청 수, 오류 수, 처리량과 오류율을 `null`로 두고 `reason_code=not_applicable` 및 `MET001_COUNT_INCONSISTENT`를 기록합니다.

## 관측 지연과 기준 비교 계산 기준

- M-008 `ingestion_lag_ms`: 로그 입력에서는 `observed_time - event_time`으로 내부 계산합니다. 개별 값 목록은 산출물에 펼치지 않고 표본 수와 누락 수만 남깁니다.
- M-009 `ingestion_lag_p50_ms`, `ingestion_lag_p95_ms`, `ingestion_lag_p99_ms`: 유효한 관측 지연 표본의 nearest-rank 백분위수입니다.
- `metrics.csv`만 유효한 경우에는 `ingestion_lag_sample_ms`를 관측 지연 표본으로 사용합니다.
- M-010 `baseline_median`: 기준 구간의 유효한 60초 버킷 값 중앙값입니다.
- M-011 `incident_peak`: 사고 구간의 유효한 60초 버킷 값 최댓값입니다.
- M-012 `change_abs`: `incident_peak - baseline_median`입니다.
- M-013 `change_pct`: `(incident_peak - baseline_median) / baseline_median × 100`입니다. 기준값이 0이면 `null`과 `reason_code=zero_denominator`를 기록합니다.

## CPU·메모리 맥락 지표 기준

- M-015 `cpu_utilization_median_pct`, `memory_utilization_median_pct`: `metrics.csv`의 CPU·메모리 percent 표본을 서비스 경로 × 60초 버킷별 중앙값으로 계산합니다.
- CPU·메모리 표본은 로그 존재 여부와 관계없이 `context_metrics`에 보존합니다.
- CPU·메모리 값은 원인 가설의 맥락 자료일 뿐이며, 높은 수치만으로 자원 포화나 근본 원인을 단정하지 않습니다.
- CPU·메모리 개별 표본 목록은 산출물에 펼치지 않고 중앙값, 표본 수와 근거 위치만 남깁니다.

## 상태 판정 기준

- 버킷 상태는 `breach`, `healthy`, `unknown` 중 하나입니다.
- 설정된 임계치 중 하나라도 계산 가능한 값이 엄격하게 `>` 임계치이면 `breach`입니다.
- 설정된 모든 임계치가 계산 가능하고 각각 `<=` 임계치이면 `healthy`입니다.
- 임계치가 없거나 필요한 지표가 `null`이면 `unknown`입니다.
- 사고 구간에서 `breach` 버킷이 2개 연속이면 첫 번째 breach 버킷을 `outage_start`로 기록합니다.
- 장애 시작 후 `healthy` 버킷이 2개 연속이면 첫 번째 healthy 버킷을 `recovery_time`으로 기록합니다.
- 이 판정은 입력 번들의 사용자 정의 임계치 기준이며, 카카오페이증권의 실제 내부 SLO 또는 공식 장애 판정을 의미하지 않습니다.

## evidence·claim 기준

- `evidence-summary.json`은 `incident`, `log`, `metric`, `service_map` 근거를 `E-001` 형식 ID로 기록합니다.
- `confirmed_fact` claim은 하나 이상의 존재하는 evidence ID를 참조합니다.
- `hypothesis` claim은 지지 근거, 반대 근거, 추가 필요 데이터와 `high`, `medium`, `low`, `unknown` 중 하나의 질적 신뢰도를 가집니다.
- `unknown` claim은 현재 입력만으로 확정할 수 없는 내용을 `missing_data`와 함께 기록합니다.
- 로그 원문 메시지를 그대로 펼치지 않고, 계산된 요약과 논리 위치만 근거로 남깁니다.
- CPU·메모리 값은 맥락 근거로 사용할 수 있지만, 단독으로 자원 포화나 근본 원인을 확정하지 않습니다.

## analysis.json 기준

- `analysis.json`은 `record-summary.json`, `metric-summary.json`, `state-summary.json`, `evidence-summary.json`을 병합한 기계 검증용 기준 산출물입니다.
- `contract_version`, 계약 파일 SHA-256, 사고 구간, 처리 레코드 수, 서비스 경로 상태, bucket 지표, 비교 지표, 맥락 지표, evidence와 claim을 포함합니다.
- `analysis.json`에는 원본 번들의 절대경로와 원문 로그 메시지를 넣지 않습니다.
- `analysis.json`은 보고서 초안이 아니라 후속 출력 검증기와 Markdown 보고서 작성의 입력입니다.

## 안전 원칙

- OpenBell Guard는 읽기 전용 분석 도구입니다.
- 실제 주문, 주문 취소, 계좌 조작, 고객 데이터 변경 기능을 구현하거나 실행하지 않습니다.
- 합성 데이터 분석 결과를 카카오페이증권의 실제 내부 원인으로 단정하지 않습니다.
- 데이터가 부족하면 추정하지 않고 `null`, `reason_code`, 또는 후속 단계의 `판단 불가`로 표시합니다.

## 다음 구현 예정 범위

다음 단계에서는 출력 검증기, 보고서 템플릿, 파이프라인 실행시간·Python 추적 메모리 benchmark를 순차적으로 구현합니다.
