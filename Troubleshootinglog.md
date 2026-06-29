# Troubleshootinglog

이 문서는 OpenBell Guard 구현 과정에서 실제로 발생한 문제와 해결 과정을 누적 기록합니다.

원본 대화 전문은 `logs/`에 보존되므로, 이 파일에는 사람이 검토할 수 있는 증상·원인·조치·결과만 요약합니다. 비공개 사고 과정, 비밀정보, 실제 고객·계좌정보는 기록하지 않습니다.

## 빠른 색인

전체 파일을 매번 읽지 않고, 현재 작업 상황에 맞는 T-ID만 확인합니다.

| 상황 | 확인할 T-ID | 우선 조치 | 자동 점검 |
|---|---:|---|---|
| 공식 플러그인·Skill 검증기 실행 전 | T-001 | `PyYAML` 존재 여부를 먼저 확인하고, 없으면 공식 검증 미완료 범위를 기록합니다. | `python tools/preflight_check.py` |
| 한글 문자열이나 Markdown 문구 자동 검증 전 | T-002 | UTF-8 파일 읽기와 ASCII 식별자 또는 코드포인트 기반 검증을 우선합니다. | `python tools/preflight_check.py` |
| Notion 동기화 전후 | T-003 | fetch 도구 노출 여부와 검색 인덱스 검증 한계를 분리해 기록합니다. | 수동 확인 |
| Git 상태 확인 전 | T-004 | Git 저장소 유효성을 먼저 확인하고, 실패 시 파일 시스템 기준으로 보고합니다. | `python tools/preflight_check.py` |

## 기록 원칙

- 구현, 검증, 문서화, Notion 동기화, 패키징 중 실제로 발생해 작업에 영향을 준 문제만 기록합니다.
- 예상 위험이나 일반 주의사항은 Worklog의 `남은 위험`에 기록하고, 실제 발생 전에는 T-ID를 만들지 않습니다.
- 기존 항목을 삭제하거나 의미가 바뀌게 고치지 않습니다. 추가 확인이나 정정은 같은 T-ID의 후속 메모 또는 새 T-ID로 남깁니다.
- 같은 문제가 재발하면 기존 T-ID를 참조하고, 원인이나 조치가 달라졌을 때만 새 T-ID를 부여합니다.

## 기록 형식

```markdown
### T-000 · 제목

**발생 단계**

- Phase/P4 단계:
- 관련 W-ID:

**증상**

- 무엇이 실패했는지:
- 사용자 작업에 미친 영향:

**확인한 원인**

- 확인된 원인:
- 아직 불확실한 점:

**조치**

- 시도한 조치:
- 최종 처리:

**재발 방지·후속 조치**

- 다음에 적용할 기준:
```

## 항목

### T-001 · 공식 플러그인·Skill 검증기 실행 중 PyYAML 의존성 누락

**발생 단계**

- Phase/P4 단계: Phase 4 / P4-01 플러그인 스캐폴드 검증
- 관련 W-ID: W-034

**증상**

- `plugin-creator`의 `validate_plugin.py`와 `skill-creator`의 `quick_validate.py` 실행이 모두 `ModuleNotFoundError: No module named 'yaml'`로 중단됐습니다.
- 플러그인 구조 자체 검증은 가능했지만 공식 검증 스크립트 기반 검증은 완료하지 못했습니다.

**확인한 원인**

- 현재 로컬 Python 환경에 `PyYAML` 모듈이 설치되어 있지 않았습니다.
- 검증 스크립트가 YAML 파싱에 해당 모듈을 요구합니다.

**조치**

- 이번 단계에서는 새 의존성을 즉시 설치하지 않고, JSON 파싱·필수 경로·Skill frontmatter·미존재 구성요소 미선언을 표준 라이브러리 기반으로 별도 검증했습니다.
- 공식 검증기 미실행 범위를 W-034에 명시했습니다.

**재발 방지·후속 조치**

