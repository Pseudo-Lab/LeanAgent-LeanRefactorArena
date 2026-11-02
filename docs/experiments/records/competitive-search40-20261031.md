# 원본 출발 portfolio 40회

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

P01–P03에서 scout별 6회, merger 22회로 총 40회를 배정한다.

## 확인된 결과와 해석

120후보와 독립 final 3개. P02는 후반 merger에서 추가 개선. Lean 4.26 primary 결과이며 모든 지정 버전 성공이나 통계적 우위를 뜻하지 않는다.

## 코드·Lean 보존 결정

PR #46 portfolio의 제어 출처. 결과는 아래 보고서로 보존한다.

## 보존 근거

아래는 당시 설계·실행 결과의 Markdown 본문이다. 당시의 진행 상태·경로·명령을 보존했으며, 현재 실행 지침이나 새 실행 요청이 아니다. 상충하는 중간 기록은 더 뒤의 완료 보고서와 본문 첫 요약을 우선한다. 결과 이해에 Lean·JSON·그림 열람은 필요하지 않다. 원시 로그를 다시 감사하거나 실행을 재현하려면 별도 원본·고정 환경이 필요하다.

| 원본 | 출처 | 원문 SHA256 |
| --- | --- | --- |
| `experiments/competitive-search40-20261031/README.md` | `로컬 작업본` | `9394d8e2f58fab35eb62f3a7bb05c9b50d33c44696cffefea1fc0724b10bf8cb` |
| `runs/competitive-search40-20261031/report.md` | `로컬 작업본` | `c6ef0fff38124ccf5cb1faf24439a2c9ad3352658ab374535707442bd98a65b6` |
| `runs/competitive-search40-20261031/analysis.md` | `로컬 작업본` | `a8dee07b65b9c547de5aaaebaf9b381a3bd411c78937c6a011d64a0384aae799` |

## 원문: `experiments/competitive-search40-20261031/README.md`

### Fresh independent forty-attempt portfolio pilot

This directory implements the completed `gpt-6.1-sol` / reasoning `high` portfolio experiment on P01, P02 and P03: forty candidates each, all three final proofs independently verified. Results live in [the run report](competitive-search40-20261031.md), with archived evidence audit (`runs/competitive-search40-20261031/audit.json`, 원래 실행 자료). The archived `experiments/competitive-search-20261031` and its runs remain separate. Every new problem starts from `runs/common-v5-study-inputs-20261030`, without previous best proofs, other runs' solver reports or historical candidate seeding. After all eighteen scout evaluations complete, the fresh merger may read this same run's sealed scout reports; scouts cannot read each other's reports.

Each problem has forty candidate credits: three fresh, sealed scout contexts with six each, followed by a fresh merger with twenty-two. Scout-a derives a goal/types route with the original target proof hidden automatically throughout all six attempts. Scout-b contracts dependencies of the visible original proof. Scout-c seeks a stronger internal property or representation and a bridge to the goal. All eighteen scout evaluations must finish before any merger view or evaluation. Quotas do not transfer; unsupported early stopping marks a scheduled run incomplete rather than authorizing filler or extra golf.

The fixed objective is `O=T/T0+H/H0`, with original normalizers P01 `(313,5173302)`, P02 `(222,2695002)`, P03 `(224,4671681)`. Relative cost is `100*O/O_anchor`. The anchor advances after each four completed evaluations in the visible population: scout-local after4; pooled after4,8,12,16,20,24,28,32,36, retaining36 at forty. Thus the fresh merger starts with the pooled anchor after16. Aspiration50 is never an acceptance gate. Valid strict objective improvement plus fresh independent verification selects the final proof.

Every candidate credit includes unchanged-context plain checking and three heartbeat measurements for a valid proof. Invalid candidates and repairs consume credits. Exact source dedup applies within each scout; identical independent scout discoveries are separately charged. Merger dedup covers all pooled history, including failures. Baseline and full fresh independent final verification are separate from forty candidate credits. The controller permits finalization only after exactly forty completed candidate evaluations with no pending slot: scout6, pooled18 and merger39 are rejected. Unsupported early stopping checkpoints the run as incomplete for the root coordinator; it cannot finalize early. An interrupted measurement retains its reserved immutable source and credit; recovery writes a new evidence label. Source hashes, frozen manifests and a chained reservation/evaluation ledger are checked before resumed operations. Final sources are checked for tampering too.

