# 수동 테스트 보고서: case-002-large-scenario

## 1. 결론

OpenBell Guard는 80,000행 규모의 현실형 합성 데이터에서 기대한 판정과 일치했습니다.

- 입력 규모: `logs.jsonl` 60,000행, `metrics.csv` 20,000행
- 분석 결과: `market_data`, `watchlist_info`는 `outage_detected`
- 분석 결과: `order_execution`은 `healthy`
- ground truth 대조: 3개 서비스 경로 모두 기대 상태, 장애 시작, 회복 시각 일치
- 출력 validator: `passed`
- 민감정보 원문 잔존 검색: 결과 폴더 기준 히트 없음

이 테스트는 실제 카카오페이증권 운영 로그가 아니라, OpenBell Guard의 로컬 분석 파이프라인이 복잡한 합성 상황에서도 안정적으로 동작하는지 확인하기 위한 통제된 더미데이터 검증입니다.

## 2. 이 테스트가 필요한 이유

`case-001`은 사람이 흐름을 이해하기 쉬운 작은 예제였습니다. 하지만 작은 데이터만으로는 다음 질문에 충분히 답하기 어렵습니다.

- 정상 경로에 소량의 오류가 있어도 장애로 과장하지 않는가?
- 장애 경로 안에도 성공 요청이 섞여 있을 때 장애를 놓치지 않는가?
- 임계값 근처의 경계 상황을 안정적으로 처리하는가?
- 시세·관심종목 경로의 장애와 주문 경로의 정상을 계속 분리하는가?
- 대량 로그 안에 가짜 민감정보 패턴이 드물게 섞여도 결과물에 원문이 남지 않는가?

그래서 `case-002`는 행 수만 늘리지 않고, 정상·장애·회복·경계·노이즈를 함께 넣은 대규모 합성 시나리오로 구성했습니다.

## 3. 파일 구조

| 구분 | 경로 | 설명 |
| --- | --- | --- |
| 생성기 | `tools/generate_large_scenario.py` | seed 고정 기반 대규모 합성 데이터 생성기 |
| 합성 입력 번들 | `out/manual-tests/case-002-large-scenario/bundle/` | OpenBell Guard 입력 파일 4개 |
| Ground truth | `out/manual-tests/case-002-large-scenario/ground-truth.json` | 기대 상태, 장애 시작, 회복 시각, 설계 요약 |
| 생성 요약 | `out/manual-tests/case-002-large-scenario/generation-summary.md` | 생성 규모와 기대 결과 요약 |
| 실제 실행 결과 | `out/manual-tests/case-002-large-scenario/result/` | CLI가 생성한 분석 결과 |
| 휴먼 리뷰 보고서 | `docs/manual-test-reports/case-002-large-scenario.md` | 사람이 검토하기 위한 본 문서 |

`out/`은 로컬 실행 산출물 위치이며 Git 추적 대상이 아닙니다. GitHub에는 생성기와 본 보고서만 올라갑니다.

## 4. 합성 데이터 설계

| 항목 | 값 |
| --- | --- |
| case ID | `case-002-large-scenario` |
| seed | `20260630` |
| 기준 구간 | 2026-06-30 08:50:00~09:00:00 KST |
| 사고 구간 | 2026-06-30 09:00:00~09:10:00 KST |
| 로그 행 수 | 60,000 |
| 메트릭 행 수 | 20,000 |
| 전체 수용 행 수 | 80,000 |
| 서비스 경로 | `market_data`, `watchlist_info`, `order_execution` |
| 마스킹 검증용 가짜 민감정보 삽입 행 | 4 |

설계상 단순한 “전부 실패” 데이터는 피했습니다.

- `market_data`는 09:01~09:04 KST에 장애 버킷이 되도록 설계했습니다.
- `watchlist_info`는 09:01~09:03 KST에 장애 버킷이 되도록 설계했습니다.
- `order_execution`은 소량의 오류와 지연 노이즈가 있지만 임계치를 넘지 않도록 설계했습니다.
- 장애 경로에도 성공 요청이 섞여 있습니다.
- 정상 경로에도 소량의 timeout, 느린 응답, 관측 지연, 누락 `observed_time`이 섞여 있습니다.

## 5. 실행 명령

프로젝트 루트에서 아래 명령을 실행했습니다.

```powershell
python .\tools\generate_large_scenario.py --output .\out\manual-tests\case-002-large-scenario --seed 20260630 --log-records 60000 --metric-records 20000
python .\src\skills\openbell-guard\scripts\run_openbell.py --bundle .\out\manual-tests\case-002-large-scenario\bundle --output .\out\manual-tests\case-002-large-scenario\result
python .\src\skills\openbell-guard\scripts\validate_bundle.py --output .\out\manual-tests\case-002-large-scenario\result
```

민감정보 원문 잔존 여부는 결과 폴더를 대상으로 다음 패턴 검색을 수행했습니다.

```powershell
rg -n "case002BearerToken|case002SyntheticKey|analyst@example.com|010-2222-3333|999-888-777666" out\manual-tests\case-002-large-scenario\result
```

검색 결과는 `NO_MATCH_IN_RESULT`였습니다.