- P4-02 이후 검증 환경을 고정할 때 `PyYAML` 설치 또는 검증 스크립트 실행용 별도 환경을 결정합니다.
- 공식 검증기 결과가 필요한 단계에서는 의존성 실패를 성공으로 간주하지 않습니다.

**후속 메모**

- 2026-06-30 / W-039: `python -m pip install --user PyYAML`로 PyYAML 6.0.3을 로컬 사용자 환경에 설치했습니다. 이후 `python tools/preflight_check.py --quiet` 결과가 `ok=5`, `warn=0`, `error=0`으로 바뀌어 T-001 경고는 해소됐습니다. PyYAML은 OpenBell Guard 실행 의존성이 아니라 공식 검증기 실행을 위한 로컬 개발·검증 환경 의존성으로 취급합니다.

### T-002 · 한글 문구 검증 중 PowerShell·Python 인코딩 경로 차이 발생

**발생 단계**

- Phase/P4 단계: Phase 4 / P4-01 `SKILL.md` 검증
- 관련 W-ID: W-034

**증상**

- `SKILL.md`에 존재하는 한글 문구를 PowerShell과 inline Python 문자열로 검사할 때 문자열 매칭이 실패했습니다.
- 실제 파일 내용 문제인지 검증 명령 입력 인코딩 문제인지 구분이 필요했습니다.

**확인한 원인**

- 파일은 UTF-8로 정상 저장되어 있었고, Python으로 파일 내용을 출력했을 때 문구가 확인됐습니다.
- 실패는 검증 명령에 직접 들어간 한글 문자열이 PowerShell에서 Python stdin으로 전달되는 과정의 인코딩 차이 때문으로 판단했습니다.

**조치**

- 한글 검증 문자열을 유니코드 코드포인트로 구성해 재검증했습니다.
- 최종 로컬 검증은 통과했습니다.

**재발 방지·후속 조치**

- 한글 고정 문구를 자동 검증할 때는 UTF-8 파일 읽기와 코드포인트 또는 ASCII 중심 식별자를 함께 사용합니다.
- 사용자 보고에는 검증 명령 자체의 인코딩 문제와 파일 내용 문제를 분리해 설명합니다.

**후속 메모**

- 2026-06-30 / W-036: 문서 검증 중 inline Python 코드에 직접 넣은 한글 문자열 검사에서 같은 유형의 매칭 실패가 재발했습니다. 파일 문제는 아니었고, 코드포인트 방식으로 재검증해 통과했습니다. 이후 자동 검증 명령에는 한글 리터럴 직접 삽입을 피합니다.
- 2026-06-30 / W-039: 공식 Skill quick validator가 Windows 기본 인코딩 cp949로 UTF-8 `SKILL.md`를 읽으려다 실패했습니다. `python -X utf8 ...quick_validate.py .\src\skills\openbell-guard`로 실행하자 `Skill is valid!`가 출력됐습니다. 이후 Windows에서 공식 Skill 검증기를 실행할 때는 `-X utf8`을 기본으로 사용합니다.

### T-003 · Notion 업데이트 후 즉시 검색 검증 제한

**발생 단계**

- Phase/P4 단계: Phase 4 / P4-01 Notion 동기화
- 관련 W-ID: W-034

**증상**

- Notion Phase 4 페이지에 W-034 삽입 API는 성공 응답을 반환했지만, 즉시 이어진 Notion 검색에서 새 문구가 하이라이트되지 않았습니다.
- 현재 노출된 Notion 도구에는 페이지 본문 fetch가 없어, 검색 인덱스 기반 검증만 가능했습니다.

**확인한 원인**

- Notion 검색 인덱스 반영이 즉시 이루어지지 않았거나, 도구 노출 범위상 본문을 직접 다시 읽을 수 없는 상태였습니다.
- 업데이트 요청 자체는 정상 응답을 반환했습니다.

**조치**

- W-034에 “업데이트 요청 성공, 재검색 기반 본문 검증 제한”이라고 기록했습니다.
- 같은 내용을 최종 보고에도 제한 사항으로 명시했습니다.

**재발 방지·후속 조치**

