# OpenBell Guard 플러그인 제작 가이드

> 문서 유형: OpenAI 공식문서 기반 프로젝트 특화 해설본  
> 대상 프로젝트: OpenBell Guard  
> 공식 원문: [Build plugins](https://developers.openai.com/codex/plugins/build), [Agent Skills](https://developers.openai.com/codex/skills)  
> 최종 확인일: 2026-06-30  
> 주의: `plugin.json` 스키마와 설치 명령은 구현·제출 직전에 공식 원문 및 실제 검증기로 확인합니다.
> 프로젝트 지표·오류 단일 기준: [OpenBell Guard 지표·수식·판정 기준 계약](../openbell-guard-metrics-validation-contract.md)

## 먼저 알아둘 말: MVP

`MVP`는 **Minimum Viable Product**의 약자이며, 한국어로는 보통 `최소 기능 제품` 또는 `최소 실행 가능 제품`이라고 합니다.

여기서 `최소`는 대충 만들거나 핵심 기능이 빠진 미완성품이라는 뜻이 아닙니다. 사용자가 해결하려는 가장 중요한 문제를 **처음부터 끝까지 실제로 처리하고 검증할 수 있는 가장 작은 버전**이라는 뜻입니다.

OpenBell Guard의 MVP는 최소한 다음 흐름이 모두 작동해야 합니다.

1. 장애 종료 후 합성 사고 번들 폴더 경로를 입력받습니다.
2. 형식·시간대·지원 한도와 비밀정보를 검사하고 안전한 파생 입력을 만듭니다.
3. 지표·판정 계약의 M-ID와 issue code에 따라 Python으로 계산·판정합니다.
4. 주문·시세·외부 연계 등 서비스 경로별 영향을 구분합니다.
5. 확인된 사실, 원인 가설과 추가 확인 필요 사항을 분리합니다.
6. `analysis.json`, `openbell-report.md`, `sanitization-report.md`를 생성합니다.
7. 대표 합성 시나리오의 기대 결과와 실제 결과를 테스트로 비교합니다.

따라서 `MVP에 반영한다`는 말은 단순한 아이디어 목록에 적는 것이 아니라, 첫 제출 가능한 버전의 코드·Skill·출력 형식·테스트 중 필요한 곳에 실제로 넣고 검증한다는 뜻입니다.

반면 실제 카카오페이증권 시스템 연결, 외부 API·MCP, Kafka·ClickHouse·Kubernetes 인프라와 화려한 화면은 핵심 흐름이 아니므로 MVP 이후의 선택 기능입니다.

## 1. 목표 제출 구조

AX 해커톤 제출 구조와 Codex 플러그인 구조를 함께 만족해야 합니다.

```text
submission.zip
├── src/
│   ├── .codex-plugin/
│   │   └── plugin.json
│   ├── skills/
│   │   └── openbell-guard/
│   │       ├── SKILL.md
│   │       ├── scripts/
│   │       │   ├── run_openbell.py
│   │       │   ├── redact_inputs.py
│   │       │   ├── analyze_telemetry.py
│   │       │   └── validate_bundle.py
│   │       ├── references/
│   │       │   ├── input-contract.md
│   │       │   ├── analysis-contract.md
│   │       │   ├── metrics-validation-contract.md
│   │       │   ├── evidence-policy.md
│   │       │   ├── incident-taxonomy.md
│   │       │   ├── service-path-model.md
│   │       │   └── report-template.md
│   │       └── assets/
│   │           ├── incident-example.json
│   │           └── service-map-example.json
│   └── tests/
│       ├── fixtures/
│       └── test_analyzer.py
├── README.md
└── logs/
```

`src/`가 플러그인 루트입니다. `.codex-plugin/` 안에는 `plugin.json`만 두고 Skill, 스크립트와 assets는 플러그인 루트 쪽에 둡니다.

## 2. 최소 manifest

초기 버전의 `src/.codex-plugin/plugin.json`은 실제로 존재하는 구성요소만 선언합니다.

```json
{
  "name": "openbell-guard",
  "version": "0.1.0",
  "description": "Analyze brokerage telemetry for market-open and external-dependency incidents with evidence-backed reports.",
  "skills": "./skills/"
}
```

원칙은 다음과 같습니다.

- `name`은 안정적인 소문자 kebab-case `openbell-guard`를 사용합니다. 제출 루트 `src/`의 이름과 같을 필요는 없습니다.
- 경로는 플러그인 루트 기준 상대경로이며 `./`로 시작합니다.
- `.mcp.json`, 앱 또는 hooks가 없으면 관련 필드를 선언하지 않습니다.
- 임시 문구나 존재하지 않는 홈페이지·개인정보처리방침 링크를 넣지 않습니다.
- 공식 검증기가 허용하지 않는 선택 필드는 제거합니다.

## 3. Skill 메타데이터

`src/skills/openbell-guard/SKILL.md`는 최소한 이름과 설명을 포함합니다.

```md
---
name: openbell-guard
description: Analyze a synthetic or anonymized post-incident brokerage bundle for market-open and external-broker degradation; produce a machine-verifiable analysis and evidence-backed report.
---
```

설명은 Codex가 Skill을 언제 사용해야 하는지 판단하는 핵심 정보입니다. 다음 요청과 자연스럽게 연결돼야 합니다.

- “개장 직후 지연 로그를 분석해주십시오.”
- “주문 경로와 시세 경로의 영향을 구분해주십시오.”
- “외부 중개사 장애 사후 보고서를 만들어주십시오.”

## 4. Skill의 실행 순서

`SKILL.md`에는 다음 절차를 명시합니다.

1. 사용자가 지정한 사고 번들 폴더 경로를 확인합니다. 원본 내용을 대화에 붙여넣지 않습니다.
2. `run_openbell.py`로 단일 계약의 파일·스키마·시간대·지원 한도와 비밀정보 기준을 검사합니다.
3. 마스킹된 임시 작업본과 `sanitization-report.md`를 생성하며 실패하면 중단합니다.
4. 결정론적 분석기로 60초 통계와 evidence·claim을 담은 `analysis.json`을 생성합니다.
5. Codex는 원본이 아니라 `analysis.json`과 제한된 마스킹 근거만 읽습니다.
6. 사실·원인 가설·추가 확인 필요를 분리해 `openbell-report.md`를 작성합니다.
7. `validate_bundle.py`로 claim-evidence 참조와 비밀정보 잔존을 검사합니다.
8. 결과 파일, 실행 상태와 미검증 범위를 사용자에게 보고합니다.

실행 중 실제 주문, 운영 시스템 변경 또는 운영 주소 부하 테스트는 하지 않습니다.

## 5. 코드와 AI의 역할 분리

### 결정론적 스크립트

- 지표·판정 계약의 입력 스키마와 issue code 검증
- 시간대 정규화
- M-ID별 지표와 장애 상태 계산
- 비밀정보 패턴 탐지와 마스킹
- evidence·claim이 연결된 `analysis.json` 생성·검증

### Codex

- 여러 데이터 사이의 시간 관계 종합
- 주문·시세·관심종목·외부 연계 경로별 영향 설명
- 경쟁하는 원인 가설과 반대 근거 구성
- 누락된 데이터와 추가 조사 항목 식별
- `openbell-report.md` 작성

숫자 계산을 자연어 추론에만 맡기지 않고, 공개 근거로 알 수 없는 실제 내부 원인을 만들어내지 않습니다.

## 6. 합성 fixture를 먼저 정의합니다

분석기보다 기대 결과를 먼저 고정하면 무엇을 검증해야 하는지 명확해집니다.

| fixture | 핵심 상황 | 기대 판단 |
|---|---|---|
| `domestic-market-open` | 개장 직후 시세·관심종목 지연, 주문 정상 | 부분 장애로 분류 |
| `external-broker` | 내부 지표 정상, 해외 브로커 타임아웃 | 외부 의존성 상위 가설 |
| `partial-data` | 로그 또는 메트릭 누락·손상 행 | degraded, 누락·거부 위치 보고 |
| `secret-containing-input` | 테스트용 토큰·계좌 패턴 포함 | 마스킹 또는 안전 중단 |
| `misleading-timeout` | 타임아웃 증상만 있고 원인 근거 부족 | DB·JVM 원인 확정 금지 |
| `support-limit` | 지원 한도 경계값과 초과 | 경계 처리, 초과 종료 코드 4 |

합성 데이터는 공개 사건의 현상만 참고하며 실제 내부 로그나 실제 근본 원인을 재현한다고 주장하지 않습니다.

## 7. 구현 순서

1. 공식 스캐폴드 도구로 manifest와 Skill 구조를 생성합니다.
2. 단일 지표·판정 계약에서 입력·분석 JSON Schema, 합성 fixture와 기대 `analysis.json`을 작성합니다.
3. 입력·민감정보 검증기를 구현합니다.
4. 텔레메트리 통계 분석기를 구현합니다.
5. 단위 테스트와 Golden fixture 테스트를 통과시킵니다.
6. `run_openbell.py`는 마스킹·분석을, Codex는 보고서 작성을, `validate_bundle.py`는 최종 검증을 담당하도록 `SKILL.md`에서 대표 요청 한 번의 흐름으로 연결합니다.
7. Codex 재시작 후 새 스레드에서 설치·발견·자동 선택·명시 호출을 확인합니다.
8. 실제 검증 결과를 README와 질문 5문항에 반영합니다.
9. 제출용 디렉터리를 만들고 ZIP 내부 구조를 재검사합니다.

## 8. 검증 체크리스트

### 구조

- [ ] `src/.codex-plugin/plugin.json`이 존재합니다.
- [ ] manifest 이름과 플러그인 ID가 일치합니다.
- [ ] manifest가 선언한 모든 경로가 존재합니다.
- [ ] `SKILL.md`의 메타데이터와 설명이 유효합니다.
- [ ] 공식 플러그인 및 Skill 검증기가 통과합니다.

### 기능

- [ ] 고정 입력의 통계가 기대값과 일치합니다.
- [ ] 모든 M-ID·issue code·경계값·`null` reason code와 종료 코드가 단일 계약과 일치합니다.
- [ ] 개발용 계약과 `src/` 제출용 복사본의 계약 버전·SHA-256이 일치합니다.
- [ ] 주문 정상·시세 지연을 전체 주문장애로 오판하지 않습니다.
- [ ] 내부 장애와 외부 중개사 장애를 구분합니다.
- [ ] 불완전 데이터에서 근본 원인을 확정하지 않습니다.
- [ ] 모든 사실 claim에 유효한 evidence가 있고 보고서 claim ID가 검증됩니다.
- [ ] 기본 산출물은 `analysis.json`, `openbell-report.md`, `sanitization-report.md` 세 개입니다.

### 보안

- [ ] 원본 입력을 수정하지 않습니다.
- [ ] Codex가 원본 번들을 직접 열지 않고 마스킹·분석 결과만 읽습니다.
- [ ] 테스트용 비밀정보가 최종 출력에 남지 않습니다.
- [ ] 실제 고객 데이터와 운영 주소를 사용하지 않습니다.
- [ ] 기본 동작이 읽기 전용입니다.

### 제출

- [ ] README의 기능 설명과 실제 구현이 일치합니다.
- [ ] 질문 5문항은 실제 검증 결과만 사용합니다.
- [ ] `logs/`의 원본을 편집하지 않았습니다.
- [ ] `submission.zip`의 루트에는 `src/`, `README.md`, `logs/`가 있습니다.
- [ ] 개발 문서, 캐시, 임시 출력과 비밀정보가 ZIP에 포함되지 않았습니다.

## 9. 로컬 설치와 Marketplace

개발 중에는 공식 `plugin-creator` 흐름과 저장소의 `.agents/plugins/marketplace.json`을 사용해 플러그인이 실제로 발견되는지 확인합니다. Marketplace 항목은 `./src`를 가리키며 개발 편의를 위한 것이므로 AX 해커톤 `submission.zip`에는 넣지 않습니다.

- 개발용 Marketplace 경로와 제출용 `src/`를 혼동하지 않습니다.
- Marketplace 항목은 실제 플러그인 경로를 가리키게 합니다.
- 플러그인을 수정한 뒤 공식 절차로 재설치하고 Codex를 재시작합니다.
- 새 스레드에서 플러그인 발견, 설명에 따른 자동 선택, 명시적 호출을 각각 확인합니다.
- 최종 제출물은 Marketplace 설치 없이도 구조와 코드를 심사할 수 있어야 합니다.

## 10. 자주 발생하는 실수

- `plugin.json`을 `src/` 바로 아래에 둡니다.
- Skill과 assets를 `.codex-plugin/` 안에 넣습니다.
- 존재하지 않는 MCP·앱·hook을 manifest에 선언합니다.
- 스크립트는 있지만 `SKILL.md`에서 언제 실행할지 설명하지 않습니다.
- 테스트 fixture의 정답을 실제 사건의 원인처럼 README에 씁니다.
- 설치 확인 없이 파일 구조만 보고 플러그인이 동작한다고 판단합니다.
- 개발 편의를 위해 로그 원본을 재포맷하거나 일부만 제출합니다.

정확한 필드 허용 범위와 설치 명령은 구현 시점의 공식문서와 실제 검증 결과를 최종 기준으로 삼습니다.
