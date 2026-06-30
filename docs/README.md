# OpenBell Guard 문서 안내

이 디렉터리는 카카오페이증권 AX 해커톤 프로젝트의 조사 근거와 개발 가이드를 보관합니다.
영문 공식문서를 그대로 복사하기보다, 공식 원문을 바탕으로 OpenBell Guard에 필요한 내용을 한국어로 재구성했습니다.

## 권장 읽기 순서

1. [조사 및 기획서](./openbell-guard-research-plan.md)  
   카카오페이증권의 공개된 문제, 문제 선정 이유, 플러그인 설계와 검증 계획을 설명합니다.
2. [지표·수식·판정 기준 계약](./openbell-guard-metrics-validation-contract.md)  
   구현에 사용하는 모든 지표, grain, 단위, 수식, 반올림, `null`, 임계치, 실행 상태, 오류 코드와 경계값의 유일한 기준입니다.
   의미 계층의 구성 결과는 [Semantic Model Builder 보고서](./reviews/semantic-model-builder_report.md)에서 요약합니다.
3. [서브에이전트 운영·구현 분담 가이드](./subagent-operating-guide.md)  
   Phase 4~6의 작업 패킷, 역할, 파일 소유권, 병렬화 범위, 핸드오프와 품질 게이트를 설명합니다.
4. [Phase 4 실제 구현 순서와 검증 계획](./phase4-implementation-sequence.md)  
   가장 작은 기능 단위부터 어떤 순서로 만들고 무엇을 검증할지, 각 단계가 어떤 지표·오류 코드와 연결되는지 설명합니다.
5. [P4-17 통합 시나리오 매트릭스](./p4-17-scenario-matrix.md)  
   A~H 합성 시나리오가 어떤 입력과 기대 결과로 OpenBell Guard를 검증하는지 설명합니다.
6. [P4-18 성능·회귀 benchmark 결과](./p4-18-benchmark-report.md)  
   지원 한도 합성 입력에서 M-016 실행시간과 M-017 Python 추적 메모리를 측정한 결과와 경량화 조치를 설명합니다.
7. [P4-19 설치·호출·제출 패키징 검증 보고서](./p4-19-packaging-report.md)
   제출 ZIP 생성, 공식 플러그인·Skill 검증, ZIP 구조 검사, 제출 경로 기준 실행 검증, 임시 Codex marketplace 설치 확인과 새 세션 인식 결과를 설명합니다.
8. [P4-14~P4-18 제출 전 검토 보고서](./p4-14-to-p4-18-review-report.md)
   비전공자 초급자도 이해할 수 있도록 P4-14~P4-18 핵심 결과물, 검증 의미, 한계와 P4-19 전 확인사항을 통합 설명합니다.
9. [수동 테스트·휴먼 리뷰 안내](./manual-test-reports/README.md)
   사용자가 더미 데이터로 직접 실행한 입력·결과 위치와 사람이 검토할 체크리스트를 설명합니다.
10. [구현 트러블슈팅 로그](../Troubleshootinglog.md)
   구현 중 실제로 발생한 오류, 검증 실패, 환경 의존성 문제, 도구 제한과 해결 과정을 T-ID로 누적 기록합니다.
11. [기획서 최종 QA 점검 보고서](./reviews/analysis-qa-checklist_report.md)
   Phase 4 구현 전에 보완할 입력·통계·보안·근거·플러그인 규격 항목을 우선순위별로 정리합니다.
12. [최종 QA P0 여섯 항목 초급자 설명](./guides/methodology-explainer_report.md)
   여섯 보완 항목의 문제·해결 구조·선정 이유를 비유와 구체적인 입력·출력 예시로 설명합니다.
13. [호그와트 도서관 프로젝트 초급자 가이드](./guides/hogwarts-library-beginner-guide.md)
   로그·메트릭과 OpenTelemetry·Kafka·ClickHouse의 역할을 비전공자 눈높이로 설명합니다.
14. [카카오페이증권 로그 플랫폼 Techlog 활용성 검토](./reviews/pallas-v2-log-platform-review.md)
   실제 로그 플랫폼 설계 중 OpenBell Guard에 채택할 원칙과 제외할 인프라를 구분합니다.
15. [카카오페이 JVM 웜업 Techlog 활용성 검토](./reviews/jvm-warm-up-review.md)
   배포 직후 지연의 원인 분석 절차와 OpenBell Guard 적용 비용을 검토하고, JVM·Kubernetes 구현 제외 근거를 설명합니다.
16. [카카오페이 Spring Batch Partitioning Techlog 활용성 검토](./reviews/spring-batch-partitioning-review.md)
   대량 데이터를 나누고 스트리밍한 원칙 중 Python 로컬 분석기에 적용할 후보와 병렬화 제외 근거를 설명합니다.
17. [Codex 활용 모범 사례](./guides/codex-best-practices.md)
   Codex에 일을 요청하고 계획·검증하는 방법을 이 프로젝트에 맞게 설명합니다.
18. [AGENTS.md 사용 가이드](./guides/agents-md-guide.md)
   프로젝트 지침 파일의 역할과 현재 루트 `AGENTS.md`의 사용법을 설명합니다.
