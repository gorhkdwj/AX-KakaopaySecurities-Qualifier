---
name: openbell-guard
description: Analyze a synthetic or anonymized post-incident brokerage bundle for market-open and external-broker degradation; produce a machine-verifiable analysis and evidence-backed report.
---

# OpenBell Guard

OpenBell Guard는 카카오페이증권 AX 해커톤 제출물을 위한 Codex Skill입니다.

현재 이 파일은 Phase 4의 P4-01 스캐폴드 단계입니다. 플러그인이 발견될 수 있는 최소 구조와 Skill 메타데이터만 정의하며, 실제 분석 스크립트·입력 계약 복사본·fixture·보고서 템플릿은 아직 구현하지 않았습니다.

## 현재 사용 가능 범위

- 플러그인 이름과 Skill 이름은 `openbell-guard`로 고정합니다.
- 분석 대상은 합성 또는 익명화된 사고 분석 번들로 제한합니다.
- 실제 고객정보, 계좌정보, API 키, 토큰, 비밀번호가 포함된 원본 운영 데이터는 받지 않습니다.
- 현재 단계에서는 사용자가 분석 실행을 요청해도 분석을 수행하지 않고, 구현 전 상태임을 알립니다.

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
