# P4-18 성능·회귀 benchmark 결과

## 결론

P4-18 기본 benchmark는 통과했습니다.

- 입력: 합성 지원 한도 번들
  - `logs.jsonl`: 100,000행
  - `metrics.csv`: 50,000행
- 실행 방식: 준비 실행 1회 후 측정 실행 5회
- M-016 실행시간 중앙값: 34.523738초
- M-016 기준: 60초 이하
- M-017 Python 추적 메모리 최고값: 194.280592MiB
- M-017 기준: 512MiB 이하
- 측정 5회 모두 exit code 0

이 결과는 로컬 합성 benchmark입니다. 운영환경 성능 보장, 실제 카카오페이증권 운영 시스템 성능, 전체 프로세스 메모리 사용량 보장을 의미하지 않습니다.

## 실행 명령

```bash
python src/skills/openbell-guard/scripts/benchmark_openbell.py --output out/p4-18-benchmark
```

## 측정 환경

- OS: Windows-11-10.0.26200-SP0
- Python: CPython 3.12.4
- machine: AMD64
- processor: AMD64 Family 25 Model 97 Stepping 2, AuthenticAMD
- cpu_count: 32

## 측정 결과

| run | exit code | M-016 seconds | M-017 MiB |
|---:|---:|---:|---:|
| 1 | 0 | 35.045603 | 194.280592 |
| 2 | 0 | 34.523738 | 194.279986 |
| 3 | 0 | 34.545053 | 194.279256 |
| 4 | 0 | 34.453817 | 194.280085 |
| 5 | 0 | 34.360674 | 194.280235 |

## P4-18에서 발견한 병목과 조치

첫 번째 기본 benchmark 시도는 도구 호출 제한 180초를 넘겨 종료되었습니다. 개별 run은 대략 37~40초 범위였으므로 M-016 단일 실행 기준 초과라기보다는, 준비 실행 1회와 측정 실행 5회를 한 번의 호출에서 수행하면서 전체 호출 시간이 길어진 것이 직접 원인이었습니다.

다만 점검 과정에서 더 중요한 개선 지점이 확인되었습니다. 기존 산출물은 `source_locations`에 모든 행 번호를 그대로 저장해, 10개 버킷뿐인데도 `bucket-summary.json`, `metric-summary.json`, `state-summary.json`, `analysis.json`이 수 MB까지 커졌습니다.

이에 따라 `source_locations`를 전체 행 번호 목록이 아니라 파일별 행 범위 요약으로 압축했습니다. 예를 들어 많은 행을 포함하는 aggregate bucket은 `logs.jsonl:L1-L99660`처럼 기록합니다. 지표 계산값과 상태 판정은 바꾸지 않고, 산출물의 근거 위치 표현만 경량화했습니다.

압축 후 대표 출력 크기는 다음과 같이 줄었습니다.

| 파일 | 압축 전 관측 크기 | 압축 후 크기 |
|---|---:|---:|
| `bucket-summary.json` | 4,531,773 bytes | 4,689 bytes |
| `metric-summary.json` | 4,563,393 bytes | 36,309 bytes |
| `state-summary.json` | 2,992,629 bytes | 4,082 bytes |
| `analysis.json` | 2,943,358 bytes | 44,352 bytes |

## 검증 범위

- `benchmark_openbell.py`는 합성 지원 한도 번들을 직접 생성합니다.
- benchmark는 실제 네트워크, 외부 API, 운영 인프라, 실제 고객·계좌 데이터를 사용하지 않습니다.
- M-017은 Python 표준 라이브러리 `tracemalloc` 기준입니다.
- `tracemalloc`은 Python이 추적하는 할당만 포함하며, native memory와 OS 파일 캐시는 포함하지 않습니다.
- 출력 디렉터리 `out/p4-18-benchmark`는 로컬 검증 산출물이며 Git 제출 대상이 아닙니다.

## 남은 한계

- 현재 파이프라인은 지원 한도 안에서는 기준을 통과했지만, 입력 파일을 완전한 streaming 방식으로 끝까지 처리한다고 주장하지 않습니다.
- 정확한 p95·p99 계산을 위해 버킷별 latency 표본을 보관하므로, 훨씬 큰 입력을 지원하려면 근사 백분위수 또는 별도 집계 전략이 필요합니다.
- P4-19에서는 설치·호출·제출 패키징 구조와 README·질문지 정합성을 별도로 검증해야 합니다.