Compiler scope is **Lean v4.26.0 only**. Preparation selects exactly one unchanged supplied `leanprover/lean4:v4.26.0` environment, freezes both supplied configuration and selected private configuration, and fingerprints that compiler. It does not verify v4.31 or support a cross-version claim. All native fingerprint, baseline, candidate, recovery and final-verification work uses one shared exclusive lock at `runs/competitive-search40-private-20261031/native-slots/0.lock`, across every problem. The controller acquires it only around requested native work and releases it on exceptions. The host schedules at most two active solver contexts; waiting contexts may reason/read only, without idle Lean probes.

Public output is `runs/competitive-search40-20261031/portfolio/P0N`; raw evaluator inputs, selected environments, fingerprints and logs are private at `runs/competitive-search40-private-20261031/portfolio/P0N`. Branch input and feedback views live under each public case's `views/<branch>/`. The host may inspect full state; solvers receive only their assigned view/input and permitted own source paths. This is logical research isolation rather than OS-level access control. Never pass a scout the public root packet, state, original.lean, another scout's paths or private files.

The root coordinator reviewed and froze implementation, prepared the inputs/baselines, dispatched twelve fresh solver contexts, enforced scheduling, and completed the experiment. All 120 candidate credits and three fresh final checks are archived. Twenty-four synthetic controller tests passed before preparation; the completed archive audit passed after execution. There is no automatic launcher, model API client or extra golf step in this directory.

Synthetic validation uses standard-library unittest (no Lean, network, model calls, pytest dependency or test cache; `-B` suppresses bytecode):

```sh
source /Users/jwkweon/00_work/00_project/env/use.sh 05_pseudolab/LeanAgent-LeanRefactorArena
/Users/jwkweon/00_work/00_project/env/05_pseudolab/LeanAgent-LeanRefactorArena/.venv/bin/python -B experiments/competitive-search40-20261031/test_controller.py -v
```

After root review only, the controller CLI supports `prepare --arm portfolio --problem P01 --instruction-file experiments/competitive-search40-20261031/instructions/portfolio.txt`, `status --run-dir <case> --branch scout-a`, `evaluate --run-dir <case> --branch <branch> --candidate <complete.lean> --metadata <metadata.json>`, `recover --run-dir <case>` and `finalize --run-dir <case>`. Use the central environment and explicit Python interpreter above for every invocation. Preparation and evaluation launch Lean; do not run them as a documentation check. A branch is mandatory for every candidate, and only portfolio preparation is accepted. Scout-a redaction does not depend on remembering `--hide-original`.

This is one fresh development pilot per problem: 120 planned candidate evaluations in total. It does not establish statistical superiority, effectiveness on other problems, or competition-wide score improvement. Runtime and memory are recorded operational conditions, not controlled equal-cost comparisons. The contract is in `protocol.json`, `resource-policy.json`, `common.txt` and `arms/portfolio.txt`; `instructions/portfolio.txt` is the exact common-plus-arm prompt supplied to each fresh worker.

Post-run reporting uses `report.py --write`, `audit.py`, and `plot.py` with the central environment above. These consume archived evidence without new Lean or model calls. `analysis.md`, `worker-manifest.json`, `results.json`, `audit.json`, and the two PNG/SVG trajectory pairs are in the run directory. Frozen runtime and experiment inputs were not changed during execution.

## 원문: `runs/competitive-search40-20261031/report.md`

### Fresh40 독립 portfolio 결과

고정 목적값은 O=T/T0+H/H0이며 낮을수록 좋다. 후보 40회와 별도의 원본 기준선·독립 최종 검증을 구분한다.

P01–P03 각 1회, gpt-6.1-sol high의 새 독립 Codex 문맥에서 수행한다. 별도 과금 모델 API 호출은 없다.

전체 완료: True; 후보 평가 120/120; 독립 최종 검증 3/3.

