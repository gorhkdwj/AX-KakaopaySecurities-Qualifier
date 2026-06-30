# 수동 테스트 보고서: case-001-market-open-watchlist-review

## 1. 결론

OpenBell Guard는 이 합성 케이스에서 의도한 대로 동작했습니다.

- `market_data`와 `watchlist_info`는 09:00~09:01 KST 두 개 연속 60초 버킷에서 오류율 66.667%로 임계치 50%를 초과해 `outage_detected`로 판정되었습니다.
- `order_execution`은 같은 구간에서 오류율 0%로 유지되어 `healthy`로 판정되었습니다.
- 따라서 플러그인은 “시세·관심종목 경로의 부분 장애”와 “주문 경로 정상”을 분리했습니다.
- 원인 가설은 제시했지만, 실제 근본 원인은 확정하지 않았습니다.
- 결과 폴더 기준 민감정보 잔존 검사는 통과했습니다.

## 2. 이 테스트가 필요한 이유

OpenBell Guard의 핵심 가치는 장애 상황을 무작정 “전체 서비스 장애”로 뭉뚱그리지 않고, 어떤 서비스 경로가 영향을 받았고 어떤 경로는 정상인지 나누어 설명하는 데 있습니다.

이번 케이스는 다음 상황을 확인하기 위해 만들었습니다.

1. 국내장 개장 직후 요청이 몰린 것처럼 보이는 시간대를 둡니다.
2. 시세 경로(`market_data`)와 관심종목·정보 경로(`watchlist_info`)만 2분 동안 악화시킵니다.
3. 주문·체결 경로(`order_execution`)는 같은 시간대에도 정상으로 둡니다.
4. 원본 입력에는 마스킹 검증용 가짜 토큰·이메일·전화번호·계좌번호 형태 값을 넣습니다.
5. 결과 보고서에는 원문 민감정보가 남지 않는지 확인합니다.

이 구조는 “장애 영향 범위를 정확히 좁혀 말하는가”와 “민감정보를 안전하게 다루는가”를 동시에 확인합니다.

## 3. 파일 구조

| 구분 | 경로 | 설명 |
| --- | --- | --- |
| 합성 입력 번들 | `out/manual-tests/case-001-market-open-watchlist-review/bundle/` | `incident.json`, `service-map.json`, `logs.jsonl`, `metrics.csv` |
| 실제 실행 결과 | `out/manual-tests/case-001-market-open-watchlist-review/result/` | CLI가 생성한 분석 JSON, Markdown 보고서, 검증 결과 |
| 휴먼 리뷰 보고서 | `docs/manual-test-reports/case-001-market-open-watchlist-review.md` | 사람이 읽고 판단하기 위한 본 문서 |
| 수동 테스트 안내 | `docs/manual-test-reports/README.md` | 수동 테스트 폴더 구조와 재실행 방법 |
| 휴먼 리뷰 템플릿 | `docs/manual-test-reports/human-review-template.md` | 다음 케이스 작성용 양식 |

`out/`은 로컬 실행 산출물 위치이므로 Git 추적 대상이 아닙니다. 다만 현재 작업 폴더에는 입력과 결과가 그대로 남아 있어 직접 열람하고 재실행할 수 있습니다.

## 4. 입력 데이터 요약

| 항목 | 값 |
| --- | --- |
| 기준 구간 | 2026-06-30 08:58:00~09:00:00 KST |
| 사고 구간 | 2026-06-30 09:00:00~09:04:00 KST |
| 서비스 경로 | `market_data`, `watchlist_info`, `order_execution` |
| 로그 행 수 | 54 |
| 메트릭 행 수 | 15 |
| 판정 임계치 | 서비스 경로별 오류율 50% 초과 시 breach |
| 의도된 악화 경로 | `market_data`, `watchlist_info` |
| 의도된 정상 경로 | `order_execution` |