## 6. 자동 검증 결과

| 검증 항목 | 결과 |
| --- | --- |
| CLI 실행 상태 | `report_validated` |
| 출력 validator 상태 | `passed` |
| `analysis_schema` | `passed` |
| `confirmed_fact_evidence` | `passed` |
| `evidence_references` | `passed` |
| `report_claim_refs` | `passed` |
| `secret_residue` | `passed` |
| `raw_excerpts_emitted` | `false` |

실행 결과 요약입니다.

| 항목 | 값 |
| --- | ---: |
| accepted `logs.jsonl` rows | 60,000 |
| accepted `metrics.csv` rows | 20,000 |
| total accepted rows | 80,000 |
| bucket count | 60 |
| breach bucket count | 7 |
| healthy bucket count | 53 |
| total redactions | 20 |

## 7. Ground truth 대조 결과

| 서비스 경로 | 기대 상태 | 실제 상태 | 기대 장애 시작 | 실제 장애 시작 | 기대 회복 | 실제 회복 | 결과 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `market_data` | `outage_detected` | `outage_detected` | 2026-06-30T00:01:00+00:00 | 2026-06-30T00:01:00+00:00 | 2026-06-30T00:05:00+00:00 | 2026-06-30T00:05:00+00:00 | 통과 |
| `watchlist_info` | `outage_detected` | `outage_detected` | 2026-06-30T00:01:00+00:00 | 2026-06-30T00:01:00+00:00 | 2026-06-30T00:04:00+00:00 | 2026-06-30T00:04:00+00:00 | 통과 |
| `order_execution` | `healthy` | `healthy` | `null` | `null` | `null` | `null` | 통과 |

## 8. 주요 출력 파일 크기

| 파일 | 크기 |
| --- | ---: |
| `bundle/logs.jsonl` | 22,874,075 bytes |
| `bundle/metrics.csv` | 2,123,306 bytes |
| `result/analysis.json` | 239,820 bytes |
| `result/openbell-report.md` | 22,360 bytes |
| `result/output-validation.json` | 898 bytes |
| `ground-truth.json` | 23,235 bytes |

출력 크기는 대규모 입력 대비 통제 가능한 수준으로 유지되었습니다. 특히 원본 로그 행 전체를 보고서에 복사하지 않고, 근거 ID와 요약 위치를 사용했기 때문에 결과 파일이 과도하게 커지지 않았습니다.

## 9. 휴먼 리뷰 체크리스트

| 항목 | 판정 | 근거 |
| --- | --- | --- |
| 합성 데이터만 사용했는가 | 통과 | 생성기는 고정 seed 기반 synthetic 데이터만 생성 |
| 너무 뻔한 전부 성공·전부 실패 패턴을 피했는가 | 통과 | 정상 경로에도 노이즈, 장애 경로에도 성공 요청 포함 |
| 기대 정답과 실제 분석 결과가 일치하는가 | 통과 | 3개 서비스 경로 모두 상태·장애 시작·회복 시각 일치 |
| 주문 경로를 장애로 과장하지 않았는가 | 통과 | `order_execution=healthy` |
| 민감정보 원문이 결과 폴더에 남지 않았는가 | 통과 | validator `secret_residue=passed`, `rg` 검색 히트 없음 |
| 실제 운영 원인으로 단정하지 않았는가 | 통과 | 보고서는 합성 데이터 기반 가설과 추가 확인 필요를 분리 |

## 10. 실행 중 발생한 문제와 조치

첫 실행에서는 `service-map.json` 검증 오류가 발생했습니다.

- 오류: `INP009_SERVICE_MAP`
- 원인: 외부 피드처럼 보이게 하려고 `synthetic-exchange-feed`를 dependency에 넣었으나, 현재 service map 계약은 dependencies가 같은 파일 안의 서비스만 참조해야 합니다.
- 조치: 해당 외부 dependency 참조를 제거하고, 외부 의존성 성격은 `dependency_type=exchange`와 로그 메시지 패턴으로 표현했습니다.
- 결과: 재생성 후 CLI 실행과 validator가 통과했습니다.

또한 ground truth 대조용 임시 Python 명령을 처음에 Bash heredoc 형태로 실행해 PowerShell 문법 오류가 발생했습니다. 같은 내용을 PowerShell here-string 방식으로 재실행해 정상 대조했습니다.

## 11. 한계

- 이 데이터는 실제 카카오페이증권 운영 로그가 아닙니다.
- 이 검증은 OpenBell Guard의 로컬 분석 안정성을 보여주지만, 실제 운영 환경 성능이나 실제 장애 원인을 입증하지는 않습니다.
- 현재 ground truth 대조는 서비스 경로 상태, 장애 시작, 회복 시각 중심입니다. 향후 필요하면 bucket별 세부 기대값까지 자동 비교할 수 있습니다.

## 12. 검토 결론

- 자동 검증 결론: 통과
- 휴먼 리뷰 예비 결론: 통과
- 다음 권장 작업: 이 case-002 결과를 P4-19 제출 전 검토 보고서에 반영하고, 필요하면 bucket별 세부 ground truth 비교를 추가합니다.
