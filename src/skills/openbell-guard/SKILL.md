---
name: openbell-guard
description: Analyze a synthetic or anonymized post-incident brokerage bundle for market-open and external-broker degradation; produce a machine-verifiable analysis and evidence-backed report.
---

# OpenBell Guard

OpenBell Guard는 카카오페이증권 AX 해커톤 제출물을 위한 Codex Skill입니다.

현재 구현 상태는 Phase 4의 P4-07 행 단위 파서 단계입니다. 플러그인 구조, 지표 계약 복사본, 최소 합성 fixture와 `run_openbell.py --bundle --output` 실행 입구가 있습니다. CLI는 번들의 허용 파일, 필수 파일, UTF-8, 파일 크기, `incident.json` 시간 창과 선택 `service-map.json` 구조를 검사한 뒤, 7개 민감정보 패턴을 마스킹한 `sanitized-bundle/`과 `sanitization-report.md`를 생성합니다. 이어서 마스킹된 `logs.jsonl`과 `metrics.csv`를 행 단위로 검증해 M-014 기준 `record-summary.json`을 생성합니다. 다만 아직 지표를 계산하거나, 최종 `analysis.json`을 생성하지 않습니다.

## 현재 사용 가능 범위

- 플러그인 이름과 Skill 이름은 `openbell-guard`로 고정합니다.
- 분석 대상은 합성 또는 익명화된 사고 분석 번들로 제한합니다.
- 실제 고객정보, 계좌정보, API 키, 토큰, 비밀번호가 포함된 원본 운영 데이터는 받지 않습니다.
- 현재 단계에서는 CLI 경로 점검, 번들 사전 검사, 민감정보 마스킹 작업본 생성과 행 단위 레코드 요약 생성을 수행할 수 있습니다.
- 실행 예시는 다음과 같습니다.

```bash
python src/skills/openbell-guard/scripts/run_openbell.py --bundle src/tests/fixtures/domestic-market-open-min/bundle --output out/domestic-market-open-min
```

- 성공하면 `openbell-cli-summary.json`, `sanitized-bundle/`, `sanitization-report.md`, `record-summary.json`을 생성합니다. 이 파일들은 P4-07 사전 처리 결과이며 최종 분석 산출물인 `analysis.json`은 아닙니다.
- 사용자가 분석 실행을 요청하면, 아직 지표 계산기는 구현 전이며 다음 단계에서 서비스 정규화와 지표 계산을 순차 구현한다고 안내합니다.

## 예정된 실행 흐름

다음 단계에서 구현될 흐름은 아래와 같습니다.

1. 입력 계약과 metric 정의를 확인합니다.
2. 로컬 Python 분석기를 실행해 번들을 검증하고 정규화합니다.
3. 서비스 경로별 지연, 오류, 외부 의존성 징후와 증거 연결을 계산합니다.
4. `analysis.json`과 `sanitization-report.md`를 생성합니다.
5. Codex는 검증된 산출물을 읽고 `확인된 사실`, `원인 가설`, `추가 확인 필요`를 분리한 보고서 초안을 작성합니다.

## 안전 원칙

- OpenBell Guard는 읽기 전용 분석 도구로 유지합니다.
- 실제 주문, 주문 취소, 계좌 조작, 고객 데이터 변경 기능을 구현하지 않습니다.
- 합성 데이터 분석 결과를 카카오페이증권의 실제 내부 원인으로 단정하지 않습니다.
- 데이터가 부족하면 추정하지 않고 `판단 불가` 또는 `추가 확인 필요`로 표시합니다.
