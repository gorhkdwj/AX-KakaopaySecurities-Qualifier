# OpenBell Guard Semantic Model Builder 보고서

> 작성일: 2026-06-30  
> 목적: Phase 4 구현 전에 지표·데이터 grain·판정 기준의 단일 의미 계층을 확정합니다.  
> 상세 단일 기준: [OpenBell Guard 지표·수식·판정 기준 계약](../openbell-guard-metrics-validation-contract.md)

## 1. 결과

OpenBell Guard에서 사용할 지표·수식·입력 검증·장애 상태·오류 코드를 계약 버전 `1.0.0`으로 동결했습니다. 실제 수식과 경계값은 단일 기준 문서에만 두며 이 보고서는 의미 계층의 구성과 적용 결과만 요약합니다.

## 2. 데이터 모델과 grain

| 자산 | 한 행 또는 객체의 의미 |
|---|---|
| `incident.json` | 사고 번들 하나의 분석 구간·표시 시간대·사용자 정의 임계치 |
| `logs.jsonl` | 요청 결과 관측값 하나 |
| `metrics.csv` | 표준 metric_name의 60초 집계값 하나 또는 개별 표본 하나 |
| `service-map.json` | 서비스 이름 하나와 표준 고객 경로·의존성 관계 |
| `analysis.json.metrics` | 서비스 경로 × 60초 버킷 또는 서비스 경로 × 지표 요약 |
| `analysis.json.evidence` | 논리 파일 위치에 연결된 마스킹 근거 하나 |
| `analysis.json.claims` | 확인된 사실·가설·판단 불가 주장 하나 |

## 3. 지표 묶음

- M-001~M-004: 요청 수, 오류 수, 처리량과 오류율
- M-005~M-009: 지연시간과 관측 지연의 백분위수
- M-010~M-013: 기준 중앙값, 사고 최고값과 변화량
- M-014: 처리·거부·제외·선택 필드 폐기 건수
- M-015: CPU·메모리 맥락 지표
- M-016~M-017: 결정론적 파이프라인 실행시간과 Python 추적 메모리 benchmark

정의되지 않은 평균 지연, 가용성, SLO 준수율, 영향 고객 수, 손실액과 원인 확률은 계산하지 않습니다.

## 4. 판정 계층

- 버킷 상태: `breach`, `healthy`, `unknown`
- 경로 상태: `outage_detected`, `degradation_observed`, `healthy`, `unknown`
- 실행 상태: `complete`, `degraded`, `fatal`
- 프로세스 종료: 성공 `0`, 입력 `2`, 보안 `3`, 한도 `4`, 출력 검증 `5`
- 오류 식별: `INP`, `LIM`, `REC`, `FLD`, `MET`, `TIM`, `WRN`, `SEC`, `OUT` 접두사의 표준 issue code

## 5. 변경 통제

- 다른 문서와 코드에서는 수식을 복사하지 않고 M-ID와 issue code를 참조합니다.
- 의미가 바뀌면 단일 계약, 계약 버전과 Decisionlog를 코드보다 먼저 갱신합니다.
- Phase 4에서 제출용 계약 복사본과 개발 원본의 SHA-256 일치를 자동 검사합니다.
- 각 M-ID·issue code·경계값·`null` reason code를 fixture와 Golden test에 연결합니다.

## 6. 구현 전 남은 작업

- 입력·출력 JSON Schema 작성
- 계약 `1.0.0`의 대표 Golden fixture 작성
- 각 issue code와 종료 코드 우선순위 테스트 작성
- 계산 함수·테스트 이름과 M-ID 연결
- 제출용 계약 복사본과 SHA-256 검사 구현

이 보고서는 설계 완료 기록이며 실제 코드와 테스트가 통과했다는 의미는 아닙니다.