| 문제 | 상태 | 평가 (유효/실패) | T | H | O | 독립 최종 검증 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| P01 (`runs/competitive-search40-20261031/portfolio/P01/final.lean`, 원래 실행 자료) | verified | 40 (26/14) | 29 | 1741204 | 0.429227 | 예 |
| P02 (`runs/competitive-search40-20261031/portfolio/P02/final.lean`, 원래 실행 자료) | verified | 40 (21/19) | 22 | 301702 | 0.211048 | 예 |
| P03 (`runs/competitive-search40-20261031/portfolio/P03/final.lean`, 원래 실행 자료) | verified | 40 (28/12) | 81 | 238714 | 0.412705 | 예 |

running/awaiting_final 행의 수치는 잠정 search best다. baseline_retained는 원본을 유지하며 새 독립 최종 검증이 없다.

| 문제 | 기준선 O | 18회 후 best O | 최종 search best O | scout 감소량 | merge 감소량 | 독립 최종 O |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| P01 | 2.000000 | 0.452077 | 0.429243 | 1.547923 | 0.022835 | 0.429227 |
| P02 | 2.000000 | 0.429540 | 0.211048 | 1.570460 | 0.218492 | 0.211048 |
| P03 | 2.000000 | 0.422207 | 0.412705 | 1.577793 | 0.009502 | 0.412705 |

단계 기여량은 이 시행의 ledger 순서에 따른 목적값 감소량이다. 독립 최종 재측정의 흔들림은 search curve와 분리한다.

| 문제 | 후보 compile 초 | 후보 bundle 초 | 기준선 bundle 초 | 최종 bundle 초 |
| --- | ---: | ---: | ---: | ---: |
| P01 | 1203.632695 | 1390.458836 | 42.718396 | 68.247403 |
| P02 | 1067.560150 | 1307.876697 | 41.033133 | 44.241933 |
| P03 | 406.621822 | 723.188309 | 13.375134 | 13.073818 |

#### Archived12와 fresh40의 사후 비교

독립적인 새 시작이며 배분도 2/2/2/6 → 6/6/6/22로 바뀌었다. 예산만의 통제 비교·인과 비교가 아니다.

| 문제 | prior12 O | fresh40 O | O 변화 | 후보 수 | prior12 bundle 초 | fresh40 bundle 초 |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| P01 | 0.492735 | 0.429227 | -12.89% | 12 → 40 | 658.737244 | 1390.458836 |
| P02 | 0.432723 | 0.211048 | -51.23% | 12 → 40 | 441.112587 | 1307.876697 |
| P03 | 0.422872 | 0.412705 | -2.40% | 12 → 40 | 217.621876 | 723.188309 |

평균 O: prior12 0.449443, fresh40 0.350993.

#### 해석 범위

- Input scope: supplied P01-P03 v4.26.0 contexts only; no cross-version or generalization claim.
- Fresh starts; no old proofs or solver reports seed the new runs.
- One run per problem; no statistical efficacy claim.
- LLM reasoning tokens, billing and total wall time are unmatched and not fully metered.
- Candidate compile/bundle seconds are recorded costs, not causal speed comparisons.
- Allocation changes from 2/2/2/6 to 6/6/6/22; prior12 versus fresh40 is not a controlled budget-only or causal comparison.

#### 시행 해석

P01·P02·P03을 각각 원본에서 새로 시작해 40회씩 평가했다. 이전 12회 시행의 증명은 출발점으로 넘기지 않았다. 각 문제는 새 sol6.1/high 문맥의 독립 scout 세 개에 6회씩, 세 결과가 모두 봉인 해제된 뒤 새 merger에 22회를 배분했다. 첫 scout는 목표·타입에서 시작하며 원본 증명을 숨겼고, 둘째는 원본의 의존성 축약, 셋째는 강한 내부 성질·표현과 외부 목표로의 연결을 탐색했다. 독립은 문맥·입력 분리이며 OS 접근 통제는 아니다.

모든 worker가 현재 보이는 최선·Pareto 후보·최근 유효 후보의 통계·실패 진단을 기준으로 경쟁했다. 상대 목표 50은 탐색을 유도하는 값이며 채택 조건이 아니다. 선택은 고정 O=T/T0+H/H0로 판단했다. 아래 후반 그래프의 100은 18회 후 pooled best이며, 네 번마다 바뀌는 실제 프롬프트 anchor와는 별도의 사후 시각화 기준이다.

