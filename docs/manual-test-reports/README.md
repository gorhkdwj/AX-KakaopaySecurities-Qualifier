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

## 재실행 명령

프로젝트 루트에서 다음 명령을 실행합니다.

```powershell
python .\src\skills\openbell-guard\scripts\run_openbell.py --bundle .\out\manual-tests\case-001-market-open-watchlist-review\bundle --output .\out\manual-tests\case-001-market-open-watchlist-review\result
python .\src\skills\openbell-guard\scripts\validate_bundle.py --output .\out\manual-tests\case-001-market-open-watchlist-review\result
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
