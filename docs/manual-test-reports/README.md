# OpenBell Guard 수동 테스트·휴먼 리뷰 안내

이 폴더는 OpenBell Guard를 사용자가 직접 더미 데이터로 실행해보고, 결과를 사람이 검토할 수 있도록 만든 보고서를 보관합니다.

## 폴더 역할

- `out/manual-tests/<case-id>/bundle/`: 수동 테스트에 사용한 합성 입력 데이터입니다.
- `out/manual-tests/<case-id>/result/`: 실제 CLI 실행으로 생성된 분석 결과입니다.
- `docs/manual-test-reports/<case-id>.md`: 사람이 검토하기 쉽게 정리한 보고서입니다.
- `docs/manual-test-reports/human-review-template.md`: 새 수동 테스트 케이스를 만들 때 복사해 사용할 검토 양식입니다.

`out/` 폴더는 로컬 실행 산출물 보관 위치이며 Git 추적 대상이 아닙니다. 제출물이나 원격 저장소에 포함해야 하는 대표 케이스는 별도 논의 후 `src/tests/fixtures/` 또는 `docs/`로 승격해야 합니다.

## 현재 수동 테스트 케이스

| 케이스 ID | 목적 | 입력 | 결과 | 휴먼 리뷰 |
| --- | --- | --- | --- | --- |
| `case-001-market-open-watchlist-review` | 국내장 개장 직후 시세·관심종목 경로만 악화되고 주문 경로는 정상인 상황을 부분 장애로 판정하는지 확인 | `out/manual-tests/case-001-market-open-watchlist-review/bundle/` | `out/manual-tests/case-001-market-open-watchlist-review/result/` | [case-001 보고서](./case-001-market-open-watchlist-review.md) |
| `case-002-large-scenario` | 80,000행 규모의 현실형 합성 데이터에서 장애 경로와 정상 주문 경로를 안정적으로 분리하는지 확인 | `out/manual-tests/case-002-large-scenario/bundle/` | `out/manual-tests/case-002-large-scenario/result/` | [case-002 보고서](./case-002-large-scenario.md) |

## 처음 보는 사람을 위한 5분 사용 흐름

OpenBell Guard를 처음 보는 사람은 아래 순서대로 보면 됩니다. 처음부터 JSON 파일을 모두 열 필요는 없습니다.

1. 먼저 이 README에서 어떤 테스트 케이스가 있는지 확인합니다.
2. 작은 예제로 흐름을 이해하려면 [case-001 보고서](./case-001-market-open-watchlist-review.md)를 읽습니다.
3. 대규모 현실형 검증 결과를 보고 싶으면 [case-002 보고서](./case-002-large-scenario.md)를 읽습니다.
4. 실제 플러그인을 실행하려면 아래 재실행 명령을 PowerShell에서 실행합니다.
5. 실행 후에는 `result/openbell-report.md`를 먼저 열고, 더 자세한 기계 판정은 `state-summary.json`, `metric-summary.json`, `output-validation.json` 순서로 확인합니다.

추천 읽기 순서는 다음과 같습니다.

| 순서 | 파일 | 처음 보는 사용자가 확인할 것 |
| --- | --- | --- |
| 1 | `docs/manual-test-reports/<case-id>.md` | 사람이 읽기 좋게 정리한 목적, 결과, 해석 |
| 2 | `out/manual-tests/<case-id>/result/openbell-report.md` | 플러그인이 생성한 보고서 초안 |
| 3 | `out/manual-tests/<case-id>/result/openbell-cli-summary.json` | 실행이 성공했는지, 어떤 출력이 생성됐는지 |
| 4 | `out/manual-tests/<case-id>/result/state-summary.json` | 서비스 경로별 최종 상태, 장애 시작, 회복 시각 |
| 5 | `out/manual-tests/<case-id>/result/metric-summary.json` | 1분 단위 오류율, 지연, 수집 지연 |
| 6 | `out/manual-tests/<case-id>/result/output-validation.json` | 보고서와 JSON 출력이 검증을 통과했는지 |
| 7 | `out/manual-tests/<case-id>/result/sanitization-report.md` | 민감정보 마스킹이 어떻게 처리됐는지 |

