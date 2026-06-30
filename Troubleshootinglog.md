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
| 최종 출력 JSON 구조 작성 전 | T-013 | 내부 중간 산출물 필드를 그대로 노출하지 말고 최종 원장용 필드로 정규화합니다. | CLI·전체 unittest |
| Skill 문서 한글·줄 단위 패치가 불안정할 때 | T-014 | 줄 단위 패치가 실패하면 파일 내용을 재확인하고, 의미 보존이 가능한 경우 정상 UTF-8 문서로 재작성합니다. | `quick_validate.py` |

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

### T-006 · 단계명 상승 후 테스트 기대값 갱신 누락

**발생 단계**

- Phase/P4 단계: Phase 4 / P4-06 민감정보 탐지·마스킹
- 관련 W-ID: W-043

**증상**

- P4-06 구현 후 `python -m unittest .\src\tests\test_run_openbell_cli.py -v` 실행에서 1개 테스트가 실패했습니다.
- 실패 테스트는 `test_success_creates_output_summary_without_analysis_outputs`였고, 실제 출력의 `stage`는 `P4-06`인데 테스트 기대값은 이전 단계인 `P4-05`로 남아 있었습니다.

**확인한 원인**

- `run_openbell.py`의 단계와 상태를 P4-06 기준으로 올렸지만, P4-05에서 작성된 성공 smoke 테스트 기대값을 함께 갱신하지 않았습니다.
- 기능 오류라기보다 단계 상태 필드 변경에 따른 테스트 정합성 누락이었습니다.

**조치**

- 성공 smoke 테스트의 기대값을 `stage=P4-06`, `run_status=sanitized_preflight_ready`, `sanitization_report_created=true`로 갱신했습니다.
- `sanitized-bundle/logs.jsonl`과 `sanitization-report.md` 생성 확인도 추가했습니다.
- 수정 후 P4-06 CLI 테스트 15개와 전체 unittest 27개가 모두 통과했습니다.

**재발 방지·후속 조치**

- 단계가 P4-07, P4-08처럼 올라갈 때는 구현 상수뿐 아니라 성공 smoke 테스트의 `stage`, `run_status`, 생성 산출물 기대값을 함께 확인합니다.
- 단계별 상태 변경은 기능 추가와 별도로 회귀 테스트 기대값 갱신 항목으로 Worklog에 적습니다.

### T-007 · Notion update_content에서 `<page>` 태그를 신규 참조로 삽입하려다 실패

**발생 단계**

- Phase/P4 단계: Phase 4 / P4-06 Notion 동기화
- 관련 W-ID: W-043

**증상**

- Phase 4 페이지에 W-043 요약과 D-026 링크를 추가할 때 `<page url="...">...</page>` 태그를 직접 넣은 `insert_content` 요청이 실패했습니다.
- Notion 도구는 기존 페이지를 새로 만들거나 참조하기 위해 `<page>` 태그를 쓰지 말고, inline reference는 `<mention-page>` 또는 일반 링크를 쓰라고 반환했습니다.

**확인한 원인**

- Notion fetch 결과에는 기존 child page가 `<page>` 태그로 보이지만, update 요청에서 이 태그를 새로 삽입하는 것은 허용되지 않습니다.
- fetch 표현 형식과 update 입력 형식을 혼동했습니다.

**조치**

- W-043 본문에서 D-026 참조를 일반 Markdown 링크로 바꿔 다시 `insert_content`를 실행했습니다.
- 재시도는 성공했고, fetch로 Phase 4 본문과 D-026 페이지 생성을 확인했습니다.

**재발 방지·후속 조치**

- Notion 페이지 본문에 기존 페이지를 새로 참조할 때는 일반 Markdown 링크 또는 `<mention-page>`를 사용합니다.
- fetch 결과에 보이는 `<page>` 태그는 “기존 child page 표현”으로만 해석하고, update 입력에 그대로 복사하지 않습니다.

### T-008 · 임시 민감정보 잔존 스캔 명령의 PowerShell·정규식 인용 오류

**발생 단계**

- Phase/P4 단계: Phase 4 / P4-06 민감정보 탐지·마스킹 최종 검증
- 관련 W-ID: W-043

**증상**

- `out/p4-06-smoke` 산출물에 민감정보가 남지 않았는지 추가 확인하려고 PowerShell에서 여러 정규식을 직접 조합한 `rg` 명령을 실행했으나, PowerShell 파서 오류가 발생했습니다.
- 이어서 임시 Python here-string으로 같은 정규식을 다시 작성했지만, 수동 전사한 패턴 일부가 잘못되어 `re.error: nothing to repeat` 컴파일 오류가 발생했습니다.

**확인한 원인**

- 구현 코드에 이미 존재하는 민감정보 탐지 함수를 재사용하지 않고, 복잡한 정규식을 셸 명령에 다시 입력하면서 PowerShell 인용 규칙과 정규식 문법이 섞였습니다.
- 제품 코드의 마스킹 로직 오류가 아니라, 검증용 임시 명령 작성 방식의 오류였습니다.

**조치**

- 임시 정규식을 폐기하고 `run_openbell.py`의 `find_sensitive_matches` 함수를 직접 import해 `out/p4-06-smoke` 전체 파일을 재검사했습니다.
- 재검사 결과 `no_sensitive_residue`가 출력되어 마스킹 산출물에 민감정보 패턴 잔존이 없음을 확인했습니다.

