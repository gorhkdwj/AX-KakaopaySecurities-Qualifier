# 문서 출처 목록

> 최종 확인일: 2026-06-30  
> 문서 성격: 공식 원문을 기반으로 한 프로젝트 특화 해설 문서의 출처 기록

## Codex 공식문서

| 로컬 해설 문서 | 공식 원문 | 용도 | 확인일 |
|---|---|---|---|
| `guides/codex-best-practices.md` | [Best practices](https://developers.openai.com/codex/learn/best-practices) | 프롬프트, 계획, AGENTS.md, 검증, MCP, Skill, 자동화와 세션 관리 | 2026-06-28 |
| `guides/agents-md-guide.md` | [Custom instructions with AGENTS.md](https://developers.openai.com/codex/guides/agents-md) | 전역·프로젝트 지침 탐색과 우선순위 | 2026-06-28 |
| `guides/plugin-overview.md` | [Plugins](https://developers.openai.com/codex/plugins) | 플러그인의 역할, 구성요소, 설치와 권한 | 2026-06-28 |
| `guides/plugin-build-guide.md` | [Build plugins](https://developers.openai.com/codex/plugins/build) | 플러그인 구조, manifest, 배포와 Marketplace | 2026-06-28 |
| `guides/plugin-build-guide.md` | [Agent Skills](https://developers.openai.com/codex/skills) | Skill 구조, 설명, 스크립트와 참고자료 | 2026-06-28 |
| `reviews/analysis-qa-checklist_report.md` | [Build plugins](https://developers.openai.com/codex/plugins/build), [Plugins](https://developers.openai.com/codex/plugins) | 기획서의 manifest·Skill·Marketplace 설치 검증 계획과 로컬 이름 규칙 대조 | 2026-06-30 |

## 프로젝트 문제 조사 출처

카카오페이증권 사건, 성장 지표, 산업 통계와 감독당국 자료는
[`openbell-guard-research-plan.md`의 출처 목록](./openbell-guard-research-plan.md#17-출처-목록)에 기록합니다.

`reviews/analysis-qa-checklist_report.md`는 2026-06-30에 위 출처 목록의 핵심 링크를 다시 열어 기획서 문장과 대조했습니다.

## 기업 Techlog 검토 출처

| 로컬 검토 문서 | 공식 원문 | 용도 | 확인일 |
|---|---|---|---|
| `guides/hogwarts-library-beginner-guide.md` | [일 41TB, 200억 건의 로그를 ClickStack으로 실시간 처리하기](https://tech.kakaopay.com/post/pallas-v2-log-platform/) | 로그 플랫폼 구조와 OpenBell Guard에 필요한 개념을 초급자 관점에서 설명 | 2026-06-29 |
| `reviews/pallas-v2-log-platform-review.md` | [일 41TB, 200억 건의 로그를 ClickStack으로 실시간 처리하기](https://tech.kakaopay.com/post/pallas-v2-log-platform/) | 카카오페이증권의 로그 플랫폼, 장 시작 트래픽 스파이크, 관측 지연과 조회 패턴 확인 | 2026-06-29 |
| `reviews/jvm-warm-up-review.md` | [배포 직후 발생하는 응답 지연을 해결하기 위한 여정 (feat. JVM 웜업)](https://tech.kakaopay.com/post/jvm-warm-up/) | 카카오페이 굿딜 서비스의 원인 분석 절차를 OpenBell Guard에 적용할 수 있는지와 구현 비용 검토 | 2026-06-29 |
| `reviews/spring-batch-partitioning-review.md` | [수억 건의 데이터, 맛있게 쪼개 먹는 방법 (with. Partitioning)](https://tech.kakaopay.com/post/spring-batch-partitioning/) | 카카오페이 정산플랫폼팀의 대량 데이터 분할·스트리밍·일괄 처리 원칙과 OpenBell Guard 적용 비용 검토 | 2026-06-29 |

## 기술 공식 문서

| 로컬 검토 문서 | 공식 원문 | 용도 | 확인일 |
|---|---|---|---|
| `reviews/spring-batch-partitioning-review.md` | [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html) | 복잡한 병렬화 전 단순 구현 측정 원칙과 Partitioning의 manager·worker 구조 확인 | 2026-06-29 |

## 사용 시 주의사항

- 로컬 가이드는 공식문서 전체를 복제한 문서가 아니라 OpenBell Guard에 필요한 내용을 재구성한 해설본입니다.
- 공식문서의 URL이나 구조가 바뀌면 새 원문을 확인하고 확인일을 갱신합니다.
- `plugin.json` 필드, 설치 명령, Marketplace 규격 등 실행에 직접 영향을 주는 내용은 공식 원문과 실제 검증기를 우선합니다.
- 외부 문장을 그대로 장문 인용하지 않고 사실과 요구사항을 요약해 기록합니다.