| 문제 | 18회 후 best O | 독립 최종 O | 후반 추가 감소 | 원본 정규화값 2 대비 감소 | 최종 선택 시도 |
| --- | ---: | ---: | ---: | ---: | ---: |
| P01 | 0.452077 | 0.429227 | 5.05% | 78.54% | attempt-34 |
| P02 | 0.429540 | 0.211048 | 50.87% | 89.45% | attempt-40 |
| P03 | 0.422207 | 0.412705 | 2.25% | 79.36% | attempt-37 |

P01은 고정된 원소에 대한 함수 귀납과 제한된 정규화가 주력 경로였다. 후반에는 귀납 원리에서 쓰이지 않는 인자를 추론에 맡기고, 타입 클래스 projection을 분기 전에 한 번 정규화해 개선했다. 26회와 34회에서 새 최선이 나왔고 35–40회는 더 좋아지지 않았다. 19토큰 증명도 검증됐지만 HB가 462만으로 올라 최종 29토큰 증명보다 나빴다. 최종 비용의 약 78%가 HB 항이다. P01 근거 (`runs/competitive-search40-20261031/portfolio/P01/solver-report.json`, 원래 실행 자료).

P02는 가장 큰 추가 개선을 보였다. 원본 외부 정리는 유지하면서 내부에서는 정규화 전제가 없는 더 강한 Sublist 성질을 증명했다. 제공된 정의에서 panic 분기가 논리적으로 빈 리스트의 기본값으로 환원되어 이 성질이 성립했다. 추출 함수의 실제 분기를 따라 귀납하고, 넓은 자동 탐색을 가정·nil·append·cons₂의 결정적 구조적 닫기로 바꿨다. 30회 이후 잠시 정체했지만 40회에서 생성자 적용 순서를 조정해 HB 318,465→301,702를 달성했다. 내부 불필요 전제 제거와 탐색 결과의 직접 증명화가 결합된 사례다. P02 근거 (`runs/competitive-search40-20261031/portfolio/P02/solver-report.json`, 원래 실행 자료).

P03은 세 독립 scout가 모두 전체 store update의 교환 법칙을 사용하는 경로로 수렴했다. 독립 출발점이 세 개라는 사실만으로 세 개의 다른 수학적 해법을 얻은 것은 아니다. 후반에는 endpoint 제거·추론 가능한 전제·두 길이 사실의 공유를 결합해 31·32·33·37회에서 개선했다. 길이 조건이 불필요한 더 강한 support 포함 관계도 검증했지만 HB 비용 때문에 탈락했다. 최종 증명은 pool 대비 T86→81, H178,826→238,714로 HB가 늘어도 O는 2.25% 낮아졌다. 최종 비용의 약 88%가 Length 항이어서 HB만 줄이는 경로의 개선 여지가 작다. P03 근거 (`runs/competitive-search40-20261031/portfolio/P03/solver-report.json`, 원래 실행 자료).

이번 시행은 이미 개선된 후보에서 더 줄이는 탐색이 P02에서는 큰 추가 이득으로 이어지고, P01·P03에서는 작은 이득에 그칠 수 있음을 보여준다. 다만 현재 후보군 기반 프롬프트를 끈 대조군이 없으므로 그 프롬프트 자체의 인과 효과로 단정할 수 없다. 이후 설계에서는 T/H 잔여 비중과 마지막 개선 위치를 함께 보고, 같은 증명 계열의 자동화 변형과 실제 다른 내부 명제·표현을 구분해 탐색 폭을 기록하는 것이 유용하다. 이번 40회 예산과 실행 중 선택 규칙은 바꾸지 않았다.

#### 검증·자원 기록

후보는 총 120회, 유효 75개·무효 45개이며 실패와 수정도 예산에 포함했다. 각 유효 후보는 변경하지 않은 문맥의 plain check 및 HB 3회 측정을 거쳤다. 원본 기준선 3개와 독립 최종 검증 3개는 후보 예산과 별도다. 감사는 126개 evidence bundle, 369개 native run의 source/log 해시 쌍, 측정 중앙값·허용 공리·선택 증명·6/6/6/22 예산을 확인했고 모두 통과했다. P01 최종 재측정은 선택 당시보다 82HB 낮았고 P02·P03은 중앙값이 같았다. 컴파일러 검증 범위는 제공된 Lean v4.26.0이다.

