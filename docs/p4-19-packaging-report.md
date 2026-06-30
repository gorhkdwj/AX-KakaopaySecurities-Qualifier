# P4-19 설치·호출·제출 패키징 검증 보고서

## 1. 결론

P4-19에서는 OpenBell Guard를 제출 가능한 형태로 묶고, 제출 ZIP 안에서 실제 분석 명령이 동작하는지 확인했습니다.

검증 결과는 다음과 같습니다.

- `submission.zip` 생성 완료
- ZIP 내부 최상위 구조: `README.md`, `src/`, `logs/`
- ZIP 내부 파일 수: 18개
- 원본 대화 로그 파일 수: 1개
- 공식 플러그인 manifest 검증: 통과
- 공식 Skill 구조 검증: 통과
- 전체 테스트: 68개 통과
- 제출 ZIP 구조 검증: 통과
- 제출 ZIP 내부 경로에서 대표 fixture 실행: 통과
- 제출 ZIP 내부 실행 결과의 독립 검증: 통과
- 임시 로컬 Codex marketplace 등록: 통과
- `openbell-guard@openbell-guard-local` 설치: 통과
- 새 Codex 비대화 세션의 Skill 인식 확인: 통과

단, 현재 대화 세션 안에서 별도 새 Codex 앱 UI를 사람이 직접 클릭해 플러그인 카드와 신뢰 승인 화면까지 확인하지는 못했습니다. 대신 현재 환경에서 자동화 가능한 공식 구조 검증, 임시 marketplace 설치, 새 Codex 비대화 세션 인식, ZIP 내부 실행 검증으로 재현 가능성을 확인했습니다.

## 2. P4-19의 목적

P4-18까지는 “분석기가 올바르게 작동하는가”를 검증했습니다. P4-19는 한 단계 더 나아가 “심사자가 받은 제출물이 실제로 열리고, 필요한 파일이 있고, 실행 가능한가”를 확인하는 단계입니다.

쉽게 말하면 다음 차이입니다.

- P4-18: 엔진이 잘 도는지 확인합니다.
- P4-19: 엔진, 설명서, 로그, 제출 포장 상태까지 함께 확인합니다.

따라서 P4-19에서는 코드 자체보다 제출물의 재현성, 구조 정합성, 문서 정합성, 로그 포함 여부가 중요합니다.

## 3. 제출 패키지 구성

생성된 제출 패키지는 다음 구조를 따릅니다.

```text
submission.zip
├── README.md
├── src/
│   ├── .codex-plugin/plugin.json
│   ├── skills/openbell-guard/SKILL.md
│   ├── skills/openbell-guard/scripts/
│   ├── skills/openbell-guard/references/
│   └── tests/
└── logs/
```

`src/`는 실제 Codex 플러그인 루트입니다. `logs/`는 해커톤 요구사항에 따라 AI와 주고받은 원본 대화 로그를 포함합니다. 개발 참고 문서인 `docs/`, 로컬 실행 결과인 `out/`, 임시 빌드 폴더인 `submission/` 자체는 ZIP 안에 넣지 않았습니다.

이렇게 분리한 이유는 제출물이 가볍고 재현 가능해야 하기 때문입니다. 실행에 꼭 필요한 플러그인 코드와 원본 로그는 포함하고, 개발 중간 산출물이나 로컬 결과물은 제외했습니다.

## 4. 추가한 자동화 도구

### 4.1 `tools/build_submission.py`

이 스크립트는 제출 폴더와 ZIP을 만듭니다.

수행하는 일은 다음과 같습니다.

- 루트 `README.md`를 `submission/README.md`로 복사합니다.
- `src/` 전체를 `submission/src/`로 복사합니다.
- `logs/` 전체를 `submission/logs/`로 복사합니다.
- Python 캐시, 테스트 캐시, `__pycache__`, `.pyc` 같은 불필요한 파일은 제외합니다.
- 필수 파일과 로그 파일 확장자를 사전 검사합니다.
- 최종 `submission.zip`을 생성합니다.

### 4.2 `tools/validate_submission.py`

이 스크립트는 생성된 `submission.zip`이 과제 요구사항에 맞는지 검사합니다.

검사하는 항목은 다음과 같습니다.

- 최상위 항목이 `README.md`, `src/`, `logs/`인지
- `src/.codex-plugin/plugin.json`이 있는지
- `src/skills/openbell-guard/SKILL.md`가 있는지
- 실행 코드와 지표 계약 복사본이 있는지
- `logs/`에 제출 가능한 형식의 로그 파일이 있는지
- `docs/`, `out/`, `.git/`, `.codex/`, `.vscode/`, 캐시 파일, 키 파일 같은 금지 항목이 들어가지 않았는지
- manifest의 플러그인 이름과 Skill 경로가 실제 구조와 맞는지
- README가 OpenBell Guard와 실제 고객정보 금지 원칙을 설명하는지

