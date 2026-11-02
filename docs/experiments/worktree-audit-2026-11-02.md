# PR #46와 워크트리 감사

[실험 목록](README.md) · 감사 기준: 2026-11-02

원격 [PR #46](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/pull/46)의 문서 정리 전 head는 `9fc68d3c1639d8af3667e1bc211a55d847cc5453`, 기준 main은 `7f9508a85d44c5369f9461222f9904d6a9c01486`이다. 감사 중 PR #46이 **2026-11-02 06:06:41 UTC에 병합**됐고 main은 `798c11e0772c5bf4c89463b7949234a48be13101`로 갱신됐다. 해당 merge commit의 파일 트리는 확인한 head `9fc68d3`와 동일하다. 이번 문서화·생성물 정리는 이 최신 main 위의 별도 후속 변경으로 관리한다.

## 공통 코드 반영 확인

| 연구·기능 | 현재 반영 위치 | 판단 |
| --- | --- | --- |
| 환경 사전 점검·오류 피드백·상태 조회 | main PR #3 | 이미 통합. |
| prepared-library stat-cache | main PR #33, `src/lean_agent/prepared.py` | 로컬의 미커밋 사본을 새 기능으로 중복 반입하지 않는다. |
| 실제 API·사용량·비용 집계 | main PR #31·#34 | 공통 장부·replay 기반 유지. |
| 예산 제한 API·OpenAI direct·기본 golf·HB profile·v4 지침 | main PR #35 | 기본판 통합. agentkit의 후속 수정은 별도 보존. |
| 행동 선택·후보 계보·실패 부모 수리 | PR #46 `actions.py`, 공통 harness | 비교 실행기 대신 공통 상태·검증·비용 경로를 사용한다. |
| 독립 scout 3개와 merger, 기본 `6+6+6→22` | PR #46 `portfolio.py`와 공통 runner/Final 배치 | 실제 코드·회귀 검사를 확인. 독립 입력을 순차 호출하며 모델 병렬 실행을 뜻하지 않는다. |
| 고정 환율·잔여 비율·교환량·다음 접근 | PR #46 `search_policy.py` | 실제 요청에 연결. 초기 임계값의 일반 성능 우위는 입증하지 않았다. |
| 환경 봉인·평가 캐시·최종 fresh 측정 | PR #46 Final adapters | 현재 의존성이 있으므로 유지. |
| v7 전체 SQLite 상태 머신·영구 실패 기억 | 미커밋 연구 폴더 | 공통 기록·예산 기능과 구별. 전체 v7 구현을 통합했다고 기록하지 않는다. |
| v9 native 타입 조회, v10 LSP/FIFO/소스 구간 golf, v11 검색 | 미커밋 연구 폴더 | 실험 코드와 결과를 보존. PR #46에 전체 기능이 반영됐다는 주장을 하지 않는다. |
| AutoSolver·native recursive repair | PR #39 → #41 → #42 | 아직 후속 연결 대상. `actions-v1.repair` 행동과 구별한다. |
| 팀 MD 스킬·prompt 변경 | PR #44, #30·#36·#38 등 | 별도 PR의 저자·출처·의존성을 유지한다. 이번 정리에서 다른 PR을 병합하지 않았다. |

제외된 과거 통합 묶음은 `3ee67de1707d712321e403da5cf1d064dc4240f9`이며 로컬 `codex/common-harness-cleanup`과 원격 `archive/common-harness-build-3ee67de`에서 복구할 수 있다. 원래 과거 코드 전체를 PR 부모 이력으로 다시 가져오지 않는다. [공통 하네스 문서](../common-harness/README.md)에 실행 계약이 있다.

## 검증

원격의 정리 전 head `9fc68d3`는 Harness CI의 Python 3.10·3.13 검사를 모두 통과했다. 이번 로컬 확인은 중앙 캐시 설정 후 `/usr/bin/python3` **3.9.6**으로 `python3 -B scripts/check_common_harness.py`를 실행했다.

- 15 suite, 총 276개 검사: **271 통과·5 조건부 skip**, 실패 0.
- 후보 격리·평가 장벽·합성 출처·환율 접근·예산 중단·replay·배치 재시작·export 계약을 합성 fixture로 검사했다.
- 이 수치는 새 모델 API 호출·Lean 컴파일·실험 재측정·공식 제출 결과가 아니다. 데이터셋/실환경 opt-in skip은 성공으로 계산하지 않는다.

문서 정리에서 내부 Markdown 링크·39종 목록·추가 파일 확장자와 `git diff --check`를 확인했고, 보존한 Markdown 원문 70개의 SHA256 일치를 검증했다. 새 Lean은 추가하지 않고 자동 생성 focus 파일 15개만 Git에서 제거한다. 보존한 warmup 입력으로 `analyze.py`를 중앙 캐시 경로에 실행해 **15개 전부 기존 Git 파일과 byte 단위로 동일하게 재생성**됨을 확인했다. 모델·Lean 호출은 없다.

## 워크트리별 결정

경로는 `05_pseudolab/` 기준이다. 브랜치 이름과 SHA를 남기며 **브랜치 삭제·강제 worktree 삭제는 하지 않는다**. Git ancestry가 squash merge 때문에 일치하지 않는 경우 PR의 merged 상태·해당 head·현재 코드와 회귀 검사를 함께 확인했다.

| 워크트리 | 보존 브랜치 / 정리 전 HEAD | 반영·보존 근거 | 결정 |
| --- | --- | --- | --- |
| `.worktrees/arena-cloudflare` | `codex/first-harness-baseline` / `843f036` | 동일 head의 PR #21 merged, 공통 하네스 후속 변경 유지 | ignored first-harness 실행 증거 보관 후 워크트리 제거 |
| `.worktrees/arena-environment-checks` | `codex/cache-prepared-environment` / `45f9410` | 동일 head의 PR #33 merged, prepared-cache 회귀 검사 통과 | ignored 환경 검증 기록 보관 후 워크트리 제거 |
| `.worktrees/arena-usage-cost` | `codex/usage-cost-accounting` / `b54afd4` | 후속 `f05c6d6` PR #34에서 집계기를 공통 패키지로 통합, usage 회귀 검사 통과 | ignored 영수증·입력 보관 후 워크트리 제거 |
| `.worktrees/arena-usage-cost-integration` | `codex/usage-cost-main-integration` / `f05c6d6` | 동일 head의 PR #34 merged, 공통 장부·replay 검증 | ignored 입력 보관 후 워크트리 제거 |
| `.worktrees/arena-vercel` | `codex/research-techniques-20261101` / `5fc7bff` | 연구 해석·기법·구조 후속을 이 문서 묶음에 이관. 원래 Lean14개·JSON·도구는 해당 커밋에 유지 | ignored 로컬 배포 설정 보관 후 워크트리 제거 |
| `.worktrees/arena-common-harness-cleanup` | `codex/common-harness-core` / `9fc68d3`; 후속 `codex/experiment-docs-cleanup-20261102` | PR #46 병합 main `798c11e`와 파일 트리 일치, 공통 검사 통과. 문서는 최신 main 기반 별도 브랜치에 보존 | 후속 브랜치 push·원격 head 확인 후 워크트리 제거 |
| `LeanAgent-LeanRefactorArena` | `codex/api-comparison-main-loop` / `9323abd` | 실험 실행기·원시 증거·문서와 미커밋 파일 다수 | 유지. 현재 작업 폴더의 변경을 덮어쓰지 않음 |
| `.worktrees/arena-astra-warmup-93` | `codex/astra-warmup-93` / `456dbc4` | 고유 untracked 실행·평가/slot 도구 3항목 | 유지. 미반영 자료가 있음 |
| `.worktrees/arena-repository-design` | `codex/arena-repository-design` / `0ed5a02` | PR #4 closed/unmerged, untracked README | 유지. 병합됐다는 근거가 없음 |
| `LeanAgent-LeanRefactorArena-agentkit` | `jwkweon/failure-repair` / `7f9508a` | api-runner 전환·진단·문제 입력·tactic probe·전략·skill 등 미커밋 변경 21항목 | 유지. 후속 작업을 PR #46 반영으로 오인하지 않음 |

제거 전 `lsof`의 cwd 목록에서 해당 워크트리를 작업 디렉터리로 연 프로세스가 없는지 확인했다. 무시된 원본 자료와 로컬 설정의 보관 위치는 [보존 기준](retention.md)에 있다. 중앙 빌드·다운로드 캐시는 제거하지 않는다.

## 로컬 보관 검증

앞의 5개 워크트리에서 Git이 무시하던 증거·입력·배포 설정 **313개 파일**을 별도 로컬 보관처로 옮겼고 파일별 SHA256 일치를 확인했다. 원래 브랜치와 중앙 env/cache는 유지했다. 마지막 공통 하네스 작업 워크트리도 후속 문서 브랜치가 원격에 보존된 뒤 제거한다.