19. [Notion 기록 운영 가이드](./notion-recording-guide.md)
   로컬 원본 기록과 AX 허브·MyProject·Study DB를 작업 완료마다 동기화하는 방법을 설명합니다.
20. [Codex 플러그인 개요](./guides/plugin-overview.md)
   플러그인, Skill, MCP의 차이와 OpenBell Guard의 구성 방향을 설명합니다.
21. [OpenBell Guard 플러그인 제작 가이드](./guides/plugin-build-guide.md)
   디렉터리 구조, manifest, 구현 순서와 검증·패키징 방법을 설명합니다.
22. [출처 목록](./SOURCES.md)
   각 해설 문서가 참고한 공식 원문과 확인일을 기록합니다.

## 문서 성격

- `openbell-guard-research-plan.md`는 프로젝트 고유의 조사·기획 기준선입니다.
- `openbell-guard-metrics-validation-contract.md`는 지표·수식·오류 판정의 단일 기준이며 다른 문서는 이 내용을 복제하지 않고 연결합니다.
- `subagent-operating-guide.md`는 구현 작업을 분배할 때 역할·파일 소유권·핸드오프와 통합 게이트를 정하는 운영 기준입니다.
- `phase4-implementation-sequence.md`는 실제 코드를 만들 순서와 각 단계의 검증·유의점·관련 M-ID·issue code, 단계 완료 보고 형식을 연결한 실행 계획입니다.
- `p4-17-scenario-matrix.md`는 A~H 합성 시나리오와 통합 테스트의 기대 결과를 설명합니다.
- `p4-18-benchmark-report.md`는 합성 지원 한도 입력의 실행시간·Python 추적 메모리 benchmark와 출력 경량화 조치를 설명합니다.
- `p4-19-packaging-report.md`는 제출 ZIP 생성과 검증, 패키지 내부 실행 결과, 임시 Codex marketplace 설치 확인, 새 Codex 비대화 세션 인식 결과와 UI 클릭 검증 한계를 설명합니다.
- `p4-14-to-p4-18-review-report.md`는 P4-19 전에 사용자가 읽고 검토할 수 있도록 핵심 결과물과 검증 의미를 통합 설명합니다.
- `manual-test-reports/`는 사용자가 직접 실행한 더미 데이터 테스트의 위치, 결과 요약과 휴먼 리뷰 체크리스트를 보관합니다.
- 루트 `Troubleshootinglog.md`는 구현 중 실제로 발생한 문제와 해결 과정을 누적하는 별도 기록입니다.
- `tools/preflight_check.py`는 반복된 트러블슈팅 항목을 긴 문서 재독해 없이 빠르게 확인하는 표준 라이브러리 기반 사전 점검 도구입니다.
- `references/kakaopay-techlog/`는 사용자가 제공한 카카오페이 Techlog 원문 또는 로컬 복사본의 보관 위치입니다.
- `reviews/`는 기업 공개 기술 자료의 프로젝트 적용 여부를 검토한 기록입니다.
- `guides/`의 문서는 OpenAI 공식문서를 요약하고 프로젝트에 맞게 해설한 문서입니다.
- 해설 문서는 공식문서의 번역본이나 완전한 사본이 아닙니다.
- 플러그인 스키마, CLI 명령처럼 변경될 수 있는 사항은 구현 및 제출 직전에 공식 원문을 다시 확인합니다.

## 관리 원칙

- 외부 자료를 추가하면 원본 URL과 확인일을 `SOURCES.md`에 기록합니다.
- 카카오페이 Techlog는 URL만 제공해도 검토할 수 있으며, 로컬 원문을 제공할 때는 `references/kakaopay-techlog/<URL-slug>.<확장자>`에 둡니다.
- 확인된 공식 요구사항과 프로젝트에서 선택한 설계를 구분해 작성합니다.
- 지표·수식·오류 기준을 변경할 때는 단일 계약을 먼저 갱신하고 계약 버전·Decisionlog·fixture·코드·제출 문서를 함께 맞춥니다.
- Phase 4 이후 구현·검증 전에는 프로젝트 루트에서 필요한 경우 `python tools/preflight_check.py`를 실행해 반복된 환경·구조 문제를 먼저 확인합니다.
- 직접 실행한 수동 테스트 입력과 결과는 기본적으로 `out/manual-tests/`에 남기고, 사람이 검토할 요약 보고서만 `docs/manual-test-reports/`에 둡니다.
- 아직 구현하거나 검증하지 않은 기능을 완료된 것처럼 표현하지 않습니다.
- 조사 근거가 바뀌면 기획서, README, 질문지와 실제 구현의 설명을 함께 갱신합니다.
- `docs/`는 개발 참고자료이며 최종 `submission.zip`에는 기본적으로 포함하지 않습니다.

## 포트폴리오 활용 문서

- [OpenBell Guard 포트폴리오 KPI 요약](./portfolio-kpi-summary.md)
  프로젝트의 핵심성과, KPI 스코어카드, 포트폴리오 문장 예시와 과장하면 안 되는 표현을 한곳에 모은 문서입니다.
