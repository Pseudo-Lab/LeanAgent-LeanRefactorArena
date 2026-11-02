# 공통 하네스 실행 기반

prompt·환경 캐시·탐색 제어·탐색 정책·평가 상태 관리를 먼저 구현·검토하고,
이 기반을 main에 병합한 뒤 기존 AutoSolver·재귀 수리 PR을 연결한다.
기존 실행 기반을 추린 뒤, scout→merger 제어와 환율 피드백·접근 정책을 공통 실행 경로에 연결했다.
main 반영은 `codex/common-harness-core` 기반 PR에서 진행한다.

## 남긴 실행 코드

| 영역 | 위치 | 현재 범위 |
| --- | --- | --- |
| 기본 루프·후보 계보·기록 재생 | `src/lean_agent/` | 기존 비용 보고와 actions-v1을 함께 유지 |
| 넓은 탐색→merger | `src/lean_agent/portfolio.py` | 격리된 세 scout, 평가 할당량 장벽, 전체 후보 합류, 공유 비용/호출 한도 |
| 환율 피드백·접근 선택 | `src/lean_agent/search_policy.py` | 매 요청에 고정 환율·잔여 비율·부모 대비 교환량과 다음 접근 지침 제공 |
| prompt·합성 입력 | `examples/actions/`, `configs/actions-smoke.json` | 공통 행동 지침·작은 고정 응답 fixture·공통 문제 참조 |
| 환경 준비 | `experiments/final-environment/` | 지정 compiler·소스 revision·대상 문맥 준비와 봉인 |
| 평가 캐시·배치 | `experiments/final-batch-next/` | 대표 버전 탐색, 최종 호환성, 캐시를 쓰지 않는 최종 측정 |
| 입력 점검·고정 환경 | `benchmarks/arena/final-d53690b057f9/`, `configs/final-environments.lock.json` | snapshot·검사 생성기·환경 pin |

`actions-v1`의 `repair`는 실패 proof 편집 행동이다. 지연님 PR #39·#41·#42의 native 목표 추출·
AutoSolver·재귀 수리는 이 정리에 포함하지 않으며 기존 PR에서 후속 연결한다.
소미님 PR #44의 MD 스킬·도구 참고와 기존 prompt PR도 저자·출처를 유지해 반영한다.

## 공통 탐색 설정과 데이터 흐름

`actions-v1` 설정에 다음을 추가한다. 기존 설정은 단일 문맥 동작을 유지한다.

```json
{
  "mode": "actions-v1",
  "corpus": "action-corpus.json",
  "portfolio": {"scout_evaluations": 6, "merger_evaluations": 22},
  "approach_policy": "exchange-v1"
}
```

`portfolio`가 있으면 접근 정책도 활성화한다. portfolio 없이 `approach_policy`만 켤 수도 있다.
공통 `lean-agent run`과 Final 배치가 같은 `make_request → prepare_response → advance`를 사용한다.

1. scout-a는 명제·정의에서 경로를 구성하고, scout-b는 원본의 의존·반복을 줄이며,
   scout-c는 합성 가능한 성질·표현과 목표로의 연결을 탐색한다.
2. scout는 원본 baseline과 자기 후보·이력만 볼 수 있다. 다른 scout 후보를 부모·읽기·
   합성 출처로 지정하면 거절한다. scout-a에서는 기본적으로 원본 proof 읽기도 차단한다.
   `hide_original_first_scout: false`로 원본 공개를 선택할 수 있다. 공유 prompt/corpus에
   원본 전체 선언이 그대로 들어 있으면 숨김 모드 설정을 거절한다. 이는 모델 입력 범위 제어다.
3. 각 scout가 6개씩 평가된 뒤 merger를 연다. 유효·무효 proof 모두 할당량을 사용한다.
   검색·읽기·잘못된 응답·같은 문맥의 중복 proof는 모델 호출/비용을 사용하지만 평가 수를 늘리지 않는다.
4. merger는 전체 후보·실패·scout별 best ID와 Pareto 후보를 받아 실제 proof를 제안하고 평가받는다.
   `propose.source_candidate_ids`로 여러 후보의 합성 출처를 기록한다. 출처 기록은 검증을 대체하지 않는다.
5. merger의 기본 22회 평가가 끝나면 `portfolio_complete`로 종료한다. 전역 비용·호출·문맥 한도는
   항상 우선 적용하며, 먼저 중단되면 검증 best와 최종 검사 결과를 보존하고 `status: stopped`로 표시한다.

실행은 **독립된 모델 입력을 순차 호출**한다. 병렬 scout나 별도 provider·evaluator·예산 루프를 만들지 않는다.
세 scout와 merger의 평가 기본 합계는 40회이며 도구 호출만큼 모델 호출 수가 더 필요하다.
`finish`로 할당량을 건너뛸 수 없다. 최종 선택은 모든 유효 후보의 기존 고정 순위를 따른다.

환율은 원본의 실제 측정값에서 `r = H0/T0`로 고정한다. 매 요청의 `approach_policy`에는
정확한 유리수 환율, `T/T0`·`H/H0`, 유효한 직전 후보와 부모의 `ΔT + ΔH/r`, Pareto 후보,
최근 구조 부모와 다음 접근 지침을 넣는다. objective 동률은 토큰 수·선언 SHA256 순으로 정한다.

