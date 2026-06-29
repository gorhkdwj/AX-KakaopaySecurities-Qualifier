---
name: openbell-guard
description: Analyze a synthetic or anonymized post-incident brokerage bundle for market-open and external-broker degradation; produce a machine-verifiable analysis and evidence-backed report.
---

# OpenBell Guard

OpenBell Guard는 카카오페이증권 AX 해커톤 제출물을 위한 Codex Skill입니다.

현재 구현 상태는 Phase 4의 P4-10 관측 지연·기준 비교 계산 단계입니다. 플러그인 구조, 지표 계약 복사본, 최소 합성 fixture와 `run_openbell.py --bundle --output` 실행 입구가 있습니다.

## 현재 사용 가능한 범위

- 분석 대상은 합성 또는 익명화된 사고 분석 번들로 제한합니다.
- 실제 고객정보, 계좌정보, API 키, 토큰, 비밀번호가 포함된 운영 원본 데이터는 받지 않습니다.
- CLI는 번들의 허용 파일, 필수 파일, UTF-8, 파일 크기, `incident.json` 시간 창과 선택 `service-map.json` 구조를 검사합니다.
- CLI는 7개 민감정보 패턴을 마스킹한 `sanitized-bundle/`과 `sanitization-report.md`를 생성합니다.
- CLI는 마스킹된 `logs.jsonl`과 `metrics.csv`를 행 단위로 검증해 M-014 기준 `record-summary.json`을 생성합니다.
- CLI는 유효한 구간 내 행을 UTC 60초 버킷으로 정렬해 `bucket-summary.json`을 생성합니다.
- CLI는 M-001~M-007 기본 지표, M-008~M-009 관측 지연 지표, M-010~M-013 기준 구간 대비 비교 지표를 계산해 `metric-summary.json`을 생성합니다.
- 아직 최종 분석 산출물인 `analysis.json`, evidence, claim, 장애 상태 판정, Markdown 보고서는 생성하지 않습니다.

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

이 산출물들은 P4-10 중간 분석 결과입니다. 최종 제출용 보고서 기준 산출물인 `analysis.json`은 아직 생성하지 않습니다.

## 기본 지표 계산 기준

- M-001 `request_count`: 서비스 경로 × 60초 버킷의 요청 수입니다.
- M-002 `error_count`: `error`, `timeout`, `rejected` 상태의 요청 수입니다.
- M-003 `throughput_rps`: `request_count / 60`입니다.
- M-004 `error_rate_pct`: `error_count / request_count × 100`입니다. 분모가 0이면 `null`과 `reason_code=zero_denominator`를 기록합니다.
- M-005 `latency_p50_ms`: latency 표본의 nearest-rank p50입니다.
- M-006 `latency_p95_ms`: latency 표본이 20개 미만이면 `null`과 `reason_code=insufficient_sample`을 기록합니다.
- M-007 `latency_p99_ms`: latency 표본이 100개 미만이면 `null`과 `reason_code=insufficient_sample`을 기록합니다.

로그가 하나 이상 유효한 분석 구간 안에 있으면 M-001~M-007의 주 계산 소스는 `logs.jsonl`입니다. 로그가 없고 유효한 `metrics.csv`만 있으면 `metrics.csv`를 주 계산 소스로 사용합니다.

## 관측 지연과 기준 비교 계산 기준

- M-008 `ingestion_lag_ms`: 로그 입력에서는 `observed_time - event_time`으로 내부 계산합니다. 개별 값 목록은 산출물에 펼치지 않고 표본 수와 누락 수만 남깁니다.
- M-009 `ingestion_lag_p50_ms`, `ingestion_lag_p95_ms`, `ingestion_lag_p99_ms`: 유효한 관측 지연 표본의 nearest-rank 백분위수입니다.
- `metrics.csv`만 유효한 경우에는 `ingestion_lag_sample_ms`를 관측 지연 표본으로 사용합니다.
- M-010 `baseline_median`: 기준 구간의 유효한 60초 버킷 값 중앙값입니다.
- M-011 `incident_peak`: 사고 구간의 유효한 60초 버킷 값 최댓값입니다.
- M-012 `change_abs`: `incident_peak - baseline_median`입니다.
- M-013 `change_pct`: `(incident_peak - baseline_median) / baseline_median × 100`입니다. 기준값이 0이면 `null`과 `reason_code=zero_denominator`를 기록합니다.

## 안전 원칙

- OpenBell Guard는 읽기 전용 분석 도구입니다.
- 실제 주문, 주문 취소, 계좌 조작, 고객 데이터 변경 기능을 구현하거나 실행하지 않습니다.
- 합성 데이터 분석 결과를 카카오페이증권의 실제 내부 원인으로 단정하지 않습니다.
- 데이터가 부족하면 추정하지 않고 `null`, `reason_code`, 또는 후속 단계의 `판단 불가`로 표시합니다.

## 다음 구현 예정 범위

다음 단계에서는 상태 판정, evidence·claim, 최종 `analysis.json` 생성을 순차적으로 구현합니다.