활성 solver 문맥은 최대 2개, native Lean 작업은 기준선·fingerprint·후보·최종 검증을 포함해 전역 1개로 제한했다. 종료된 문맥을 반환한 뒤 다음 worker를 시작했다. 관측한 메모리 압력은 정상(1)이었고 swap 사용량은 시작 2,693.75MiB에서 마지막 확인 2,389.75MiB로 감소했다. 이 수치는 시스템 관측값이며 이 실험만의 RSS나 다른 프로세스의 사용량을 뜻하지 않는다. 모델 추론 토큰·과금·전체 wall time을 통제한 비교는 아니다.

감사 결과 (`runs/competitive-search40-20261031/audit.json`, 원래 실행 자료) · 작업자 구성 (`runs/competitive-search40-20261031/worker-manifest.json`, 원래 실행 자료) · 자원 기록 (`runs/competitive-search40-20261031/resource-events.jsonl`, 원래 실행 자료) · 기계 판독 결과 (`runs/competitive-search40-20261031/results.json`, 원래 실행 자료)

원본부터의 전체 탐색 곡선 (과거 그림; 수치는 본문 표 참조)

현재 후보군을 기준으로 한 후반 탐색 (과거 그림; 수치는 본문 표 참조)

## 원문: `runs/competitive-search40-20261031/analysis.md`

#### 시행 해석

P01·P02·P03을 각각 원본에서 새로 시작해 40회씩 평가했다. 이전 12회 시행의 증명은 출발점으로 넘기지 않았다. 각 문제는 새 sol6.1/high 문맥의 독립 scout 세 개에 6회씩, 세 결과가 모두 봉인 해제된 뒤 새 merger에 22회를 배분했다. 첫 scout는 목표·타입에서 시작하며 원본 증명을 숨겼고, 둘째는 원본의 의존성 축약, 셋째는 강한 내부 성질·표현과 외부 목표로의 연결을 탐색했다. 독립은 문맥·입력 분리이며 OS 접근 통제는 아니다.

모든 worker가 현재 보이는 최선·Pareto 후보·최근 유효 후보의 통계·실패 진단을 기준으로 경쟁했다. 상대 목표 50은 탐색을 유도하는 값이며 채택 조건이 아니다. 선택은 고정 O=T/T0+H/H0로 판단했다. 아래 후반 그래프의 100은 18회 후 pooled best이며, 네 번마다 바뀌는 실제 프롬프트 anchor와는 별도의 사후 시각화 기준이다.

| 문제 | 18회 후 best O | 독립 최종 O | 후반 추가 감소 | 원본 정규화값 2 대비 감소 | 최종 선택 시도 |
| --- | ---: | ---: | ---: | ---: | ---: |
| P01 | 0.452077 | 0.429227 | 5.05% | 78.54% | attempt-34 |
| P02 | 0.429540 | 0.211048 | 50.87% | 89.45% | attempt-40 |
| P03 | 0.422207 | 0.412705 | 2.25% | 79.36% | attempt-37 |

P01은 고정된 원소에 대한 함수 귀납과 제한된 정규화가 주력 경로였다. 후반에는 귀납 원리에서 쓰이지 않는 인자를 추론에 맡기고, 타입 클래스 projection을 분기 전에 한 번 정규화해 개선했다. 26회와 34회에서 새 최선이 나왔고 35–40회는 더 좋아지지 않았다. 19토큰 증명도 검증됐지만 HB가 462만으로 올라 최종 29토큰 증명보다 나빴다. 최종 비용의 약 78%가 HB 항이다. P01 근거 (`runs/competitive-search40-20261031/portfolio/P01/solver-report.json`, 원래 실행 자료).