**재발 방지·후속 조치**

- 보안 정규식처럼 복잡하고 제품 코드와 일치해야 하는 검증은 셸에서 패턴을 다시 작성하지 않고, 구현 함수 또는 공용 helper를 재사용합니다.
- PowerShell에서 긴 정규식 묶음을 직접 조합해야 하는 상황은 피하고, 필요한 경우 짧은 Python 검증 스크립트로 분리해 먼저 컴파일 가능성을 확인합니다.

### T-009 · 구간 밖 로그 fixture의 `observed_time` 정합성 누락

**발생 단계**

- Phase/P4 단계: Phase 4 / P4-07 행 단위 파서
- 관련 W-ID: W-044

**증상**

- P4-07 구현 후 `python -m unittest .\src\tests\test_run_openbell_cli.py -v` 실행에서 `test_logs_parser_reports_m014_counts_and_row_level_issues`가 실패했습니다.
- 테스트는 `field_dropped_count=1`을 기대했지만 실제 결과는 `field_dropped_count=2`였습니다.

**확인한 원인**

- 구간 밖 행을 만들기 위해 `event_time`만 `2026-06-30T09:03:00+09:00`로 바꿨고, 기본 `observed_time`은 `2026-06-30T09:00:06+09:00`로 남겨 두었습니다.
- 계약상 `observed_time >= event_time`이어야 하므로, 해당 구간 밖 행이 의도와 달리 선택 필드 오류도 함께 발생시켰습니다.
- 제품 코드 오류가 아니라 테스트 fixture의 시간 필드 정합성 누락이었습니다.

**조치**

- 구간 밖 행의 `observed_time`을 `2026-06-30T09:03:01+09:00`로 함께 조정했습니다.
- 같은 구간 밖 행을 사용하는 `INP008_NO_VALID_RECORD` 테스트도 같은 방식으로 수정했습니다.
- 수정 후 P4-07 CLI 테스트 19개와 전체 unittest 31개가 모두 통과했습니다.

**재발 방지·후속 조치**

- 시간 관련 테스트 fixture에서 `event_time`을 바꿀 때는 `observed_time`과 분석 구간 포함 여부를 함께 확인합니다.
- 행 단위 파서 테스트는 하나의 행에 여러 오류가 섞이지 않도록, 의도한 issue code 외의 선택 필드 오류가 발생하지 않는지 기대 카운트로 검증합니다.
### T-010 · PowerShell 인라인 Python 명령에서 한글 경로가 깨져 민감정보 잔존 검사 1차 실패

**발생 단계**

- Phase/P4 단계: Phase 4 / P4-09 기본 지표 계산 검증
- 관련 W-ID: W-046

**증상**

- `out/p4-09-smoke` 산출물에 민감정보 패턴이 남지 않았는지 확인하기 위해 PowerShell here-string으로 Python 검증 명령을 실행했습니다.
- 명령 안에 한글 절대 경로를 직접 넣었고, Python 실행 시 해당 경로가 `AX???\??? AX???\???????`처럼 깨져 `OSError: [Errno 22] Invalid argument`가 발생했습니다.
- 제품 코드나 산출물 오류는 아니며, 검증 보조 명령 작성 방식의 문제였습니다.

**확인된 원인**

- PowerShell here-string을 파이프로 Python 표준 입력에 전달하는 과정에서 한글 절대 경로 문자열이 안전하게 보존되지 않았습니다.
- 이전 T-008과 유사하게, 긴 임시 검증 명령에서 셸 인용·인코딩·경로 처리를 직접 조합할 때 오류가 발생할 수 있음을 다시 확인했습니다.

**조치**

- 한글 절대 경로를 코드에 직접 쓰지 않고 `Path.cwd()`와 상대 경로 조합으로 검증 스크립트를 다시 실행했습니다.
- 재실행 결과 `no_sensitive_residue`가 출력되어 `out/p4-09-smoke` 산출물에 민감정보 패턴 잔존이 없음을 확인했습니다.

**재발 방지·후속 조치**

- 한글 경로가 포함된 프로젝트에서는 임시 Python 검증 명령 안에 절대 경로 문자열을 직접 넣지 않고, 작업 디렉터리 기준 `Path.cwd()` 또는 상대 경로를 우선 사용합니다.
- 보안 잔존 검사처럼 반복되는 검증은 가능하면 제품 코드의 helper를 import하되, 경로는 현재 작업 디렉터리 기준으로 구성합니다.
- PowerShell 인라인 명령이 실패하면 제품 코드 실패로 단정하지 않고, 먼저 인코딩·인용·경로 조합 문제를 분리해 확인합니다.

### T-011 · 민감정보 잔존 검사 helper 입력 형태 오해

**발생 단계**

- Phase/P4 단계: Phase 4 / P4-10 관측 지연·기준 비교 검증
- 관련 W-ID: W-048

**증상**

- `out/p4-10-smoke` 산출물에 민감정보 패턴이 남지 않았는지 확인하려고 `run_openbell.py`의 `find_sensitive_matches`를 import해 실행했습니다.
- 1차 검증 명령에서 `{파일명: 문자열}` 형태의 dict 전체를 `find_sensitive_matches`에 넘겨 `TypeError: expected string or bytes-like object, got 'dict'`가 발생했습니다.

**확인된 원인**