가장 중요한 결론만 보고 싶다면 각 case 문서의 `결론`, `핵심 판정 결과`, `처음 보는 사용자를 위한 해석 가이드`를 먼저 읽으면 됩니다.

## 핵심 용어 빠른 설명

| 용어 | 쉬운 설명 | 이 프로젝트에서의 의미 |
| --- | --- | --- |
| bundle | 플러그인에 넣는 입력 파일 묶음 | `incident.json`, `logs.jsonl`, `metrics.csv`, `service-map.json` 같은 파일을 함께 넣은 폴더 |
| service path | 서비스 기능 경로 | 시세 `market_data`, 주문·체결 `order_execution`, 관심종목·정보 `watchlist_info` |
| bucket | 시간을 일정 단위로 자른 분석 칸 | 현재는 60초 단위로 요청 수, 오류 수, 지연을 계산 |
| healthy | 정상 | 기준을 넘는 오류율·지연이 발견되지 않은 상태 |
| breach | 기준 초과 | 해당 60초 bucket에서 오류율이나 지연이 설정 기준을 넘은 상태 |
| outage_detected | 장애 감지 | breach가 연속적으로 나타나 서비스 경로 단위 장애로 판정된 상태 |
| recovery_time | 회복 시각 | 장애 이후 다시 healthy로 돌아온 첫 시각 |
| claim | 보고서의 주장 | “09:01에 오류율이 기준을 넘었다”처럼 검증 가능한 문장 |
| evidence | claim의 근거 | claim을 뒷받침하는 로그 범위, 메트릭, service map 참조 |
| raw excerpt | 원본 로그 일부 | 이 프로젝트에서는 민감정보 보호를 위해 보고서에 원본 전문을 넣지 않음 |

처음 보는 사용자는 `healthy`, `breach`, `outage_detected`만 구분해도 주요 결과를 이해할 수 있습니다. `breach`는 1분짜리 작은 칸의 기준 초과이고, `outage_detected`는 그런 신호를 묶어 서비스 경로 전체에 장애가 있었다고 보는 판정입니다.

## 왜 `out/` 전체를 Git에 올리지 않는가

`out/`에는 실제 실행으로 만들어진 원본 입력, 마스킹된 복사본, 분석 JSON, 보고서 초안이 모두 들어 있습니다. 이 폴더를 통째로 Git에 올리지 않는 이유는 다음과 같습니다.

- 대용량 로그와 메트릭이 포함되어 저장소가 빠르게 무거워집니다.
- 실행할 때마다 다시 만들 수 있는 재생성 산출물입니다.
- 지금은 합성 데이터지만, 나중에 실제 테스트 데이터가 섞이면 민감정보 노출 위험이 있습니다.
- 심사자나 포트폴리오 독자에게는 원본 로그 덤프보다 해석이 붙은 Markdown 문서가 훨씬 읽기 좋습니다.

따라서 이 프로젝트는 다음 원칙을 사용합니다.

| 구분 | Git 포함 여부 | 이유 |
| --- | --- | --- |
| `out/manual-tests/.../bundle/` | 제외 | 재생성 가능한 입력 산출물, 대용량 가능성 |
| `out/manual-tests/.../result/` | 제외 | 실행 결과와 중간 JSON, 민감정보 관리 위험 |
| `tools/generate_large_scenario.py` | 포함 | case-002를 재생성하는 코드 |
| `docs/manual-test-reports/*.md` | 포함 | 사람이 읽는 사용 예제, 해석 가이드, 검증 요약 |

## 대규모 합성 로그 설계 원칙

대규모 수동 테스트는 행 수만 늘리는 방식으로 만들지 않습니다. 실무에서 실제로 나타날 수 있는 복잡성과 노이즈를 섞어 OpenBell Guard가 과장 없이 탐지하는지 확인합니다.