P02는 가장 큰 추가 개선을 보였다. 원본 외부 정리는 유지하면서 내부에서는 정규화 전제가 없는 더 강한 Sublist 성질을 증명했다. 제공된 정의에서 panic 분기가 논리적으로 빈 리스트의 기본값으로 환원되어 이 성질이 성립했다. 추출 함수의 실제 분기를 따라 귀납하고, 넓은 자동 탐색을 가정·nil·append·cons₂의 결정적 구조적 닫기로 바꿨다. 30회 이후 잠시 정체했지만 40회에서 생성자 적용 순서를 조정해 HB 318,465→301,702를 달성했다. 내부 불필요 전제 제거와 탐색 결과의 직접 증명화가 결합된 사례다. P02 근거 (`runs/competitive-search40-20261031/portfolio/P02/solver-report.json`, 원래 실행 자료).

P03은 세 독립 scout가 모두 전체 store update의 교환 법칙을 사용하는 경로로 수렴했다. 독립 출발점이 세 개라는 사실만으로 세 개의 다른 수학적 해법을 얻은 것은 아니다. 후반에는 endpoint 제거·추론 가능한 전제·두 길이 사실의 공유를 결합해 31·32·33·37회에서 개선했다. 길이 조건이 불필요한 더 강한 support 포함 관계도 검증했지만 HB 비용 때문에 탈락했다. 최종 증명은 pool 대비 T86→81, H178,826→238,714로 HB가 늘어도 O는 2.25% 낮아졌다. 최종 비용의 약 88%가 Length 항이어서 HB만 줄이는 경로의 개선 여지가 작다. P03 근거 (`runs/competitive-search40-20261031/portfolio/P03/solver-report.json`, 원래 실행 자료).

이번 시행은 이미 개선된 후보에서 더 줄이는 탐색이 P02에서는 큰 추가 이득으로 이어지고, P01·P03에서는 작은 이득에 그칠 수 있음을 보여준다. 다만 현재 후보군 기반 프롬프트를 끈 대조군이 없으므로 그 프롬프트 자체의 인과 효과로 단정할 수 없다. 이후 설계에서는 T/H 잔여 비중과 마지막 개선 위치를 함께 보고, 같은 증명 계열의 자동화 변형과 실제 다른 내부 명제·표현을 구분해 탐색 폭을 기록하는 것이 유용하다. 이번 40회 예산과 실행 중 선택 규칙은 바꾸지 않았다.

#### 검증·자원 기록

후보는 총 120회, 유효 75개·무효 45개이며 실패와 수정도 예산에 포함했다. 각 유효 후보는 변경하지 않은 문맥의 plain check 및 HB 3회 측정을 거쳤다. 원본 기준선 3개와 독립 최종 검증 3개는 후보 예산과 별도다. 감사는 126개 evidence bundle, 369개 native run의 source/log 해시 쌍, 측정 중앙값·허용 공리·선택 증명·6/6/6/22 예산을 확인했고 모두 통과했다. P01 최종 재측정은 선택 당시보다 82HB 낮았고 P02·P03은 중앙값이 같았다. 컴파일러 검증 범위는 제공된 Lean v4.26.0이다.

활성 solver 문맥은 최대 2개, native Lean 작업은 기준선·fingerprint·후보·최종 검증을 포함해 전역 1개로 제한했다. 종료된 문맥을 반환한 뒤 다음 worker를 시작했다. 관측한 메모리 압력은 정상(1)이었고 swap 사용량은 시작 2,693.75MiB에서 마지막 확인 2,389.75MiB로 감소했다. 이 수치는 시스템 관측값이며 이 실험만의 RSS나 다른 프로세스의 사용량을 뜻하지 않는다. 모델 추론 토큰·과금·전체 wall time을 통제한 비교는 아니다.

감사 결과 (`runs/competitive-search40-20261031/audit.json`, 원래 실행 자료) · 작업자 구성 (`runs/competitive-search40-20261031/worker-manifest.json`, 원래 실행 자료) · 자원 기록 (`runs/competitive-search40-20261031/resource-events.jsonl`, 원래 실행 자료) · 기계 판독 결과 (`runs/competitive-search40-20261031/results.json`, 원래 실행 자료)

원본부터의 전체 탐색 곡선 (과거 그림; 수치는 본문 표 참조)

현재 후보군을 기준으로 한 후반 탐색 (과거 그림; 수치는 본문 표 참조)