## 5. 실행한 검증 명령과 결과

### 5.1 스크립트 문법 검사

```powershell
python -m py_compile tools\build_submission.py tools\validate_submission.py
```

결과: exit code 0

의미: 새로 추가한 제출 빌드·검증 스크립트가 Python 문법 오류 없이 로드됩니다.

### 5.2 사전 점검

```powershell
python .\tools\preflight_check.py --quiet
```

결과:

```text
SUMMARY ok=5 warn=0 error=0
```

의미: 반복적으로 발생했던 프로젝트 구조·환경 문제에 대한 빠른 점검에서 오류가 없었습니다.

### 5.3 공식 플러그인 manifest 검증

```powershell
python <plugin-creator>\scripts\validate_plugin.py .\src
```

결과:

```text
Plugin validation passed
```

의미: `src/.codex-plugin/plugin.json`이 Codex 플러그인 구조 기준을 만족합니다.

### 5.4 공식 Skill 구조 검증

```powershell
python -X utf8 <skill-creator>\scripts\quick_validate.py .\src\skills\openbell-guard
```

결과:

```text
Skill is valid!
```

의미: `src/skills/openbell-guard/SKILL.md`의 Skill frontmatter와 기본 구조가 검증 기준을 통과했습니다.

### 5.5 제출 ZIP 생성

```powershell
python .\tools\build_submission.py
```

결과:

```text
submission_dir: submission
zip_path: submission.zip
zip_file_count: 18
log_file_count: 1
status: built
```

의미: 제출 폴더와 ZIP이 생성됐고, ZIP 안에는 총 18개 파일과 로그 파일 1개가 포함됐습니다. 불필요한 `.gitkeep` 파일과 빈 `assets/` 폴더는 최종 정리 과정에서 제거했습니다.

### 5.6 전체 테스트

```powershell
python -m pytest src\tests
```

결과:

```text
68 passed
```

의미: 입력 검사, 마스킹, 지표 계산, 상태 판정, evidence·claim, 보고서 검증, A~H 통합 시나리오가 모두 통과했습니다.

### 5.7 제출 ZIP 구조 검증

```powershell
python .\tools\validate_submission.py .\submission.zip
```

결과 요약:

```json
{
  "status": "passed",
  "file_count": 18,
  "log_file_count": 1,
  "required_file_count": 6,
  "top_level_entries": [
    "README.md",
    "logs",
    "src"
  ]
}
```

의미: 제출 ZIP의 내부 경로, 필수 파일, 로그 포함 여부, 금지 폴더 제외 여부가 모두 통과했습니다.

### 5.8 제출 ZIP 내부 경로 기준 실행 검증

```powershell
python .\submission\src\skills\openbell-guard\scripts\run_openbell.py `
  --bundle .\submission\src\tests\fixtures\domestic-market-open-min\bundle `
  --output .\out\p4-19-submission-smoke-final
```

결과 요약:

```json
{
  "run_status": "report_validated",
  "analysis_run_status": "complete",
  "output_validation_status": "passed",
  "raw_excerpts_emitted": false,
  "fixture_id": "domestic-market-open-min",
  "accepted_total": 9,
  "bucket_count": 3,
  "claim_count": 5,
  "evidence_count": 5
}
```

의미: 개발 원본 경로가 아니라 제출 폴더 안의 `src/` 경로에서 대표 fixture 분석이 정상 실행됐습니다. 이는 심사자가 ZIP을 풀었을 때도 기본 명령이 재현될 가능성이 높다는 뜻입니다.

### 5.9 제출 ZIP 내부 실행 결과 독립 검증

```powershell
python .\submission\src\skills\openbell-guard\scripts\validate_bundle.py `
  --output .\out\p4-19-submission-smoke-final
