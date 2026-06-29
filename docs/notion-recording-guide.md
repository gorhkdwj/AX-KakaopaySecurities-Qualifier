# OpenBell Guard Notion 기록 운영 가이드

> 적용 시작일: 2026-06-29  
> 목적: 로컬 원본 기록을 보존하면서 프로젝트 진행 과정과 학습을 포트폴리오 형태로 Notion에 동기화합니다.

## 1. 기록 체계

| 위치 | 역할 | 사실 기준 여부 |
|---|---|---|
| `logs/` | AI 대화 원본 JSONL | 원본 |
| `Worklog.md` | 사용자 요청 단위의 수행·검증 기록 | 기준 |
| `Decisionlog.md` | 중요 결정의 선택지·근거·영향 | 기준 |
| MyProject DB | 단계·주요 작업·결정 포트폴리오 | 구조화 요약 |
| Study DB | 기술 학습·공개 자료 분석 | 구조화 요약 |
| AX 허브 | 전체 탐색 시작점 | 링크·현황 요약 |

Notion은 로컬 기록을 대체하지 않습니다. 서로 어긋나면 로컬 파일과 실제 산출물·테스트 결과를 기준으로 Notion을 수정합니다.

## 2. Notion 대상

### AX 허브

- 페이지: [조코딩 AX해커톤](https://app.notion.com/p/38d05ea68bfc80ec9db7d8d05e31a41e)
- 용도: 프로젝트 소개, 현재 상태, 공개 근거, MyProject·Study DB 진입점
- 연결 보기: `OpenBell Guard 단계별 진행`
- 보기 ID: `view://38d05ea6-8bfc-8162-a2ed-000cbeaf0579`

### MyProject DB

- DB: [MyProject](https://app.notion.com/p/2df05ea68bfc80bc9b76d5f802535c95)
- 데이터 소스: `collection://2df05ea6-8bfc-806d-8f2d-000ba60550ca`
- 메인 페이지: [[PJ12][AX] OpenBell Guard](https://app.notion.com/p/38d05ea68bfc8132b3a0df71bce7aad8)
- 용도: Phase, 주요 작업, 결정, 상태와 포트폴리오 결과

### Study DB

- DB 보기: [Study DB 보기](https://app.notion.com/p/38d05ea68bfc804bbe61c4a7ce4843ed)
- 데이터 소스: `collection://2bc05ea6-8bfc-8071-8f1a-000b7c69d214`
- 인덱스: [[AX] OpenBell Guard 학습·문서 인덱스](https://app.notion.com/p/38d05ea68bfc8068aab3d16e4a594b41)
- 필터: `Topic = 조코딩 AX해커톤`
- 용도: 기술 개념, 공식 자료, 초급자 학습과 프로젝트 적용 판단

## 3. MyProject Phase

| Phase | 페이지 | 상태 |
|---|---|---|
| 0 | [프로젝트 운영·기록 기반](https://app.notion.com/p/38d05ea68bfc81649a58d9af5ed20cd2) | 완료 |
| 1 | [기업 문제 발견·공개 근거 조사](https://app.notion.com/p/38d05ea68bfc81b69ce8d2d121fbf346) | 완료 |
| 2 | [기술 학습·적합성 검토](https://app.notion.com/p/38d05ea68bfc81238a0cf87bc9b112f0) | 완료 |
| 3 | [플러그인·검증 설계](https://app.notion.com/p/38d05ea68bfc8189bf49c95563ec4863) | 완료 |
| 4 | [MVP 구현](https://app.notion.com/p/38d05ea68bfc81e28c0ec316d0c0326e) | 계획 |
| 5 | [합성 시나리오·자동 검증](https://app.notion.com/p/38d05ea68bfc814db6d0fac60a0dca83) | 계획 |
| 6 | [제출 패키징·포트폴리오 회고](https://app.notion.com/p/38d05ea68bfc8102937ce6cac98b9b59) | 계획 |

## 4. 요청 완료 시 동기화 순서

1. 공식 로그 훅과 감시기가 `logs/` 원본을 수집하게 둡니다.
2. 다음 사용 가능한 W-ID로 `Worklog.md`를 갱신합니다.
3. 중요 결정이 있으면 다음 D-ID로 `Decisionlog.md`를 갱신합니다.
4. 현재 작업이 속한 MyProject Phase를 정합니다.
5. 해당 Phase를 읽어 같은 W-ID가 없는지 확인합니다.
6. 요청·수행·산출물·검증·근거·결과·남은 작업을 Phase 본문에 추가합니다.
7. 중요 결정이면 같은 D-ID가 없는지 조회한 뒤 Phase 하위 결정 페이지를 생성합니다.
8. 새 기술이나 외부 자료를 학습했을 때만 Study DB를 갱신합니다.
9. 메인 페이지의 상태·주요 발견·학습 포인트가 실질적으로 바뀐 경우에만 속성을 갱신합니다.
10. 수정한 Notion 페이지를 다시 읽어 내용과 속성을 검증합니다.

## 5. Phase 선택 기준

- 기록·문서·Notion·개발 환경: Phase 0
- 기업·산업·고객 문제와 공개 근거: Phase 1
- Techlog·백엔드 개념·기술 적합성: Phase 2
- 입력·출력·아키텍처·검증 설계: Phase 3
- 실제 `src/` 코드와 fixture 구현: Phase 4
- 테스트·품질·새 세션 재현: Phase 5
- README·질문지·ZIP·최종 회고: Phase 6

여러 단계에 걸치면 주된 결과가 속하는 Phase 한 곳에 W-ID를 기록하고 관련 페이지를 링크합니다. 같은 W-ID를 여러 Phase에 복제하지 않습니다.

## 6. 기록 형식

### 일반 작업

```markdown
### W-000 · 작업 제목

- 요청:
- 수행 내용:
- 산출물:
- 검증:
- 판단 근거:
- 결과·남은 작업:
```

### 중요 결정

```markdown
## 상황
## 검토한 선택지
## 결정
## 근거
## 영향과 재검토 조건
```

다음에 영향을 주면 개별 결정 페이지를 만듭니다.

- 문제와 기능 범위
- 플러그인 아키텍처·외부 연동
- 보안·개인정보·데이터 처리
- 검증·합격 기준
- 제출 구조와 실격 위험

단순한 구현 세부사항은 Phase 작업 기록에만 둡니다.

## 7. Study DB 기록 기준

새로운 공식 자료나 기술 개념이 프로젝트 판단에 영향을 줄 때만 페이지를 만듭니다.

- 속성: `Topic=조코딩 AX해커톤`
- 프로젝트 개요 문서는 `분류=프로젝트`
- 기술·자료 학습 문서는 `분류=스터디`
- 구조: 핵심 요약 → 개념 → 비판적 검토 → 프로젝트 적용 → 제외 범위 → 학습 포인트

일반 작업마다 학습 페이지를 만들지 않습니다. 페이지 수보다 포트폴리오 설명력과 재사용성을 우선합니다.

## 8. 중복·실패 처리

- 페이지 생성 전 MyProject 제목 또는 Study DB 이름을 정확히 조회합니다.
- 본문 추가 전 W-ID·D-ID가 이미 있는지 확인합니다.
- 같은 ID가 있으면 새 페이지를 만들지 않고 현재 내용과 로컬 기록을 비교합니다.
- Notion 연결이나 권한이 없으면 로컬 기록을 완료하고 Worklog와 최종 보고에 `Notion 동기화 대기`를 명시합니다.
- 다음 연결 시 로컬 W-ID·D-ID와 Notion 기록을 대조해 누락된 항목만 추가합니다.
- 동기화 실패 때문에 프로젝트 코드·테스트 작업을 미완료 상태로 두지 않습니다.

## 9. 보안과 기록 금지 항목

Notion에 다음 내용을 기록하지 않습니다.

- 원본 AI 대화 JSONL 전문
- 모델의 비공개 사고 전개
- 비밀번호, API 키, 토큰과 세션 쿠키
- 실제 고객·계좌·인증정보
- 공개 근거로 확인할 수 없는 내부 사실

`[AX]` 제목과 `Topic=조코딩 AX해커톤` 범위 밖의 기존 Notion 페이지를 수정하지 않습니다.

## 10. 적용 한계

- `AGENTS.md`는 Codex가 프로젝트에서 실행될 때 읽는 지침이며 백그라운드 동기화 프로그램이 아닙니다.
- Codex 세션이 실행되지 않는 동안 Notion이 자동 갱신되지는 않습니다.
- 이 지침은 프로젝트 루트의 `AGENTS.md`를 읽는 Codex 세션에 적용됩니다.
- Claude와 다른 도구에는 별도 프로젝트 지침이 없으면 Notion 동기화가 자동 적용되지 않습니다.