- `find_sensitive_matches`는 단일 문자열과 `source_file` 이름을 받는 helper입니다.
- P4-06 이후 검증 습관대로 여러 파일을 한꺼번에 묶어 넘기려다가 함수의 실제 시그니처를 확인하지 않고 잘못 호출했습니다.
- 제품 코드나 산출물 오류가 아니라 검증 보조 명령 작성 오류입니다.

**조치**

- `find_sensitive_matches` 정의를 확인한 뒤 산출물 파일을 하나씩 읽어 문자열 단위로 검사하도록 명령을 수정했습니다.
- 재실행 결과 `no_sensitive_residue`가 출력되어 `out/p4-10-smoke` 산출물에 민감정보 패턴 잔존이 없음을 확인했습니다.

**재발 방지·후속 조치**

- 제품 코드 helper를 검증 명령에서 재사용할 때는 먼저 함수 시그니처와 반환 형태를 확인합니다.
- 여러 파일을 검사할 때도 helper가 단일 문자열을 받는다면 파일별 반복 호출로 감싸고, wrapper 입력 형태를 임의로 추정하지 않습니다.

### T-012 · Notion 본문 삽입에서 `<page>` 태그를 기존 페이지 참조로 오사용

**발생 단계**

- Phase/P4 단계: Phase 4 / P4-10 Notion 동기화
- 관련 W-ID: W-048

**증상**

- D-027 하위 페이지 생성 후 Phase 4 페이지에 W-048 요약과 결정 링크를 추가하는 과정에서 `<page url="...">...</page>` 태그를 본문에 삽입했습니다.
- Notion API가 `Cannot add a page by using the corresponding tag with a URL` 오류를 반환했습니다.

**확인된 원인**

- 기존 T-007에서 확인했던 것처럼 `<page>` 태그는 본문에서 기존 페이지를 새로 참조하는 용도로 직접 쓰면 안 됩니다.
- 기존 페이지를 인라인으로 가리킬 때는 일반 Markdown 링크나 `<mention-page>` 형식을 사용해야 합니다.
- 제품 코드 오류가 아니라 Notion 동기화 보조 입력 형식 오류입니다.

**조치**

- `<page>` 태그를 제거하고 일반 Markdown 링크 `[D-027](https://app.notion.com/p/38e05ea68bfc816b8e32e42579d6155c)`로 바꾸어 W-048 요약을 다시 삽입했습니다.
- 재시도 결과 Phase 4 페이지 업데이트가 성공했습니다.

**재발 방지·후속 조치**

- Notion 본문에 기존 페이지 링크를 넣을 때는 기본적으로 일반 Markdown 링크를 사용합니다.
- `<page>` 태그는 fetch 결과에 이미 존재하는 하위 페이지를 보존하거나 이동할 때만 신중하게 다룹니다.
- Notion 업데이트 전에 T-007과 T-012를 함께 확인합니다.

**후속 메모**

- 2026-06-30 W-051 Notion 동기화 중 D-030 페이지를 Phase 4 본문에 `<page url="...">` 태그로 참조하려 하면서 같은 validation error가 재발했습니다.
- 즉시 일반 Markdown 링크 `[D-030](https://app.notion.com/p/38e05ea68bfc8129ac50d0beeeb27ee0)` 방식으로 재시도해 W-051 삽입을 성공시켰습니다.
- 이후 Notion 본문 삽입 시 기존 페이지는 `<page>` 태그 대신 일반 링크를 기본값으로 사용해야 합니다.

### T-013 · analysis.json에 내부용 breach_reasons 필드가 그대로 섞인 문제

**발생 단계**

- Phase/P4 단계: Phase 4 / P4-14 analysis/sanitization 출력
- 관련 W-ID: W-052

**증상**

- 새로 추가한 `test_fixture_analysis_json_preserves_golden_core_and_claim_refs`가 실패했습니다.
- 실패 지점은 `analysis.json.bucket_metrics[].breach_reasons` 비교였습니다.
- 값 자체의 장애 판정은 맞았지만, 최종 `analysis.json`에 내부 상태 판정용 `threshold_key`가 포함되고 `threshold` 표현이 Golden 핵심 구조와 달랐습니다.

**확인한 원인**

- `analysis.json`을 만들 때 `state-summary.json`의 `breach_reasons`를 그대로 복사했습니다.
- `state-summary.json`은 내부 판정 추적을 위해 `threshold_key`를 보존하지만, 최종 기계 검증용 원장은 Golden 기준의 `metric`, `value`, `threshold`, `operator`만 필요합니다.
- 제품 기능의 계산 오류가 아니라 중간 산출물과 최종 산출물의 표현 계층을 분리하지 않은 출력 정규화 오류였습니다.

**조치**

- `analysis_bucket_metrics()`에서 `breach_reasons`를 최종 원장용 필드로 재구성했습니다.
- 최종 `analysis.json`에는 `metric`, `value`, `threshold`, `operator`만 남기고, `threshold`는 `float`로 정규화했습니다.
- 수정 후 CLI 테스트 34개와 전체 테스트 46개가 모두 통과했습니다.

**재발 방지·후속 조치**

- P4-15 출력 검증기에서는 중간 산출물 전용 필드와 최종 산출물 필드가 섞이지 않는지 검사해야 합니다.
- `analysis.json`을 만들 때는 중간 JSON을 단순 병합하지 말고, 보고·검증에 필요한 최종 계약 필드만 명시적으로 투영합니다.
- Golden 핵심 구조와 다를 때는 테스트를 완화하기보다 최종 산출물의 목적에 맞는 정규화 여부를 먼저 확인합니다.