```

결과:

```json
{
  "status": "passed",
  "checks": {
    "analysis_schema": "passed",
    "confirmed_fact_evidence": "passed",
    "evidence_references": "passed",
    "report_claim_refs": "passed",
    "secret_residue": "passed"
  },
  "issue_counts": {
    "fatal": 0
  },
  "raw_excerpts_emitted": false
}
```

의미: 제출 경로에서 생성한 결과물도 스키마, 근거 연결, 보고서 claim marker, 민감정보 잔존 검사에서 모두 통과했습니다.

## 6. Codex marketplace 설치 검증

P4-19 이후 보강 검증으로 임시 로컬 marketplace를 만들고 Codex CLI 설치 확인을 수행했습니다.

임시 marketplace는 프로젝트의 Git 무시 대상인 `out/` 아래에 만들었습니다.

```text
out/codex-marketplace-check/
├── .agents/plugins/marketplace.json
└── plugins/openbell-guard/
```

`marketplace.json`은 `openbell-guard-local` marketplace에 `openbell-guard` 플러그인을 `AVAILABLE`, `ON_INSTALL` 정책으로 노출하도록 구성했습니다.

먼저 스테이징 복사본 기준 공식 검증기를 실행했습니다.

```powershell
python <plugin-creator>\scripts\validate_plugin.py .\out\codex-marketplace-check\plugins\openbell-guard
python -X utf8 <skill-creator>\scripts\quick_validate.py .\out\codex-marketplace-check\plugins\openbell-guard\skills\openbell-guard
```

결과:

```text
Plugin validation passed
Skill is valid!
```

이후 marketplace 등록과 플러그인 설치를 확인했습니다.

```powershell
codex plugin marketplace add .\out\codex-marketplace-check --json
codex plugin add openbell-guard@openbell-guard-local --json
codex plugin list
```

설치 결과:

```json
{
  "pluginId": "openbell-guard@openbell-guard-local",
  "name": "openbell-guard",
  "marketplaceName": "openbell-guard-local",
  "version": "0.1.0+codex.20260630084148",
  "authPolicy": "ON_INSTALL"
}
```

`codex plugin list`에서는 `openbell-guard@openbell-guard-local`이 `installed, enabled` 상태로 표시됐습니다.

새 Codex 비대화 세션도 실행했습니다.

```powershell
codex exec --ephemeral -s read-only -C . "OpenBell Guard 플러그인 또는 openbell-guard Skill이 현재 세션에서 사용 가능한지 확인해 주세요..."
```

결과 요약:

```text
AVAILABLE: 현재 세션에서 openbell-guard Skill을 사용할 수 있으며, 합성 사고 번들을 분석해 서비스 지연과 외부 중개사 장애 가설을 검증 가능한 보고서로 정리하는 용도입니다.
```

이 과정에서 최초 설치 후 `interface.defaultPrompt`가 128자 제한을 넘어 Codex가 무시한다는 경고가 발견됐습니다. 최종 제출용 `src/.codex-plugin/plugin.json`에서는 `defaultPrompt`를 3개의 짧은 starter prompt 배열로 수정했습니다.

수정 후 ZIP 내부 manifest에서도 다음을 확인했습니다.

```text
zip_manifest_version=0.1.0
zip_default_prompt_type=list
zip_default_prompt_count=3
zip_default_prompt_lengths=[56, 60, 56]
```

## 7. 새 Codex UI 확인의 한계

현재 환경에서 확인한 Codex CLI에는 다음 명령이 있었습니다.

```powershell
codex plugin --help
```

확인 결과 `add`, `list`, `marketplace`, `remove` 같은 marketplace 기반 플러그인 관리 명령이 제공됩니다. 다만 현재 로컬 폴더를 바로 경로 설치해 새 세션에서 신뢰 승인까지 자동화하는 단순 명령은 확인하지 못했습니다.

따라서 이번 P4-19에서는 다음을 검증 범위로 삼았습니다.

- 공식 플러그인 manifest 검증
- 공식 Skill 구조 검증
- 임시 로컬 marketplace 등록
- 플러그인 설치 상태 확인
- 새 Codex 비대화 세션의 Skill 인식 확인
- 제출 ZIP 내부 구조 검증
- 제출 ZIP 내부 실행 검증
- 제출 ZIP 내부 실행 결과의 독립 검증

새 Codex 앱 UI에서 사용자가 직접 플러그인 카드를 열고 신뢰 승인 화면까지 확인하는 절차는 최종 제출 전 수동 확인 후보로 남깁니다. 이 한계는 기능 결함이라기보다 현재 대화형 환경에서 UI 클릭 기반 확인을 자동화하기 어려운 범위입니다.

## 8. 제출 전 남은 확인 후보

P4-19 자동화 검증은 통과했지만, 최종 제출 직전에는 다음을 한 번 더 확인하는 것이 좋습니다.

- `submission.zip`을 새 임시 폴더에 풀어 README의 실행 명령을 그대로 실행합니다.
- 로그 훅이 최종 대화까지 수집했는지 확인합니다.
- 질문 5문항 답변이 최종 구현 범위를 과장하지 않는지 확인합니다.
- README와 Skill 설명이 “합성 데이터 기반 검증”이라는 한계를 분명히 유지하는지 확인합니다.
- 가능하면 새 Codex 앱 세션에서 플러그인 루트 인식과 Skill 호출을 수동 확인합니다.

## 9. 다음 단계

P4-19의 자동화 패키징 검증은 통과했습니다. 이후 작업은 Phase 5의 합성 시나리오·자동 검증 확장 또는 Phase 6의 최종 제출물 점검·회고로 이어갈 수 있습니다.
