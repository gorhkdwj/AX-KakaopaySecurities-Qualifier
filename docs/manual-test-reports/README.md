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