### T-014 · SKILL.md 한글 문서의 줄 단위 패치가 실패한 문제

**발생 단계**

- Phase/P4 단계: Phase 4 / P4-15 출력 검증기
- 관련 W-ID: W-053

**증상**

- `SKILL.md`를 P4-15 기준으로 갱신하려고 기존 문구를 기준으로 줄 단위 `apply_patch`를 시도했지만, 예상 문구를 찾지 못해 패치가 실패했습니다.
- PowerShell `Get-Content` 출력에서는 한글이 깨진 것처럼 보여, 실제 파일이 손상됐는지 단순 터미널 표시 문제인지 구분이 필요했습니다.

**확인한 원인**

- `rg`로 같은 파일을 읽었을 때는 정상 UTF-8 한국어 문구가 확인됐습니다.
- 문제는 제품 코드가 아니라, 터미널 출력 인코딩과 줄 단위 패치 기준 문구를 혼동한 작업 절차 문제였습니다.
- 기존 문서 일부를 그대로 맞춰 패치하기보다 현재 구현 상태에 맞춘 정상 UTF-8 문서로 재작성하는 편이 더 안전했습니다.

**조치**

- `SKILL.md` 전체를 정상 UTF-8 한국어 문서로 재작성했습니다.
- 재작성 후 `python -X utf8 ...quick_validate.py .\src\skills\openbell-guard`로 Skill 유효성을 확인했습니다.
- 전체 CLI 테스트, 전체 unittest, 공식 플러그인 검증기도 다시 통과시켰습니다.

**재발 방지·후속 조치**

- 한글 문서가 깨져 보일 때는 PowerShell 출력만 믿지 말고 `rg` 또는 UTF-8 명시 읽기로 실제 파일 내용을 확인합니다.
- 줄 단위 패치가 반복 실패하고 문서 의미를 보존할 수 있다면, 작은 조각을 억지로 맞추기보다 정상 UTF-8 전체 문서로 재작성합니다.
- 문서 재작성 후에는 반드시 Skill 검증기와 관련 테스트를 다시 실행합니다.

### T-015 · 보고서 claim 문장에 소수 셋째 자리 표시가 남은 문제

**발생 단계**

- Phase/P4 단계: Phase 4 / P4-16 Skill 보고서 워크플로
- 관련 W-ID: W-054

**증상**

- `openbell-report.md` smoke 내용을 확인하는 과정에서 60초 버킷 요약은 `66.67%`로 표시됐지만, 확인된 사실 claim 문장에는 `error_rate_pct=66.667`과 `50.0`처럼 `analysis.json`의 원시 statement 값이 그대로 남아 있었습니다.
- 기능상 claim marker와 근거 연결은 맞았지만, `openbell-report.md` 표시값은 소수점 둘째 자리까지 `ROUND_HALF_UP`으로 반올림한다는 계약과 완전히 맞지 않았습니다.

**확인한 원인**

- 버킷 요약은 `report_display_value()`를 통해 표시값을 반올림했지만, claim 문장은 `analysis.json.claims[].statement` 문자열을 그대로 사용했습니다.
- 이 때문에 같은 보고서 안에서 요약 숫자와 claim 숫자의 표시 정밀도가 달라졌습니다.
- 판정 로직 오류가 아니라, 보고서 표시 계층에서 숫자 문자열을 별도로 정규화하지 않은 문제였습니다.

**조치**

- `report_display_statement()`를 추가해 claim statement 안의 소수값을 소수점 둘째 자리까지 `ROUND_HALF_UP`으로 반올림했습니다.
- `=null` 표시는 사람이 읽기 쉬운 `=판단 불가`로 바꾸도록 했습니다.
- `test_openbell_report_contains_claim_sections_and_markers`에 `66.67` 포함과 `66.667` 미포함 검증을 추가했습니다.
- 전체 CLI 테스트 44개, 전체 unittest 56개, smoke와 독립 검증기를 다시 실행해 모두 통과를 확인했습니다.

**재발 방지·후속 조치**

- 보고서에 숫자를 표시할 때는 `analysis.json`의 판정값을 바꾸지 않되, 사람용 표시 계층에서는 반올림 기준을 반드시 적용합니다.
- 앞으로 보고서 섹션을 추가할 때 raw statement를 그대로 출력하지 말고 표시 변환 함수를 통과시키는지 확인합니다.
- 같은 smoke 출력 폴더를 재사용하면 이전 산출물이 검증 대상에 포함될 수 있으므로, 기록용 smoke는 새 폴더를 사용합니다.

### T-016 · Git push 명령의 작업 디렉터리 문자열 오타

**발생 단계**

- Phase/P4 단계: Phase 4 / P4-16 Skill 보고서 워크플로 후 Git 동기화
- 관련 W-ID: W-054

**증상**

- `git push origin main` 실행 시 workdir에 프로젝트 폴더명 끝 글자를 잘못 입력해 Windows가 `디렉터리 이름이 올바르지 않습니다.`를 반환했습니다.
- Git 커밋과 파일 내용에는 영향이 없었고, push 명령이 실행되기 전에 작업 디렉터리 해석 단계에서 실패했습니다.