오류율은 한 60초 버킷 안에서 `error` 또는 `timeout` 상태인 요청 수를 전체 요청 수로 나누어 계산합니다. 예를 들어 요청 3건 중 2건이 오류이면 오류율은 `2 / 3 * 100 = 66.667%`입니다.

## 5. 실행 명령

프로젝트 루트에서 아래 명령을 실행했습니다.

```powershell
python .\src\skills\openbell-guard\scripts\run_openbell.py --bundle .\out\manual-tests\case-001-market-open-watchlist-review\bundle --output .\out\manual-tests\case-001-market-open-watchlist-review\result
python .\src\skills\openbell-guard\scripts\validate_bundle.py --output .\out\manual-tests\case-001-market-open-watchlist-review\result
```

민감정보 잔존 여부는 결과 폴더를 대상으로 다음 패턴 검색을 수행했습니다.

```powershell
rg -n "syntheticBearerToken123|syntheticKeyForMasking|analyst@example.com|010-1234-5678|123-456-789012" out\manual-tests\case-001-market-open-watchlist-review\result
```

검색 결과는 히트 없음이었습니다. PowerShell 기준 `rg` 종료 코드 1은 “검색 결과 없음”을 의미하므로, 이 확인에서는 기대한 결과입니다.

## 6. 자동 검증 결과

| 검증 항목 | 결과 | 근거 파일 |
| --- | --- | --- |
| CLI 실행 상태 | `report_validated` | `out/manual-tests/case-001-market-open-watchlist-review/result/openbell-cli-summary.json` |
| 출력 검증 상태 | `passed` | `out/manual-tests/case-001-market-open-watchlist-review/result/output-validation.json` |
| 분석 스키마 | `passed` | `output-validation.json` |
| 근거 참조 | `passed` | `output-validation.json` |
| 보고서 claim 참조 | `passed` | `output-validation.json` |
| 민감정보 잔존 검사 | `passed` | `output-validation.json` |
| raw excerpt 출력 | `false` | `openbell-cli-summary.json`, `output-validation.json` |

자동 검증기는 총 14개 결과 파일을 확인했고, fatal 이슈는 0건이었습니다.

## 7. 핵심 판정 결과

| 서비스 경로 | 상태 | breach 버킷 수 | healthy 버킷 수 | 장애 시작 | 회복 시각 | 해석 |
| --- | --- | ---: | ---: | --- | --- | --- |
| `market_data` | `outage_detected` | 2 | 4 | 2026-06-30T00:00:00+00:00 | 2026-06-30T00:02:00+00:00 | 시세 경로가 09:00~09:01 KST 동안 악화된 것으로 판정 |
| `watchlist_info` | `outage_detected` | 2 | 4 | 2026-06-30T00:00:00+00:00 | 2026-06-30T00:02:00+00:00 | 관심종목·정보 경로가 09:00~09:01 KST 동안 악화된 것으로 판정 |
| `order_execution` | `healthy` | 0 | 6 | `null` | `null` | 주문·체결 경로는 같은 시간대에 정상으로 판정 |

장애 시작과 회복 시각은 결과 JSON에서 UTC로 기록됩니다. 사람이 읽는 검토에서는 KST 기준으로 각각 09:00, 09:02입니다.

## 8. 처음 보는 사용자를 위한 해석 가이드

이 케이스는 OpenBell Guard의 가장 작은 사용 예제입니다. 처음 보는 사용자는 “플러그인이 무엇을 입력받고, 어떤 결론을 내며, 그 결론을 어떻게 검토해야 하는지”를 이 문서 하나로 따라갈 수 있습니다.

먼저 상황을 아주 단순하게 생각하면 됩니다.

- 09:00에 국내장이 열렸다고 가정합니다.
- 사용자가 동시에 시세와 관심종목 화면을 많이 조회합니다.
- 이때 시세 경로와 관심종목 경로만 일부 실패합니다.
- 주문·체결 경로는 정상입니다.
- 플러그인이 이 상황을 “전체 장애”로 과장하지 않고, “부분 장애”로 분리하는지 확인합니다.

