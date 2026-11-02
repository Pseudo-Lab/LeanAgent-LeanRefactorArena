# 행동 선택과 후보 기억 fixture

`actions-v1`의 검색·조회·제안·부모 추적·실패 후보 편집·종료를 확인하는 작은 합성 입력이다.
공통 `examples/first-harness`의 문제·문맥을 사용한다.

- `smoke.json`, `corpus.json`, `responses.json`, `prompt.txt`: 행동 모드의 고정 응답 입력.
- `baseline.json`, `baseline-responses.json`: 기존 proof 응답 모드의 비교 입력.
- `run_smoke.py`: 고정 응답과 로컬 Lean 환경을 사용하는 선택적 실행 도구.
- `live_p02.py`: 호출 전 예약·endpoint 단가·미확정 비용 차단 검사의 기존 transport.
  `tests/test_budgeting.py`가 이 계약을 검사하므로 유지하며 이번 정리에서 실행하지 않는다.

오프라인 계약 검사는 `tests/test_actions.py`에서 fake evaluator로 실행한다.
`run_smoke.py`는 API를 호출하지 않지만 실제 Lean이 필요하다.

과거 P02 실험·측정 JSON·후보 proof는 원본 커밋 `3ee67de`에 보존하고 여기에는 포함하지 않는다.
이 fixture의 `repair` 행동은 실패 proof를 다시 작성하는 모델 행동이며,
PR #41의 native AutoSolver·재귀 수리는 후속 통합 대상이다.