**확인한 원인**

- 정상 경로는 `카카오페이증권`인데, 도구 호출의 workdir 문자열에 다른 한자가 섞였습니다.
- 제품 코드나 Git 원격 문제가 아니라 명령 실행 경로 입력 오류였습니다.

**조치**

- 같은 명령을 올바른 프로젝트 경로에서 즉시 재실행했습니다.
- `git push origin main`이 성공해 커밋 `d18a75a`가 원격 `origin/main`에 반영됐습니다.

**재발 방지·후속 조치**

- Git, 테스트, 파일 검사처럼 프로젝트 루트가 중요한 명령은 이미 확인된 현재 작업 디렉터리 문자열을 재사용합니다.
- 한글 경로를 직접 다시 타이핑하지 않고, 가능하면 기존 shell 호출의 정상 workdir 값을 복사해 사용합니다.
- 경로 오류가 나면 파일이나 원격 상태가 바뀌었는지 단정하지 말고, 동일 명령을 올바른 경로에서 재실행한 뒤 결과를 기록합니다.

### T-017 · H 시나리오 파일 한도 issue code 기대값을 잘못 쓴 문제

**발생 단계**

- Phase/P4 단계: Phase 4 / P4-17 통합 시나리오 검증
- 관련 W-ID: W-055

**증상**

- 새로 추가한 `test_h_damaged_rows_degrade_and_limit_excess_exits_4_before_analysis`가 1회 실패했습니다.
- 파일 크기 초과 입력이 의도대로 `exit 4`로 중단됐지만, 테스트는 stderr에 `LIM001_FILE_TOO_LARGE`가 있기를 기대했습니다.
- 실제 stderr의 issue code는 `LIM001_FILE_BYTES`였습니다.

**확인한 원인**

- 제품 코드 동작은 정상이고, 테스트 작성 과정에서 계약·구현에 존재하지 않는 이름을 기대값으로 적었습니다.
- P4-17은 issue code까지 회귀 검증하는 단계이므로, 사람이 읽기 쉬운 임의 이름이 아니라 실제 계약 코드명을 사용해야 합니다.
- 같은 수정 과정에서 한글 절대경로를 사용한 `apply_patch`가 실패해, T-016의 재발 방지 규칙대로 상대경로 patch로 전환했습니다.

**조치**

- H 시나리오 기대값을 `LIM001_FILE_BYTES`로 수정했습니다.
- P4-17 통합 시나리오 테스트 9개를 재실행해 모두 통과함을 확인했습니다.
- 기존 CLI 테스트 44개, 전체 unittest 65개, preflight, 플러그인 검증기와 Skill 검증기도 다시 통과시켰습니다.

**재발 방지·후속 조치**

- issue code를 새로 기대할 때는 기억이나 자연어 이름으로 쓰지 말고 `run_openbell.py`, 지표 계약, 기존 테스트 중 하나에서 실제 문자열을 확인합니다.
- 경계·한도 시나리오의 기대값은 exit code와 issue code를 함께 검증합니다.
- 한글 경로가 포함된 patch는 가능한 한 프로젝트 루트 기준 상대경로를 사용합니다.

### T-018 · 지원 한도 benchmark 첫 시도가 도구 시간 제한 전에 summary를 쓰지 못한 문제

**발생 단계**

- Phase/P4 단계: Phase 4 / P4-18 성능·회귀 benchmark
- 관련 W-ID: W-056

**증상**

- `python .\src\skills\openbell-guard\scripts\benchmark_openbell.py --output .\out\p4-18-benchmark` 첫 실행이 180초 도구 호출 제한을 넘겨 종료됐습니다.
- 종료 시점에는 `benchmark-summary.json`이 아직 생성되지 않았습니다.
- 부분 산출물을 확인하니 warm-up과 여러 측정 run 출력은 생성됐지만 마지막 summary 작성까지 도달하지 못했습니다.
- 대규모 run 출력에서 `bucket-summary.json`, `metric-summary.json`, `state-summary.json`, `analysis.json`이 수 MB까지 커졌습니다.

**확인한 원인**

- 첫 직접 원인은 benchmark 전체가 1회 warm-up과 5회 측정 run을 한 번에 수행해 단일 도구 호출 시간이 길어진 것입니다.
- 더 중요한 병목은 aggregate 산출물의 `source_locations`가 모든 행 번호를 그대로 JSON 배열에 저장한 점이었습니다.
- 지원 한도 입력에서는 10개 버킷이어도 각 버킷이 수천~수만 개 행 위치를 들고 있어 산출물 작성과 output validation 비용이 커졌습니다.
- M-016 단일 run 기준 자체가 60초를 넘었다는 증거는 아니었습니다. 각 run 생성 시각을 보면 개별 run은 대략 37~40초 범위였습니다.

**조치**

- `compact_source_location_list()`를 추가해 산출물의 `source_locations`를 파일별 행 범위 요약으로 압축했습니다.
- `build_bucket_summary`, context metrics, bucket metrics, metric issue 위치 출력에 압축을 적용했습니다.
- benchmark CLI의 상대 출력 경로는 OS별 구분자 차이를 줄이기 위해 `runs/run-001` 같은 POSIX 형식으로 기록하도록 조정했습니다.
- 기본 benchmark를 다시 실행해 M-016 중앙값 34.523738초, M-017 최고값 194.280592MiB로 통과함을 확인했습니다.
- `docs/p4-18-benchmark-report.md`에 첫 시도 timeout, 출력 경량화 조치와 최종 측정 결과를 기록했습니다.

