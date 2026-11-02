# 공통 하네스 실행 기반

prompt·환경 캐시·탐색 제어·탐색 정책·평가 상태 관리를 먼저 구현·검토하고,
이 기반을 main에 병합한 뒤 기존 AutoSolver·재귀 수리 PR을 연결한다.
현재 정리는 기존 실행 기반을 추리는 단계이며 다섯 기능의 새 통합 구현 완료를 뜻하지 않는다.

## 남긴 실행 코드

| 영역 | 위치 | 현재 범위 |
| --- | --- | --- |
| 기본 루프·후보 계보·기록 재생 | `src/lean_agent/` | 기존 비용 보고와 actions-v1을 함께 유지 |
| prompt·합성 입력 | `experiments/action-candidate-memory/` | 작은 고정 응답 fixture·공통 문제 참조 |
| 부모·Pareto·탐색 단계 정책 | `experiments/cost-hypothesis-pipeline/` | 순수 정책·지침·회귀 검사. 구형 harness 복사본에 의존하지 않음 |
| 환경 준비 | `experiments/final-environment/` | 지정 compiler·소스 revision·대상 문맥 준비와 봉인 |
| 평가 캐시·배치 | `experiments/final-batch-next/` | 대표 버전 탐색, 최종 호환성, 캐시를 쓰지 않는 최종 측정 |
| 입력 점검·고정 환경 | `benchmarks/arena/final-d53690b057f9/`, `configs/final-environments.lock.json` | snapshot·검사 생성기·환경 pin |

`actions-v1`의 `repair`는 실패 proof 편집 행동이다. 지연님 PR #39·#41·#42의 native 목표 추출·
AutoSolver·재귀 수리는 이 정리에 포함하지 않으며 기존 PR에서 후속 연결한다.
소미님 PR #44의 MD 스킬·도구 참고와 기존 prompt PR도 저자·출처를 유지해 반영한다.

## 이번에 제외한 것

- `portfolio-94`의 대량 후보·문제별 adapter·공식 앱 사본·제출 당시 기록.
- 첫 하네스·prompt/feedback ablation의 중복 원본·문맥·결과와 구형 실행기 복사본.
- feedback-summary, offline-proof-search, length-bounds의 과거 연구 묶음.
- `final-batch-next`와 겹치는 이전 `final-batch` 실행기.
- 실험 결과 JSON·검증 결과 snapshot·대형 파일별 반입 manifest.
- 비용 가설 연구의 과거 코호트 준비기·복구 패치·수동 worker·보고서.

필요한 합성 fixture와 회귀 검사는 유지한다. 생성 결과는 `.gitignore`에서 제외한다.
원본 데이터·API 키·로컬 빌드·실험 runs를 이 브랜치에 복사하지 않는다.

## 복구와 출처

제외한 파일은 원본 커밋 `3ee67de1707d712321e403da5cf1d064dc4240f9`에서 복원할 수 있다.
로컬 `codex/common-harness-cleanup`과 원격 `feat/common-harness-build`가 이 원본을 가리킨다.
새 `codex/common-harness-core` 브랜치는 main `7f9508a`에서 시작했으므로,
과거 자료가 들어간 대형 커밋을 PR의 부모 이력에 추가하지 않는다.

```sh
git show 3ee67de:experiments/portfolio-94/submission-round/README.ko.md
```

원래 작업 폴더의 미커밋 연구·실험 증거는 변경하지 않았다.
동결한 이전 실행은 그 실행의 보존된 코드로 재생한다.

## 검사

공통 환경 설정 후 실행한다. 모델/API 호출이나 Lean 컴파일 없이 합성 fixture로 검사한다.
동명 실험 모듈은 별도 프로세스에서 실행한다.

```sh
python3 -B scripts/check_common_harness.py
```

원본 dataset과 준비된 환경이 있는 경우의 opt-in 검사는 각 실행기 문서를 따른다.
원본 없이 skip한 통합 검사를 새 Lean 검증 성공으로 보고하지 않는다.

## PR 반영 순서

1. 현재 단계: 업로드 대상 정리와 기존 실행 코드·fixture 의존성 확인.
2. 기반 PR: prompt·환경 캐시·탐색 제어·탐색 정책·평가/상태의 공통 계약을 구현하고 검사.
   기존 prompt·스킬 PR에서 가져온 범위와 남은 범위를 명시한다.
3. 기반 PR을 main에 병합한 뒤 관련 작업 브랜치의 기준을 갱신한다.
4. 기존 PR #39 → #41 → #42의 의존관계를 유지하며 AutoSolver·native repair를 공통 계약에 연결한다.
   중복된 provider·예산·evaluator를 새로 만들지 않는다.

이번 단계에서 다른 사람의 PR을 병합·수정하거나 유료 실험을 실행하지 않는다.