접근 선택은 실패 시 오류/연결 재검토, scout 초반 2회 넓은 탐색, merger 첫 회 합성,
남은 평가/호출 2회 이하 정리, 엄격한 objective 개선 없이 3회 평가 시 접근 재고,
그 외 잔여 비율이 큰 length 또는 HB 축 개선 순이다. 이 임계값은 초기 정책이며 성능 최적성을 주장하지 않는다.
정책은 모델에 보낼 다음 지침을 선택하며 모델의 지침 이행이나 개선 성공을 보장하지 않는다.
환율을 측정 노이즈로 해석하거나 과거 `r/4` 노이즈 규칙을 옮기지 않는다.

입력·상태·평가·비용과 함께 이 정책 코드도 동결한다. 공통 runner의 offline replay는
역할별 요청, 합류 장벽, 후보 소유와 합성 출처, 평가 수와 최종 선택을 재구성한다.
Final 배치는 기존 체크포인트를 사용하고 보고서에서 요청·평가 기록으로 역할별 할당량을 재집계한다.

작은 고정 응답 예시는 `configs/portfolio-smoke.json`이다. 아래 실행은 API를 쓰지 않지만 실제 Lean은 필요하다.

```sh
PYTHONPATH=src python3 -B -m lean_agent run --config configs/portfolio-smoke.json --output runs/portfolio-smoke
PYTHONPATH=src python3 -B -m lean_agent replay runs/portfolio-smoke
```

출처는 원본 `3ee67de`의 `competitive-search40-20261031/controller.py`(세 scout·합류),
`competitive-structure-20261101/controller.py`(환율 feedback), v4 prompt(축별 접근),
과거 `cost-hypothesis-pipeline/policy.py`(잔여 비율·구조 부모·Pareto)다.
대형 후보/실험 결과나 구형 실행기를 가져오지 않고 공통 상태 계약으로 옮겼다.

## 이번에 제외한 것

- `portfolio-94`의 대량 후보·문제별 adapter·공식 앱 사본·제출 당시 기록.
- 첫 하네스·prompt/feedback ablation의 중복 원본·문맥·결과와 구형 실행기 복사본.
- feedback-summary, offline-proof-search, length-bounds의 과거 연구 묶음.
- `final-batch-next`와 겹치는 이전 `final-batch` 실행기.
- 실험 결과 JSON·검증 결과 snapshot·대형 파일별 반입 manifest.
- 비용 가설 연구의 과거 코호트 준비기·복구 패치·수동 worker·보고서.
- 공통 정책으로 옮긴 뒤 호출하지 않는 `cost-hypothesis-pipeline` 정책·비교 prompt·전용 검사.
- P02 유료 비교 실행기와 비교 전용 transport, 고정 응답 A/B 실행 wrapper·baseline 복사본.
- 배치의 `preflight`·평가 캐시와 겹치는 `cache_rows.py` 보조 실행기.

필요한 합성 fixture는 `examples/actions`, 설정은 `configs`, 공통 검사는 `tests`에 둔다.
공통 테스트는 제거한 실험 실행기를 import하지 않는다. 예산 검사는 공통 예약·미확정 비용 중단·
기록 재생을, 배치 검사는 현재 장부와 재시작을 확인한다. 제외한 비교 전용 transport의 검사도 함께 제외했다.
이번 브랜치에서 새로 추가하는 실험 실행 코드는 실제 의존성이 있는 환경 준비와 Final 배치 adapter만 남긴다.
기존 main의 다른 연구 실험은 이번 반입 범위에 포함하지 않는다. 생성 결과는 `.gitignore`에서 제외한다.
원본 데이터·API 키·로컬 빌드·실험 runs를 이 브랜치에 복사하지 않는다.

## 복구와 출처

제외한 파일은 원본 커밋 `3ee67de1707d712321e403da5cf1d064dc4240f9`에서 복원할 수 있다.
직전 통합 시점의 작은 실험 fixture·정책·스크립트는 `6cd8ba7`에도 보존되어 있다.
로컬 `codex/common-harness-cleanup`과 원격 `archive/common-harness-build-3ee67de`가 이 원본을 가리킨다.
PR #46의 `feat/common-harness-build`는 정리된 공통 하네스로 갱신했다.
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

1. 완료: 업로드 대상 정리와 기존 실행 코드·fixture 의존성 확인.
2. 기반 PR: prompt·환경 캐시·탐색 제어·탐색 정책·평가/상태의 공통 계약을 구현하고 검사.
   scout→merger·환율 피드백·접근 선택은 연결했고, 기존 prompt·스킬 PR의 남은 반영 범위를 명시한다.
3. 기반 PR을 main에 병합한 뒤 관련 작업 브랜치의 기준을 갱신한다.
4. 기존 PR #39 → #41 → #42의 의존관계를 유지하며 AutoSolver·native repair를 공통 계약에 연결한다.
   중복된 provider·예산·evaluator를 새로 만들지 않는다.

이번 단계에서 다른 사람의 PR을 병합·수정하거나 유료 실험을 실행하지 않는다.