**재발 방지·후속 조치**

- aggregate 산출물에는 대규모 raw 위치 목록을 그대로 저장하지 말고 요약 범위, count, evidence ID를 우선 사용합니다.
- benchmark나 회귀 검증처럼 전체 실행시간이 긴 작업은 단일 run 기준과 전체 호출 기준을 구분해 해석합니다.
- M-016은 개별 deterministic pipeline run의 중앙값이고, 전체 benchmark 명령 wall time이 아님을 보고서와 최종 설명에서 구분합니다.
- 대규모 입력으로 새 산출물을 추가할 때는 결과 파일 크기도 검증 항목에 포함합니다.
- `tracemalloc` 결과는 Python 추적 메모리일 뿐 전체 프로세스 메모리가 아니므로 과장하지 않습니다.

### T-019 · 전체 pytest 회귀 테스트 실행 시 `pytest` 미설치로 실패한 문제

**발생 단계**

- Phase/P4 단계: Phase 4 / 수동 테스트·휴먼 리뷰 산출물 구축
- 관련 W-ID: W-061

**증상**

- `python -m pytest src\tests` 실행 시 다음 오류가 발생했습니다.
- `C:\Users\gorhk\MiniConda3\python.exe: No module named pytest`

**확인한 원인**

- 현재 Python 환경에는 `pytest`가 설치되어 있지 않습니다.
- 이번 수동 테스트 케이스의 `run_openbell.py`, `validate_bundle.py`, `tools/preflight_check.py` 실행은 정상 통과했습니다.
- 따라서 이번 실패는 제품 코드의 회귀 실패가 아니라 전체 테스트 러너 의존성 부재입니다.

**초기 조치**

- 이번 작업 범위에서는 추가 패키지를 임의 설치하지 않고, 실행 가능한 검증을 모두 수행했습니다.
- CLI 실행 결과, 출력 validator, 민감정보 잔존 검색, preflight 검사를 통해 이번 변경 범위를 검증했습니다.
- pytest 미설치 사실을 W-061과 본 T-019에 기록했습니다.

**추가 조치**

- 사용자가 `pytest` 설치를 명시적으로 요청해 `python -m pip install pytest`를 실행했습니다.
- `pytest==9.1.1`, `pluggy==1.6.0`, `iniconfig==2.3.0` 설치를 확인했습니다.
- 같은 환경에서 `python -m pytest src\tests`를 재실행해 68개 테스트가 모두 통과했습니다.
- 다음 환경 재현을 위해 루트 `requirements-dev.txt`에 `pytest==9.1.1`을 기록했습니다.

**재발 방지·후속 조치**

- 전체 회귀 테스트가 필요할 때는 먼저 `python -m pytest --version` 또는 `python -c "import pytest"`로 의존성 존재를 확인합니다.
- 새 환경에서는 `python -m pip install -r requirements-dev.txt`로 검증 의존성을 먼저 설치합니다.
- 제출용 런타임 의존성과 개발 검증 의존성은 분리해 설명합니다.

### T-020 · docs/README.md 새 목록 줄의 Markdown 줄바꿈 공백이 `git diff --check`에 걸린 문제

**발생 단계**

- Phase/P4 단계: Phase 4 / 수동 테스트·휴먼 리뷰 산출물 구축
- 관련 W-ID: W-061

**증상**

- 커밋 전 `git diff --check` 실행 시 `docs/README.md`의 새 목록 줄 여러 곳에서 `trailing whitespace` 경고가 발생했고 exit code 1로 종료됐습니다.

**확인한 원인**

- 기존 문서의 목록 작성 스타일을 따라 링크 줄 끝에 Markdown 줄바꿈용 공백 두 칸을 넣었습니다.
- Git 검사는 변경된 새 줄의 끝 공백을 품질 이슈로 판단했습니다.
- 문맥상 해당 공백이 없어도 다음 줄 설명은 목록 항목의 설명으로 읽을 수 있어 기능적 필요성이 낮았습니다.

**조치**

- 새로 추가·수정된 `docs/README.md` 목록 줄의 trailing whitespace를 제거했습니다.
- 이후 `git diff --check`를 다시 실행해 통과 여부를 확인합니다.

**재발 방지·후속 조치**

- 새 Markdown 목록을 추가할 때 줄 끝 공백 두 칸에 의존하지 말고, 가능한 일반 줄바꿈과 들여쓰기로 설명을 연결합니다.
- 커밋 전 `git diff --check`를 실행해 공백·충돌 marker 문제를 확인합니다.

### T-021 · case-002 service-map dependency가 같은 파일 안의 서비스만 참조해야 하는 계약을 위반한 문제

**발생 단계**

- Phase/P4 단계: Phase 4 / case-002 대규모 현실형 합성 데이터 검증
- 관련 W-ID: W-065

**증상**

- `case-002-large-scenario` 첫 분석 실행에서 `run_openbell.py`가 exit code 2로 중단됐습니다.
- 오류는 `INP009_SERVICE_MAP`이며, 메시지는 `service-map.json dependencies must reference services in the same file.`였습니다.

**확인한 원인**