다음 원칙을 적용합니다.

1. 재현 가능하도록 random seed는 고정하되, 모든 행이 한눈에 정답처럼 보이는 단순 패턴은 피합니다.
2. 정상 경로에도 일시적인 timeout, 느린 응답, 관측 지연, 일부 누락 행을 소량 포함합니다.
3. 장애 경로에도 성공 요청을 섞어 “전부 실패”처럼 뻔한 장애를 만들지 않습니다.
4. 개장 직후처럼 급격히 나빠지는 구간, 서서히 회복되는 구간, 임계값 50% 근처의 경계 구간을 함께 둡니다.
5. `market_data`, `watchlist_info`, `order_execution`이 서로 완전히 독립적이지도, 완전히 같은 패턴도 아니도록 만듭니다.
6. 외부 의존성 문제처럼 보이는 신호와 내부 처리 지연처럼 보이는 신호를 함께 넣되, 실제 근본 원인을 단정할 수 없게 설계합니다.
7. 로그의 `event_time`과 `observed_time` 차이를 다양하게 만들어 관측 지연 판단을 확인합니다.
8. trace ID, severity, status, message는 반복 문자열만 쓰지 않고 여러 현실적인 변형을 둡니다.
9. 마스킹 검증용 가짜 토큰·이메일·전화번호·계좌번호 형태 값은 드물게 삽입하되, 실제 비밀정보는 절대 사용하지 않습니다.
10. 기대 정답은 입력 bundle 안에 섞지 않고, 별도 보고서나 검증용 ground truth 요약으로 관리합니다.

이 원칙의 목적은 합성 데이터가 실제 운영 로그라고 주장하기 위한 것이 아닙니다. 목적은 통제된 더미데이터 안에서 플러그인의 탐지 안정성, 오판 방지, 마스킹, 출력 검증을 더 강하게 확인하는 것입니다.

## 재실행 명령

프로젝트 루트에서 다음 명령을 실행합니다.

```powershell
python .\src\skills\openbell-guard\scripts\run_openbell.py --bundle .\out\manual-tests\case-001-market-open-watchlist-review\bundle --output .\out\manual-tests\case-001-market-open-watchlist-review\result
python .\src\skills\openbell-guard\scripts\validate_bundle.py --output .\out\manual-tests\case-001-market-open-watchlist-review\result
```

대규모 case-002는 먼저 생성기를 실행한 뒤 분석합니다.

```powershell
python .\tools\generate_large_scenario.py --output .\out\manual-tests\case-002-large-scenario --seed 20260630 --log-records 60000 --metric-records 20000
python .\src\skills\openbell-guard\scripts\run_openbell.py --bundle .\out\manual-tests\case-002-large-scenario\bundle --output .\out\manual-tests\case-002-large-scenario\result
python .\src\skills\openbell-guard\scripts\validate_bundle.py --output .\out\manual-tests\case-002-large-scenario\result
```

## 휴먼 리뷰 기준

자동 검증이 통과하더라도 다음 항목은 사람이 확인해야 합니다.

1. 합성 데이터 의도가 실제 기획서의 문제 상황과 맞는지 확인합니다.
2. 플러그인이 전체 장애를 과장하지 않고 서비스 경로별로 분리했는지 확인합니다.
3. 원인 가설이 증거보다 강하게 단정되지 않았는지 확인합니다.
4. 고객 공지, 법적 판단, 보상 여부, 운영 조치가 자동 확정되지 않았는지 확인합니다.
5. 결과 폴더에 민감정보 원문이 남지 않았는지 확인합니다.

## 주의사항

- 이 폴더의 보고서는 사람 검토를 돕는 문서이며 카카오페이증권의 실제 운영 장애 분석 결과가 아닙니다.
- 합성 데이터에 들어간 토큰·계좌·전화번호·이메일 형태 값은 마스킹 검증을 위한 가짜 값입니다.
- 실제 고객정보, 실제 계좌정보, 실제 API 키나 토큰을 입력하지 않습니다.