- Notion 본문 fetch 도구가 노출되지 않은 세션에서는 업데이트 성공 응답과 검색 검증 가능 여부를 분리해 기록합니다.
- 중요한 결정 페이지 생성처럼 본문 재확인이 필수인 경우 fetch 도구 노출 여부를 먼저 확인합니다.

### T-004 · 작업 폴더의 `.git`이 정상 Git 저장소로 인식되지 않음

**발생 단계**

- Phase/P4 단계: Phase 4 / P4-01 최종 상태 확인
- 관련 W-ID: W-034

**증상**

- `git status --short` 실행 시 `fatal: not a git repository` 오류가 발생했습니다.
- 파일 생성과 로컬 검증은 완료됐지만 Git 기준의 변경 파일 목록 확인은 할 수 없었습니다.

**확인한 원인**

- 작업 루트에 `.git` 디렉터리명은 보이지만, Git이 정상 저장소로 인식하지 못했습니다.
- 현재까지는 저장소 초기화 상태 또는 `.git` 내부 구조 이상 여부를 추가 조사하지 않았습니다.

**조치**

- Git 상태 확인 실패를 최종 보고에 명시했습니다.
- 변경 파일 목록은 파일 시스템 조회와 직접 검증 결과를 기준으로 보고했습니다.

**재발 방지·후속 조치**

- 제출 전 패키징 단계에서는 Git 상태에 의존하지 않고 필수 파일 경로와 ZIP 내부 구조를 별도로 검사합니다.
- 사용자가 Git 관리까지 원하면 `.git` 상태 복구 또는 새 저장소 초기화 여부를 별도 승인 후 진행합니다.

**후속 메모**

- 2026-06-30 / W-037: 사용자가 새 GitHub 저장소를 제공했고 push를 요청했습니다. 기존 빈 `.git` 디렉터리에 `git init -b main`을 실행해 정상 저장소로 초기화하고 원격 `origin`을 연결했습니다. 이후 preflight에서 Git 유효성 경고는 해소되어야 합니다.

### T-005 · 공식 플러그인 검증기가 `author`와 `interface` 필수 누락을 발견

**발생 단계**

- Phase/P4 단계: Phase 4 / PyYAML 설치 후 공식 검증기 재실행
- 관련 W-ID: W-039

**증상**

- PyYAML 설치 후 `validate_plugin.py .\src`가 실행 단계까지 진입했지만, `plugin.json field author must be an object`, `plugin.json field interface must be an object` 오류로 실패했습니다.
- 기존 P4-01 manifest는 실제 존재 구성요소만 선언한다는 최소 원칙에는 맞았지만, 현재 공식 검증기의 필수 표시 메타데이터 기준에는 부족했습니다.

**확인한 원인**

- 공식 검증기 스크립트가 `author` 객체와 `interface` 객체를 필수로 요구합니다.
- 로컬 `docs/guides/plugin-build-guide.md`의 초기 manifest 예시가 이 최신 검증 기준을 충분히 반영하지 못했습니다.

**조치**

- `src/.codex-plugin/plugin.json`에 `author.name`과 `interface` 표시 메타데이터를 추가했습니다.
- 존재하지 않는 MCP·앱·훅은 여전히 선언하지 않았습니다.
- `tools/preflight_check.py`에도 `author`와 `interface` 필수 검사를 추가했습니다.
- `docs/guides/plugin-build-guide.md`의 manifest 예시와 검증 명령을 실제 검증기 기준에 맞게 갱신했습니다.

**재발 방지·후속 조치**

- manifest 변경 후에는 `python C:\Users\gorhk\.codex\skills\.system\plugin-creator\scripts\validate_plugin.py .\src`를 실행합니다.
- Windows에서 Skill 검증은 `python -X utf8 C:\Users\gorhk\.codex\skills\.system\skill-creator\scripts\quick_validate.py .\src\skills\openbell-guard`로 실행합니다.
- `tools/preflight_check.py`가 공식 검증 전 기본 manifest 필수 필드를 사전 점검합니다.
