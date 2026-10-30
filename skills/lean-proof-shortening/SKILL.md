---
name: lean-proof-shortening
description: Shorten a Lean Refactor Arena proof (tokens and heartbeats) with the repository's budgeted API runner, local proof golf, and multi-version verification. Use when improving a problem's score; paid API calls still need the user's approval.
---

# Lean 증명 단축 (Arena)

저장소 루트에서 실행한다. 매 셸에서 Python 환경과 `PYTHONPATH=src`를 설정한다.
수치는 모두 로컬 측정이며 공식 점수로 표기하지 않는다.

## 1. 목표와 판단 규칙

- 문제 점수는 `(길이 감소율 + HB 감소율 + 호환성 %) / 3`이다. 지정 버전 하나가 실패하면 약 11.1점이 깎이므로 **호환성이 최우선**이다.
- 후보 비교는 `objective = T/T0 + H/H0`(낮을수록 좋음)로 한다. 토큰 단위로 쓰면 `J = T + H/r`, `r = H0/T0`이다.
  변경은 `ΔT + ΔH/r < 0`일 때만 받아들인다.
- `H/r`가 `T`보다 크면 HB를 줄이는 쪽이, 작으면 길이를 줄이는 쪽이 이득이 크다. 이 판단은 진행 중에 뒤바뀔 수 있다.
  - 예: P08은 `r`이 약 3.4k라서, aesop으로 길이를 줄이면 HB가 커져 손해다.
- 토큰 계산은 `src/lean_agent/evaluator/tokens.py` 기준이다.
  - 식별자(`._'` 포함)는 1토큰, 그 밖의 기호는 문자당 1토큰이다. 공백과 주석은 0이다.
  - `:= => <;> ← ?_`는 각각 1토큰이다.

## 2. 문제 폴더 준비 (기계마다 한 번)

`experiments/problem-inputs/PXX/`에는 원본 증명과 문맥만 있다. Lean 경로가 들어가는 `environment.json`은 각자 만든다.

1. `benchmarks/arena/<snapshot>/benchmark_data_warmup.jsonl`에서 해당 행을 찾는다.
   - `url`, `file_path`, `version_info`(버전→commit)를 확인한다.
   - 버전마다 `https://raw.githubusercontent.com/<owner>/<repo>/<commit>/<file_path>`를 받는다.
2. 그 버전의 프로젝트를 빌드한 디렉터리와 toolchain을 준비한다.
3. 지정 버전마다 아래를 실행한다. 두 번째 버전부터 `--append`를 붙인다.
   ```bash
   python experiments/problem-inputs/make_environment.py --packet experiments/problem-inputs/P02 \
     --source <받은 파일> --project <빌드된 프로젝트(lean-toolchain 포함)> \
     --lean <toolchain>/bin/lean --lean-path <프로젝트 build/lib/lean>:<toolchain>/lib/lean \
     --version v4.26.0 --revision <commit> [--sandbox macos] --output <local>/P02
   ```
4. 원본 증명을 검증해 환경이 맞는지 확인한다. 원본이 실패하면 다음 단계로 가지 않는다.
   ```bash
   python experiments/proof-golf/verify.py --problem-dir <local>/P02 \
     --candidate <local>/P02/original.lean --output <new dir> --t0 222 --h0 2696000
   ```

## 3. 진행 순서

**A. 경로 탐색 (유료 API, 사용자 승인 필요)**

- `experiments/openrouter-budget-trial/run.py`를 `prepare` → `check` → `run` 순서로 실행한다.
  - 기본 프롬프트는 `experiments/prompt-design/p01-p05-reasoning-prompts.v4.en.json`이다.
  ```bash
  python experiments/openrouter-budget-trial/run.py prepare --output runs/<new> --input-root <local> \
    --problems P01 P02 --backend openai --budget-usd 1.5 --dotenv .env
  python experiments/openrouter-budget-trial/run.py check --output runs/<new>   # API 호출 없음
  python experiments/openrouter-budget-trial/run.py run --output runs/<new>     # 유료
  ```
- 안전장치:
  - 호출 전에 로컬 예산을 예약한다. provider 쪽 금액 잠금은 아니다.
  - 자동 재시도는 없다.
  - 응답이 불확실하면(시간 초과 등) 그 뒤의 유료 호출을 모두 멈춘다.
  - 중단하려면 `stop`을 쓴다.