이 테스트에서 가장 중요한 질문은 하나입니다.

> 시세와 관심종목은 느려졌지만, 주문은 정상인 상황을 OpenBell Guard가 구분할 수 있는가?

결과는 “구분할 수 있다”입니다. `market_data`와 `watchlist_info`는 `outage_detected`, `order_execution`은 `healthy`로 나뉘었습니다.

## 9. 대표 출력 인용과 읽는 법

아래 값들은 실제 실행 결과에서 확인한 핵심 출력입니다. 원본 로그 전문을 복사하지 않고, 사용자가 판단하는 데 필요한 요약 수치만 인용합니다.

```text
run_status = report_validated
bucket_state_counts = breach 4, healthy 14
path_status_counts = outage_detected 2, healthy 1
claim_count = 24
evidence_count = 27
raw_excerpts_emitted = false
```

이 출력은 다음처럼 읽으면 됩니다.

- `report_validated`: 분석뿐 아니라 보고서 생성과 출력 검증까지 끝났다는 뜻입니다.
- `breach 4`: 전체 60초 bucket 중 기준을 넘은 bucket이 4개라는 뜻입니다.
- `outage_detected 2`: 3개 서비스 경로 중 2개 경로에서 장애가 감지됐다는 뜻입니다.
- `healthy 1`: 나머지 1개 경로는 정상이라는 뜻입니다.
- `raw_excerpts_emitted=false`: 원본 로그 전문을 보고서에 싣지 않았다는 뜻입니다.

작은 예제에서 실제 사고 구간 bucket은 다음과 같이 해석됩니다.

| 서비스 경로 | 시간 KST | 요청 수 | 오류 수 | 오류율 | 판정 |
| --- | --- | ---: | ---: | ---: | --- |
| `market_data` | 09:00 | 3 | 2 | 66.667% | 기준 초과 |
| `market_data` | 09:01 | 3 | 2 | 66.667% | 기준 초과 |
| `market_data` | 09:02 | 3 | 0 | 0.000% | 회복 |
| `watchlist_info` | 09:00 | 3 | 2 | 66.667% | 기준 초과 |
| `watchlist_info` | 09:01 | 3 | 2 | 66.667% | 기준 초과 |
| `watchlist_info` | 09:02 | 3 | 0 | 0.000% | 회복 |
| `order_execution` | 09:00~09:03 | 각 3 | 0 | 0.000% | 정상 |

여기서 오류율 66.667%는 요청 3건 중 2건이 실패했다는 의미입니다. 이 케이스의 임계치는 50% 초과이므로, 66.667%는 `breach`입니다. 반면 주문 경로는 같은 시간대에도 오류율이 0%이므로 `healthy`입니다.

## 10. 플러그인 사용자가 취해야 할 해석과 조치

이 결과를 실제 업무 상황에 적용한다면 다음처럼 받아들이면 됩니다.

1. 장애 영향 범위를 좁힙니다.
   - “전체 서비스 장애”가 아니라 “시세·관심종목 경로 중심의 부분 장애”로 표현합니다.
   - 주문·체결 경로는 현재 데이터 기준 정상으로 분리합니다.

2. 고객 공지나 내부 공유 문구를 보수적으로 작성합니다.
   - 적절한 표현: “일부 시세 및 관심종목 정보 조회 지연 또는 오류가 감지되었습니다.”
   - 피해야 할 표현: “주문 장애가 발생했습니다.”, “외부 거래소 장애가 원인입니다.”

3. 근본 원인은 확정하지 않습니다.
   - 이 테스트는 장애 신호를 감지하는 예제이지, 실제 운영 원인을 증명하는 자료가 아닙니다.
   - 실제 운영에서는 trace, 하위 시스템 지표, 외부 상태 데이터를 추가로 봐야 합니다.