- 생성기에서 외부 시세 피드처럼 보이는 신호를 만들기 위해 `quote-provider-adapter`의 dependency에 `synthetic-exchange-feed`를 넣었습니다.
- 현재 OpenBell Guard 입력 계약은 `service-map.json`의 `dependencies`가 같은 파일에 정의된 서비스명만 참조하도록 요구합니다.
- 따라서 외부 의존성 자체를 service-map dependency로 표현하는 방식은 현재 계약과 맞지 않았습니다.

**조치**

- `tools/generate_large_scenario.py`에서 `synthetic-exchange-feed` dependency를 제거했습니다.
- 외부 의존성 성격은 `dependency_type=exchange`와 로그 메시지 패턴으로 표현하도록 유지했습니다.
- bundle을 다시 생성한 뒤 분석 실행과 validator를 재실행해 통과를 확인했습니다.

**재발 방지·후속 조치**

- 합성 service-map을 만들 때 dependencies는 반드시 같은 파일 안의 service_name만 참조합니다.
- 외부 의존성 신호는 현재 계약에서는 `dependency_type`과 telemetry message, evidence 요약으로 표현합니다.
- 향후 실제 외부 시스템명을 별도 노드로 표현하려면 service-map 계약 변경부터 검토해야 합니다.

### T-022 · PowerShell에서 Bash heredoc 문법으로 ground truth 대조 스크립트를 실행한 문제

**발생 단계**

- Phase/P4 단계: Phase 4 / case-002 대규모 현실형 합성 데이터 검증
- 관련 W-ID: W-065

**증상**

- ground truth 대조용 임시 Python 스크립트를 `python - <<'PY'` 형태로 실행했다가 PowerShell parser 오류가 발생했습니다.
- 오류는 `Missing file specification after redirection operator`와 `The '<' operator is reserved for future use.`였습니다.

**확인한 원인**

- `python - <<'PY'`는 Bash 계열 heredoc 문법입니다.
- 현재 작업 셸은 PowerShell이므로 here-string `@' ... '@ | python -` 형태를 사용해야 합니다.

**조치**

- 같은 Python 코드를 PowerShell here-string 방식으로 재실행했습니다.
- ground truth 대조 결과 3개 서비스 경로의 기대 상태, 장애 시작, 회복 시각이 모두 실제 결과와 일치했습니다.

**재발 방지·후속 조치**

- Windows PowerShell에서 inline Python을 실행할 때는 `@' ... '@ | python -`를 사용합니다.
- Bash heredoc 문법은 이 프로젝트의 기본 셸 명령 예시로 사용하지 않습니다.

### T-023 · PowerShell here-string 안의 한글 검사 문자열이 임시 Python 스크립트에서 깨진 문제

**발생 단계**

- Phase/P4 단계: Phase 4 / 수동 테스트 문서 해석 가이드 보강
- 관련 W-ID: W-069

**증상**

- `docs/manual-test-reports/` 문서 보강 후 섹션 존재 여부를 Python 임시 스크립트로 검사했습니다.
- 파일 자체에는 한글 섹션 제목이 정상적으로 존재했지만, 검사 스크립트 안의 한글 문자열이 `??` 형태로 깨져 `MISSING` 오류가 발생했습니다.

**확인한 원인**

- PowerShell here-string으로 전달한 임시 Python 코드 안의 한글 리터럴이 실행 과정에서 콘솔 인코딩 영향을 받았습니다.
- 이는 문서 파일의 UTF-8 내용 문제가 아니라, 임시 검사 명령 작성 방식의 문제였습니다.

**조치**

- 같은 섹션 존재 검사를 PowerShell `Select-String -LiteralPath ... -Pattern ...` 방식으로 재실행했습니다.
- `README.md`, case-001, case-002, `human-review-template.md`의 새 핵심 섹션이 모두 존재함을 확인했습니다.

**재발 방지·후속 조치**

- Windows PowerShell에서 한글 섹션명 존재 여부를 검사할 때는 간단한 경우 `Select-String`을 우선 사용합니다.
- Python 임시 스크립트에 한글 리터럴을 넣어야 한다면 `python -X utf8` 또는 코드포인트·ASCII 기반 검사를 사용합니다.

### T-024 · PowerShell `Select-Object -Index 450..525` 범위 문법 오사용

**발생 단계**

- Phase/P4 단계: Phase 4 / case-003 추가 필요성 검토
- 관련 W-ID: W-070

**증상**

- 기획서 검증 계획 일부 줄을 확인하려고 `Get-Content ... | Select-Object -Index 450..525`를 실행했으나 PowerShell 매개변수 변환 오류가 발생했습니다.
- 오류는 `Cannot convert value "450..525" to type "System.Int32"`였습니다.

**확인한 원인**

- PowerShell에서 `Select-Object -Index`는 정수 배열을 받을 수 있지만, 명령 인자 위치에서 `450..525`가 의도한 배열로 전달되지 않았습니다.
- 이 프로젝트의 기본 셸은 PowerShell이므로 범위 선택 시 먼저 변수에 라인을 담고 `$lines[450..525]` 형태를 쓰는 편이 안전합니다.

**조치**

- `$lines = Get-Content ...; $lines[450..525]` 방식으로 재실행해 기획서의 A~H 합성 시나리오와 테스트 매트릭스를 확인했습니다.

**재발 방지·후속 조치**

- PowerShell에서 파일 줄 범위를 볼 때는 `$lines = Get-Content ...; $lines[start..end]` 패턴을 사용합니다.
- `Select-Object -Index`에 범위를 직접 넘기는 방식은 피합니다.