- 결과 파일은 `runs/<new>/PXX/summary.json`과 `best.lean`이다.
  - 이미 끝난 실행 폴더에서 다시 실행하지 않는다.
  - 88점 제출본이나 이전 최선 후보를 API 입력에 넣지 않는다.

**B. 로컬 단축 (API 없음)**

- `golf.py`: 검증된 후보를 씨앗으로 받아 결정적 변형을 J 기준으로 탐욕 탐색한다.
  - 시도하는 변형: 삭제, simp 원소 제거, `$`, `cases`, 불릿 제거, closer 교체.
  - 첫 번째 버전으로 걸러낸 뒤 최종 3회 계측한다.
  ```bash
  python experiments/proof-golf/golf.py --problem-dir <local>/P01 --seed best.lean \
    --output runs/<new> --t0 313 --h0 5175000 [--version v4.26.0] [--resume]
  ```
- `trial.py`: 손으로 쓴 블록 재작성안(`[{label, edits:[[old,new]]}]`)을 한 번씩 측정해 J로 비교한다.
- `goals.py`: 각 tactic 앞의 목표 상태를 출력한다. 블록을 다시 쓰기 전에 확인한다.
- `floor.py`: 길이 하한(2k+3, k는 전역 premise 수)과 남은 여유를 추정한다. 휴리스틱이다.
- `experiments/hb-profile/profile.py`: tactic별 HB를 측정해 HB 핫스팟을 찾는다.

**C. 채택 전 검증 (필수)**

- `verify.py`로 `environment.json`의 **모든 지정 버전**을 검증하고, `compat_pct`가 100인지 확인한다.
- 원본보다 나아지지 않으면 원본이나 기존 제출본을 유지하는 것도 유효한 결과다.

## 4. 기준값 (공식 benchmark)

| 문제 | 정리 | T0 | H0 (raw) | 지정 버전 |
|---|---|---|---|---|
| P01 | `CallElimCorrect.substOldPostSubset` | 313 | 5,175,000 | v4.26.0 |
| P02 | `CallElimCorrect.extractedOldExprInVars` | 222 | 2,696,000 | v4.26.0 |
| P03 | `Core.InitsUpdatesComm` | 224 | 4,251,000 | v4.26.0, v4.27.0, v4.29.1 |
| P04 | `fundamental_theorem_of_variational_calculus'` | 851 | 11,947,000 | v4.32.0 |
| P05 | `Electromagnetism…time_deriv_time_deriv_electricField_of_isExtrema` | 1372 | 26,970,000 | v4.32.0 |

## 5. 알려진 실패 원인

과거 API 실행 7회에서 시도 278개 중 99개가 검증에 실패했다. 다음은 실제로 반복된 원인이다.

- **환경에 없는 tactic**: Strata(P01–P03)에는 Mathlib과 Aesop이 없다.
  - `aesop`, `tauto`, `simp_rw`, `List.disjoint_left`는 쓸 수 없다.
  - `grind`, `omega`, `fun_induction`, `simp`, `decide`는 쓸 수 있다.
  - 확신이 없으면 작은 예제로 먼저 컴파일한다.
- **`case` 태그 위생**: P02에서 `induction`의 태그가 `a.abs._@._hyg.0` 형태로 바뀐다.
  `case abs =>` 대신 `induction h with | abs … => …`를 쓴다.
- **rw 패턴 불일치**: P03 목표의 `updatedStates`는 `updatedStates'`를 감싼 def다.
  rw는 def를 펼치지 않으므로 먼저 펼치거나 `cases … ▸`로 우회한다.
- **실패 반복**: 실행기는 직전 시도의 오류만 모델에 전달한다. 같은 실수가 반복되면 해당 사실을 문맥에 추가해 새 실행을 만든다.
- **측정 래퍼 충돌**: Cslib CCS의 `Name`이 측정 래퍼의 `Name.toString`과 충돌한다.
  `golf.py`와 `verify.py`는 이를 우회하지만, 공통 평가기에는 아직 수정이 들어가지 않았다.
- **한 버전만 검증**: 실행 중 검증은 첫 번째 버전만 한다. 채택 전에는 반드시 C 단계를 거친다.

## 6. 보고

다음을 남긴다.
- 실행 폴더와 사용한 프롬프트 파일
- 비용(확정, 미확정)
- 후보의 T, H, objective
- 검증한 모든 버전과 로컬 문제 점수
- 채택 또는 미채택 사유