4. 보안 검토를 함께 확인합니다.
   - 이 케이스에는 가짜 토큰·이메일·전화번호·계좌번호 형태 값이 들어 있습니다.
   - 결과 폴더 기준 민감정보 원문 검색은 히트가 없었습니다.
   - 따라서 “분석은 하되, 보고서에 원문 민감정보를 남기지 않는다”는 안전 모델을 확인할 수 있습니다.

## 11. 이 케이스가 보여주는 OpenBell Guard의 핵심 가치

이 작은 예제는 기능을 과시하기 위한 대규모 benchmark가 아닙니다. 대신 사용자가 직관적으로 이해할 수 있는 최소 상황을 만듭니다.

핵심 가치는 세 가지입니다.

| 가치 | 이 케이스에서 확인한 내용 |
| --- | --- |
| 영향 범위 분리 | 시세·관심종목 장애와 주문 정상 상태를 분리 |
| 과장 방지 | 주문 경로를 장애로 잘못 부풀리지 않음 |
| 안전한 보고 | 원본 로그 전문과 민감정보를 보고서에 남기지 않음 |

따라서 case-001은 “OpenBell Guard가 어떤 플러그인인지 처음 이해하는 입문 예제”로 보는 것이 좋습니다. 실제 성능이나 복잡한 노이즈 대응은 [case-002 보고서](./case-002-large-scenario.md)에서 확인합니다.

## 12. 휴먼 리뷰 체크리스트

| 항목 | 판정 | 근거 |
| --- | --- | --- |
| 합성 데이터만 사용했는가 | 통과 | 케이스 ID, 서비스명, trace ID, 토큰·계좌 형태 값 모두 합성 목적으로 작성 |
| 입력 의도와 기획서의 문제 상황이 일치하는가 | 통과 | 국내장 개장 피크, 시세·관심종목 영향, 주문 경로 분리 확인이라는 기획 목적과 일치 |
| 서비스 경로별 영향이 과장 없이 분리되었는가 | 통과 | `market_data`, `watchlist_info`만 장애 감지, `order_execution`은 정상 |
| 원인 가설이 근거 수준을 넘어 단정되지 않았는가 | 통과 | 출력 보고서가 근본 원인을 확정하지 않고 추가 확인 필요를 표시 |
| 고객 공지·보상·법적 판단·운영 조치가 자동 확정되지 않았는가 | 통과 | `openbell-report.md`에 사람 검토 필요 문구 포함 |
| 결과 폴더에 민감정보 원문이 남지 않았는가 | 통과 | `output-validation.json`의 `secret_residue=passed`, 결과 폴더 `rg` 검색 히트 없음 |
| 보고서가 비전공자도 이해할 수 있게 설명되어 있는가 | 통과 | 본 문서에 처음 보는 사용자용 해석 가이드, 대표 출력 인용, 조치 방향을 보강 |

## 13. 남은 검토 사항

- 자동 생성 보고서 `openbell-report.md`는 구조적으로는 검증되었지만, 최종 제출 전 사람 읽기용 표현을 더 다듬을 수 있습니다.
- 현재 수동 테스트 산출물은 `out/`에 남아 있으므로 GitHub에는 올라가지 않습니다. 원격 저장소에도 이 케이스의 원본 입력과 결과를 보존하려면 별도 tracked fixture 또는 압축 아카이브 정책을 정해야 합니다.
- 이번 케이스는 대표 수동 케이스 1개입니다. 다음 단계에서는 외부 중개사 장애, 불완전 데이터, 민감정보 포함 입력 같은 다른 시나리오도 같은 방식으로 남길 수 있습니다.

## 14. 검토 결론

- 자동 검증 결론: 통과
- 휴먼 리뷰 예비 결론: 통과
- 최종 판단: 사용자 직접 검토 후 `승인 / 수정 후 재검토 / 재실행 필요` 중 하나로 표시하면 됩니다.
