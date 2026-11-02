# 공통하네스 구축

로컬 작업 사본에 나뉘어 있던 행동 선택·후보 계보, 오류 피드백 연구,
최종 60문제 환경·배치·검증 캐시, 비용 가설·로컬 탐색 도구를 한 브랜치에 모았다.
기준은 main `7f9508a85d44c5369f9461222f9904d6a9c01486`이며, main의
사용량·비용 집계, prepared 환경 검증과 stat cache, agent kit를 보존한다.

## 공통 실행과 실험의 관계

| 영역 | 위치 | 역할 |
| --- | --- | --- |
| 기본 실행·후보 선택·기록 재생 | `src/lean_agent/harness.py` | 기존 기본 모드와 `actions-v1`을 함께 지원 |
| 행동·후보 기억 | `src/lean_agent/actions.py` | 탐색·조회·제안·수리와 후보 계보 유지 |
| 예산·오류 피드백 | `budgeting.py`, `diagnostics.py` | 요청 비용 예약과 수리 위치·진단 연결 |
| 구조화/요약 피드백 비교 | `experiments/feedback-summary-20261025/` | 과거 실험 코드와 작은 검증 근거 보존 |
| 비용 가설·부모 선택 | `experiments/cost-hypothesis-pipeline/` | 후보 계보·Pareto·결정적 재생 연구 |
| 로컬 증명 탐색 | `experiments/offline-proof-search/`, `portfolio-94/` | 변형·검색·호환성·자원 제한 연구 |
| 최종 환경 준비 | `experiments/final-environment/` | 8개 Lean 버전·17개 환경·127개 문제/버전 조합 고정 |
| 최종 배치 | `experiments/final-batch/` | 기본 버전 탐색, 개선 후보의 호환성 피드백, 비용 장부 |
| 다음 배치 정책 | `experiments/final-batch-next/` | 평가 캐시와 최종 호환성 검사, fresh 최종 측정 |

이 통합은 실험 코드를 전부 하나의 범용 서비스로 재작성한 것이 아니다.
공통 패키지에 들어간 행동·예산·진단과, 별도 실행 정책을 유지하는 실험을 구분한다.
특히 `portfolio-94`의 역사적 adapter는 당시 `insights-*` 경로·원본 자료·prepared
manifest를 요구한다. 해당 runtime은 clone에 포함되지 않으며 경로와 pin을 확인해
준비해야 한다. 원본 full-context 검사나 공리 검사를 생략해 실행하지 않는다.

## 통합한 원본

- action-memory: `7f05453`, `30f0b1b`, `183ddf4`, `12d6cf3`.
- 피드백 연구: `exp/feedback-followup-20261025`의 `709bda1`까지. 선행
  `first-harness-jwkweon` 실험은 후속 실험의 import·재현 의존성 때문에 함께 보존한다.
- 미커밋 final-environment/final-batch/final-batch-next/length-bounds 및
  cost-hypothesis/offline-proof-search/portfolio-94 코드와 작은 증거 파일.
- [가져온 파일 명세](import-manifest.json)는 통합 수정 **전**의 원본 SHA-256이다.
  과거 결과 JSON·후보·snapshot의 해시는 당시 실행에 대한 기록이며 이번 코드의
  검증 결과로 다시 표시하지 않는다.

## 충돌과 동작 차이의 해결

- `.gitignore`는 최신 main의 credential·prepared 환경 제외 규칙과 두 실험
  브랜치의 raw runtime 제외 규칙을 모두 보존했다.
- action-memory의 `harness.py` 변경은 3-way로 합쳐 main의 비용 보고 기능을 유지했다.
- final-batch-next에는 final-batch의 후속 비공개 선언 판별과 명시적 Lean allocator
  한도 진단을 가져왔다. 캐시·재시작 receipt·최종 fresh 측정 정책은 유지한다.
- 단위 테스트의 로컬 registry/문제 파일 의존성을 임시 fixture로 바꿨다.
  60문제 dataset 및 127개 환경을 직접 검사하는 테스트는 별도로 구분한다.
- 과거 proof·후보·근거의 바이트와 해시를 보존하기 위해 해당 경로의 줄바꿈
  정규화와 trailing-whitespace 판정을 `.gitattributes`에서 제한했다.

## 검증

저장소 루트에서 공통 오프라인 검사를 실행한다. Python 3.10 이상이며
모델/API 호출이나 Lean 컴파일은 하지 않는다.

```sh
python3 -B scripts/check_common_harness.py
```

테스트는 실험별 별도 프로세스에서 실행되어 `report`, `worker`, `evaluator` 같은
동명 모듈이 서로 섞이지 않는다. 데이터 없이도 실행되며 dataset 검사는
고정 원본이 설치됐을 때 수행한다. CI는 Python 3.10/3.13에서 같은 명령을 실행한다.

실제 환경 준비는 [최종 환경 안내](../../experiments/final-environment/README.md)를
따른다. 이 준비 도구는 Python 3.12 이상과 고정 소스·compiler를 요구한다.
dataset 원본은 `benchmarks/arena/final-d53690b057f9/snapshot.json`의 hash로
확인해 같은 디렉터리에 설치한다. 코드·pin·점검 명세만 Git에 포함한다.

준비한 환경의 메타데이터·문맥·setup 127개 조합을 검사하려면 다음을 실행한다.
이 검사는 기존 파일을 읽으며 새 Lean/HB 측정을 수행하지 않는다.

```sh
ARENA_FINAL_INTEGRATION=1 PYTHONPATH=src python3 -B -m unittest discover \
  -s experiments/final-batch-next -p test_evaluator.py -v
```

## 실행 기록 보존

기존 실행의 frozen code·ledger·후보·manifest를 이 통합본으로 덮어쓰지 않는다.
새 정책은 새 run root에서 시작한다. 특히 final-batch-next는 다른 verification policy의
실행 재사용을 거절하며, 캐시 성공만으로 전체 버전 호환성을 선언하지 않는다.
최종 선택은 모든 지정 버전을 확인하고 기본 버전에서 캐시 없이 다시 측정한다.

원본 작업 사본, 과거 코드 해시와 원시 로그는 그대로 두었다. 이번 통합에서 새로운
유료 실험·HB 측정·공식 제출을 수행하지 않았다. 기존 GitHub 검증·수리 PR 등
다른 연구 브랜치는 이 변경에 임의로 병합하지 않았다.
