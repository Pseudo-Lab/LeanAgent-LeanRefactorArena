# tactic HB 프로파일링

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

검증된 선언의 블록별 HB를 관측하고 결정적 변형을 고정 목적식으로 수락한다.

## 확인된 결과와 해석

진단 계측은 전체 최종 검증을 대체하지 않는다. 길이 감소와 HB 감소가 충돌할 수 있다.

## 코드·Lean 보존 결정

기본 도구는 PR #35에 반영. 실행 도구는 유지하고 측정 출력은 결과물로 구분한다.

## 보존 근거

아래는 당시 설계·실행 결과의 Markdown 본문이다. 당시의 진행 상태·경로·명령을 보존했으며, 현재 실행 지침이나 새 실행 요청이 아니다. 상충하는 중간 기록은 더 뒤의 완료 보고서와 본문 첫 요약을 우선한다. 결과 이해에 Lean·JSON·그림 열람은 필요하지 않다. 원시 로그를 다시 감사하거나 실행을 재현하려면 별도 원본·고정 환경이 필요하다.

| 원본 | 출처 | 원문 SHA256 |
| --- | --- | --- |
| `experiments/hb-profile/README.md` | `로컬 작업본` | `01e6f04b0bc569948dea576a43060aad866ed7ace88ac276be45941dc0f7ff9f` |

## 원문: `experiments/hb-profile/README.md`

### tactic 단위 heartbeat 프로파일러

한 선언의 증명을 tactic 단위로 쪼개 각 단계의 heartbeat를 측정한다. 공식 측정과 같은 조건
(`Elab.async false`, `elabCommand` 전후 차이, 단위 raw // 1000)에서 **어느 줄이 HB를 먹는지**를
보여주는 분석 도구다. 제출물에는 들어가지 않고, 모델·네트워크를 쓰지 않는다.

#### 동작

1. 선언 파일의 첫 `:= by`(공식 statement 뒤)를 `:= by hb_profile "<nonce>:0"`으로 바꾼다.
2. `src/lean_agent/evaluator/lean.py`의 `WRAPPER`(공식 측정 래퍼) 뒤에 `hb_profile` tactic 정의를 붙여
   준비된 환경(`environment.json`의 `command`·`template`)으로 컴파일한다.
3. `hb_profile`은 tacticSeq의 각 항목을 `IO.getNumHeartbeats`로 감싸 `evalTactic`하고,
   항목 안의 모든 `tacticSeq`(`·` 불릿, `case`, `calc` 단계의 `by`, 항 안의 `by`, `all_goals` 등)를
   재귀적으로 `hb_profile`로 감싼다. 결과는 `HB_PROFILE <nonce> {json}` 로그 줄로 나온다.
4. 계측 없는 일반 컴파일을 한 번 더 해 계측 오버헤드를 보고한다.

출력 표의 `%tot`은 전체 선언 HB 대비 비율, `depth 0`의 합과 전체의 차이가 **residual**
(선언 헤더 elaboration + 최종 항 instantiate + kernel 체크)이다. depth ≥ 1 항목은 부모 항목에 포함된다.

#### 실행

```sh
source /Users/jwkweon/00_work/00_project/env/use.sh 05_pseudolab/LeanAgent-LeanRefactorArena
ARENA_PY=/Users/jwkweon/00_work/00_project/env/05_pseudolab/LeanAgent-LeanRefactorArena/.venv/bin/python
V=runs/warmup-team-results/20261022-verify-01
B=benchmarks/arena/56aa7b8f738d1d6a0a24a55e03cdea1a84007b6c
N=Electromagnetism.ElectromagneticPotential.time_deriv_time_deriv_electricField_of_isExtrema

$ARENA_PY -B experiments/hb-profile/profile.py --env $V/P05/v4.32.0/environment.json \
  --decl $V/P05/v4.32.0/baseline.lean --name $N --benchmark $B --output runs/hb-profile/P05-baseline
```

`--name`은 benchmark의 전체 이름(네임스페이스 포함)이다. P10·P11·P12(ArkLib), P13–P15(Mathlib), P03은
로컬에 준비된 환경이 없다. `.github/workflows/warmup-verification.yml`의 runner에서 같은 스크립트를 돌리거나
환경을 로컬에 준비한 뒤 실행한다.

#### 해석 시 주의

- 한 항목의 HB는 그 tactic의 `evalTactic` 안에서 쓴 양이다. 항 안의 `by`(예 `(hA.of_le (by decide))`)는
  그 항을 elaborate하는 tactic 단계 안에서 실행되므로 부모 항목에 포함되고 depth+1로 따로도 보인다.
- `calc`는 depth 0에서 한 항목이고, 각 단계의 `by` 블록이 depth 1로 나뉜다.
- `t1 <;> t2`, `simp [...] at h ⊢`는 하나의 항목이다. 더 쪼개려면 후보를 수동으로 나눠 다시 잰다.
- 계측 오버헤드(항목당 수 k 미만)는 `instrumentation_overhead_scaled`로 확인한다. 항목 수가 많으면 커진다.
- 측정값은 한 번 실행한 값이다. 공식 비교나 후보 선택에는 기존 평가기(3회 중앙값)를 쓴다.
- 실패하면 `<output>/profiled.log`에 Lean 메시지가 남는다.

#### LLM 없는 후처리 최소화 (`minimize.py`)

검증된 선언 하나를 받아 `score = tok/tok₀ + hb/hb₀`(공식 기준값 사용)가 줄어드는 변경만 수락한다.
`--env`를 여러 번 주면 모든 환경에서 컴파일돼야 수락한다. 패스는 list-min(`… only [a, b]` 항목 제거),
have-drop(`have/let/obtain` 블록 삭제), try-this(`simp`/`simpa`/`simp_all`/`aesop` → `?` 변형의 제안으로 치환),
arg-subst(`(by decide)` 등 → 더 싼 닫기). 수술은 공식 statement 뒤의 증명 본문에만 적용한다.

```sh
$ARENA_PY -B experiments/hb-profile/minimize.py --env $V/P05/v4.32.0/environment.json \
  --decl runs/hb-profile/inputs/P05.lean --name $N --benchmark $B --output runs/hb-profile/P05-min
```

결과: `best.lean`, `summary.json`(입력/최적 지표, 문제 점수 추정, 수락 이력, 컴파일 횟수), `log.txt`, `work/`(모든 시도 소스·로그).

#### 일괄 실행 (`run_all.py`)

```sh
$ARENA_PY -B experiments/hb-profile/run_all.py \
  --submission submissions/warmup/submission.jsonl --output runs/hb-profile/20261028
```

로컬 환경이 있는 문제(P01·P02 strata 4.26, P04–P06 physlib 4.32, P07–P09 cslib)마다 원본·제출본 프로파일 →
제출본 최소화 → 최소화 결과 프로파일을 돌리고 `summary.md`에 표를 남긴다. `--only P05 P06`으로 범위 제한.
문제당 컴파일 수십 회(P05·P06은 100회 이상)이므로 전체는 수 시간 걸릴 수 있다.