### T-025 · Notion 검색 도구의 `max_highlight_length` 허용치를 초과한 문제

**발생 단계**

- Phase/P4 단계: Phase 4 / P4-19 Notion 동기화 검증
- 관련 W-ID: W-072

**증상**

- Notion Phase 4 페이지에 W-072가 반영됐는지 검색으로 확인하는 과정에서 `max_highlight_length: 700`을 전달했습니다.
- Notion 검색 도구가 `maximum: 500` 제한을 반환하며 요청을 거절했습니다.

**확인한 원인**

- Notion 검색 도구의 `max_highlight_length` 최대값은 500입니다.
- 도구 설명에는 기본값과 최대값 제한이 있으므로, 검색 확인 시 과도하게 큰 하이라이트 길이를 넣으면 안 됩니다.

**조치**

- `max_highlight_length`를 500으로 낮춰 재검색했습니다.
- D-039 페이지 생성과 Phase 4 페이지 갱신 호출 성공, Phase 4 검색 결과 갱신 시각을 확인했습니다.

**재발 방지·후속 조치**

- Notion 검색 도구를 사용할 때 `max_highlight_length`는 500 이하로 설정합니다.
- 정확한 문구 검증이 필요하면 검색 하이라이트에만 의존하지 말고, 생성·업데이트 도구의 성공 응답과 대상 페이지 재조회 결과를 함께 확인합니다.

### T-026 · `interface.defaultPrompt` 128자 제한 초과로 Codex가 prompt를 무시한 문제

**발생 단계**

- Phase/P4 단계: Phase 4 / P4-19 Codex marketplace 설치 검증 보강
- 관련 W-ID: W-077

**증상**

- 임시 로컬 marketplace에서 `openbell-guard@openbell-guard-local`을 설치한 뒤 새 Codex 비대화 세션을 실행했습니다.
- 세션 시작 로그에서 OpenBell Guard의 `interface.defaultPrompt`가 128자를 초과해 무시된다는 경고가 표시됐습니다.
- 플러그인 자체는 설치·인식됐지만, starter prompt가 정상 노출되지 않을 수 있는 상태였습니다.

**확인한 원인**

- `src/.codex-plugin/plugin.json`의 `interface.defaultPrompt`가 긴 단일 문자열이었습니다.
- 현재 Codex plugin manifest 검증과 런타임은 default prompt 항목별 128자 제한을 적용합니다.

**조치**

- `src/.codex-plugin/plugin.json`의 `defaultPrompt`를 짧은 starter prompt 3개 배열로 변경했습니다.
- 각 prompt 길이는 `[56, 60, 56]`자로 제한 안에 들어오도록 확인했습니다.
- 스테이징 marketplace 복사본에도 같은 수정사항을 반영하고 cachebuster 버전으로 재설치했습니다.
- 공식 plugin validator와 새 Codex 비대화 세션 인식 검증을 다시 실행했습니다.

**재발 방지·후속 조치**

- `plugin.json`의 `interface.defaultPrompt`는 긴 설명문이 아니라 짧은 starter prompt 배열로 작성합니다.
- marketplace 설치 검증 후 Codex 시작 경고를 반드시 확인합니다.
- manifest를 수정하면 `validate_plugin.py`, ZIP 내부 manifest 점검, 새 세션 인식 확인을 함께 수행합니다.

### T-027 · PowerShell 파이프 기반 Python 검증에서 한글 리터럴 검색이 다시 실패한 문제

**발생 단계**

- Phase/P4 단계: Phase 4 / P4-19 제출 ZIP README 반영 확인
- 관련 W-ID: W-077
- 관련 기존 항목: T-023

**증상**

- `submission.zip` 내부 `README.md`에 marketplace 검증 문구가 들어갔는지 Python 임시 스크립트로 확인했습니다.
- ZIP 내부 README를 UTF-8로 정상 디코딩해 일부 내용을 출력하면 문구가 보였지만, 같은 스크립트 안의 한글 리터럴 포함 여부 검사는 `False`를 반환했습니다.

**확인한 원인**

- PowerShell here-string을 `python -`으로 파이프할 때, 임시 Python 코드 안의 한글 문자열 리터럴이 콘솔 인코딩 영향을 받아 예상과 다르게 전달될 수 있습니다.
- 파일 내용 자체의 UTF-8 문제는 아니었고, 검증 스크립트 작성 방식 문제였습니다.

**조치**

- 한글 리터럴 대신 `openbell-guard-local`, `installed, enabled`, `openbell-guard` 같은 ASCII marker로 ZIP 내부 README와 Skill 반영 여부를 확인했습니다.
- 필요한 경우 `unicode_escape` 출력으로 실제 파일 내용을 확인했습니다.

**재발 방지·후속 조치**

- Windows PowerShell에서 ZIP·Markdown 문구 자동 검증을 할 때는 가능하면 ASCII marker를 사용합니다.
- 반드시 한글 문구를 검사해야 하면 Python 코드를 파일로 저장하거나 `python -X utf8`과 `unicode_escape` 기반 확인을 사용합니다.
- T-023의 교훈을 반복 적용해야 하며, PowerShell 파이프 안에 한글 리터럴을 직접 넣는 방식은 기본 검증 경로로 쓰지 않습니다.
