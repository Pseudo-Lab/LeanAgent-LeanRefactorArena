# fresh40 추가 네 문제

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

P06·P13·P14·P15를 원본에서 독립 탐색하며 6/6/6→22 평가 장벽을 유지한다.

## 확인된 결과와 해석

160/160후보, 118유효·42실패, 독립 final 4개. 네 문제 모두 pool18 이후 개선. P06 4.32, 나머지 4.26; Putnam 축소 import·추가 버전 미검증이다.

## 코드·Lean 보존 결정

평가 수·독립 final·복구 원칙을 참고하고 후보 사본은 새 PR에 추가하지 않는다.

## 보존 근거

아래는 당시 설계·실행 결과의 Markdown 본문이다. 당시의 진행 상태·경로·명령을 보존했으며, 현재 실행 지침이나 새 실행 요청이 아니다. 상충하는 중간 기록은 더 뒤의 완료 보고서와 본문 첫 요약을 우선한다. 결과 이해에 Lean·JSON·그림 열람은 필요하지 않다. 원시 로그를 다시 감사하거나 실행을 재현하려면 별도 원본·고정 환경이 필요하다.

| 원본 | 출처 | 원문 SHA256 |
| --- | --- | --- |
| `experiments/competitive-search40-extra-20261101/README.md` | `로컬 작업본` | `3f593bd0fd5bc22f08c3db70dffc3ce48bb2e86655a3cd29a6681fcd4eb78334` |
| `runs/competitive-search40-extra-20261101/report.md` | `로컬 작업본` | `55ce7b30164bd943619606dd1d8f3d3c7f7b630d2635dd3c84c8faa4deea5338` |
| `runs/competitive-search40-extra-20261101/analysis.md` | `로컬 작업본` | `e4260274601f2d7a80dc28ced735853d5dd5a1fbe6b8234d6cc2d45792a47f3b` |
| `runs/competitive-search40-extra-20261101/comparison-88.md` | `로컬 작업본` | `51bd441a44dbe8b860e4ba2375fdbee2f8c0aa909a07375b633855b32a3c0f17` |
| `runs/competitive-search40-extra-20261101/audit-review.md` | `로컬 작업본` | `cfde26ddb904ef1f7ed99b17c3f58dc0b39f44328ba87eb6be76f3193453e518` |

## 원문: `experiments/competitive-search40-extra-20261101/README.md`

### Fresh independent four-case forty-attempt portfolio trial

This new experiment covers P06, P13, P14 and P15 independently, with `gpt-6.1-sol` and reasoning `high`. It has 160 planned candidate evaluations. Earlier experiment sources and run evidence remain immutable and do not seed workers or prompts. Each case has one fresh trial; results cannot establish statistical superiority or generalization. The host enforces at most two active solver contexts. There is no model API client or model token budget control.

Each case allocates six credits to each of three fresh sealed scouts, then twenty-two to a fresh merger. All eighteen scout evaluation bundles must complete before a merger view, evaluation or report access. Scout-a automatically hides the original target proof throughout all six attempts, including frontier/champion entries; scouts see only their own full population and failure evidence. Scout-b contracts dependencies; scout-c seeks a stronger internal property and bridge. All roles use the common prompt without case-specific solution hints. The merger sees only this case's own completed scout pool and permitted same-run reports. Logical isolation is host-managed, not an OS access-control guarantee.

Ranking uses exact fixed `O=T/T0+H/H0`. Before protocol freeze and any solver, the root calibrates each unchanged supplied original in the exact chosen local environment: lexical proof tokens and median of three raw heartbeat measurements. These original-only calibration bundles are outside the 160 candidate credits and separate from the fresh prepare baseline. The calibration manifest, evidence files and hashes freeze alongside the protocol. Published benchmark proof lengths and scaled heartbeat numbers are reference only; they are never silently converted into raw local normalizers. No candidate-derived normalization is permitted.

Epoch anchors change only the display scale: each scout uses its own clock after four evaluations. The merger uses the complete pooled ledger, begins with its anchor after sixteen, advances at 20/24/28/32/36 and retains the anchor after36 at forty. Relative cost50 is an aspiration, never admission, selection or stopping policy. Fixed O determines the champion. Exact source dedup is own-scout local, then pooled across all history for the merger; independent sealed duplicate discoveries are separately charged.

P06 uses the exact supplied `v4.32.0` environment; P13/P14/P15 use exact supplied `v4.26.0`. The controller matches both environment ID and toolchain and rejects missing, conflicting or multiple matches. All supplied statements, imports, options, context and allowed axioms remain unchanged. Actual local supplied imports are shown in permitted input context; original benchmark headers and additional required versions are reference scope only. No verification of other benchmark versions is claimed.

Every requested native phase shares one exclusive flock at `runs/competitive-search40-extra-private-20261101/native-slots/0.lock`: original calibration, fingerprint, baseline, candidate bundle, recovery and independent final check across all four cases. No idle native probes are permitted. Only the controller compiles after calibration; workers never invoke Lean themselves. The static policy is in `resource-policy.json`.

Public runs are `runs/competitive-search40-extra-20261101/portfolio/<case>`; raw evaluator evidence is private under `runs/competitive-search40-extra-private-20261101`. Original-only supplied inputs and manifests are in `runs/competitive-search40-extra-inputs-20261101`. Every case freezes its controller, exact common-plus-arm prompt, protocol, static resource policy, inputs/manifests/calibration evidence, selected and supplied compiler configuration, runtime evaluator files and compiler fingerprint before its solver starts.

Invalid candidates and repairs consume credits. Each valid bundle is one unchanged-context plain check and three heartbeat measurements. Interrupted measurement reserves the same immutable source/credit and recovery gets a new evidence label. Quotas do not transfer. Unsupported early stopping marks the scheduled case incomplete for the root; no fillers, post-budget golf or budget expansion are authorized. Finalization requires exactly forty completed candidates and no pending evaluation. Strict improvement requires a fresh independent final bundle. An improved verified case has 42 committed evidence bundles (baseline + 40 candidates + final); a baseline-retained case has41 and no fresh final. Calibration, recovery and unsuccessful final retries are separately reported evidence, never extra candidate credits.

Synthetic checks use only Python standard-library unittest, temporary files and fake evaluators. They do not invoke Lean, models or network. Use the central interpreter with `-B`:

```sh
source /Users/jwkweon/00_work/00_project/env/use.sh 05_pseudolab/LeanAgent-LeanRefactorArena
/Users/jwkweon/00_work/00_project/env/05_pseudolab/LeanAgent-LeanRefactorArena/.venv/bin/python -B experiments/competitive-search40-extra-20261101/test_controller.py -v
```

After the root reviews the final frozen configuration and synthetic results, `controller.py prepare --arm portfolio --problem P06 --instruction-file experiments/competitive-search40-extra-20261101/instructions/portfolio.txt` performs native preparation. Do not use preparation as a documentation check. Other commands are `status`, `evaluate`, `recover`, `finalize`, always with `--run-dir`; every evaluation needs an explicit branch. Solvers receive only their assigned `views/<branch>/input.json`, competition packet and permitted own paths. Never hand scouts public-root state/original or private evaluator paths.

`report.py` is read-only by default; `--write` writes only the new public results/report. `audit.py --allow-incomplete` is an offline readiness check and does not promote partial runs to final success; the default audit requires four complete cases. `plot.py` is read-only by default; `--write` renders measured fixed-O trajectories and evaluation18→40 pool-relative trajectories. Final dots represent measured independent final checks only. Reporting never reads archived runs or pretends these cases have matching prior12 results. All reporting/audit steps avoid Lean and model calls.

#### Completed run

Completed P06/P13/P14/P15: 160/160 candidate evaluations (118 valid,42 invalid), four fresh independent finals. All cases preserve6/6/6/22 quotas. Default offline audit passed172 committed bundles including calibration and562 source/log pairs. Two interrupted measurement starts recovered the same immutable candidate credits; P15 resumed its existing merger context at38/40 after a model usage-limit interruption. No post-budget candidate work.

Results, analysis, worker provenance, resource/recovery events, audit and measured PNG/SVG plots are under `runs/competitive-search40-extra-20261101/`. Exact local primary compiler scope remains as described above; no official full-header or cross-version claim.

## 원문: `runs/competitive-search40-extra-20261101/report.md`

### Fresh40 독립 portfolio 결과

고정 목적값은 O=T/T0+H/H0이며 낮을수록 좋다. 후보 40회와 별도의 원본 기준선·독립 최종 검증을 구분한다.

P06/P13/P14/P15 각 1회, gpt-6.1-sol high의 새 독립 Codex 문맥에서 수행한다. 별도 과금 모델 API 호출은 없다.

전체 완료: True; 후보 평가 160/160; 독립 최종 검증 4/4.

원본만 측정한 calibration 4 bundles는 후보 credit 0이며, main baseline 4·후보 160·독립 final 최대 4와 별도로 보관한다. 전부 개선·검증된 경우 main 168 + calibration 4 = 172 bundles다.

P13/P14/P15는 공급된 local imports/opens/options의 축소된 문맥을 그대로 사용한다. 전체 benchmark header는 reference-only이며 이 시행에서 검증하지 않는다.

| 문제 | 상태 | 평가 (유효/실패) | T | H | O | 독립 최종 검증 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| P06 (`runs/competitive-search40-extra-20261101/portfolio/P06/final.lean`, 원래 실행 자료) | verified | 40 (25/15) | 418 | 22877043 | 0.887787 | 예 |
| P13 (`runs/competitive-search40-extra-20261101/portfolio/P13/final.lean`, 원래 실행 자료) | verified | 40 (30/10) | 235 | 3012079 | 0.183411 | 예 |
| P14 (`runs/competitive-search40-extra-20261101/portfolio/P14/final.lean`, 원래 실행 자료) | verified | 40 (30/10) | 126 | 1071111 | 0.084905 | 예 |
| P15 (`runs/competitive-search40-extra-20261101/portfolio/P15/final.lean`, 원래 실행 자료) | verified | 40 (33/7) | 244 | 1366707 | 0.172029 | 예 |

running/awaiting_final 행의 수치는 잠정 search best다. baseline_retained는 원본을 유지하며 새 독립 최종 검증이 없다.

| 문제 | 기준선 O | 18회 후 best O | 최종 search best O | scout 감소량 | merge 감소량 | 독립 최종 O |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| P06 | 2.000000 | 1.588065 | 0.887787 | 0.411935 | 0.700278 | 0.887787 |
| P13 | 2.000000 | 0.245681 | 0.183411 | 1.754319 | 0.062269 | 0.183411 |
| P14 | 2.000000 | 0.110770 | 0.084905 | 1.889230 | 0.025865 | 0.084905 |
| P15 | 2.000000 | 0.240977 | 0.172029 | 1.759023 | 0.068947 | 0.172029 |

단계 기여량은 이 시행의 ledger 순서에 따른 목적값 감소량이다. 독립 최종 재측정의 흔들림은 search curve와 분리한다.

| 문제 | 후보 compile 초 | 후보 bundle 초 | 기준선 bundle 초 | 최종 bundle 초 |
| --- | ---: | ---: | ---: | ---: |
| P06 | 1128.475125 | 1172.746925 | 33.992149 | 20.321199 |
| P13 | 494.898660 | 722.411943 | 22.689567 | 11.769845 |
| P14 | 398.051149 | 480.100472 | 14.188425 | 49.176908 |
| P15 | 1137.967760 | 1187.483749 | 8.661928 | 17.955852 |

| 문제 | 고정 원본 T0 | 고정 원본 raw H0 |
| --- | ---: | ---: |
| P06 | 1217 | 42028705 |
| P13 | 1769 | 59565018 |
| P14 | 1754 | 81958833 |
| P15 | 4085 | 12170290 |

| 문제 | 동결된 컴파일러 | baseline 확인 버전 | final 확인 버전 | committed evidence bundles |
| --- | --- | --- | --- | ---: |
| P06 | leanprover/lean4:v4.32.0 | v4.32.0 | v4.32.0 | 42 |
| P13 | leanprover/lean4:v4.26.0 | v4.26.0 | v4.26.0 | 42 |
| P14 | leanprover/lean4:v4.26.0 | v4.26.0 | v4.26.0 | 42 |
| P15 | leanprover/lean4:v4.26.0 | v4.26.0 | v4.26.0 | 42 |

독립 최종 검증 완료 case는 baseline 1 + 후보 40 + final 1 = 42 committed bundles다. 원본 유지 case는 독립 final이 없어 41이다. Recovery/실패한 final 재시도는 추가 증거이며 후보 credit을 늘리지 않는다.

#### 해석 범위

- Input scope: exact supplied per-case primary compiler contexts only; other benchmark versions remain unverified.
- P13/P14/P15 preserve narrowed supplied local imports/opens/options; their full benchmark headers are reference-only and are not checked.
- Four original-only lexical T/raw-three-HB calibration bundles are separate from four main baselines, 160 candidates and up to four independent finals.
- Fresh starts; no old proofs or solver reports seed the new runs.
- One run per problem; no statistical efficacy claim.
- LLM reasoning tokens, billing and total wall time are unmatched and not fully metered.
- Candidate compile/bundle seconds are recorded costs, not causal speed comparisons.
- Model token budget is not controlled. Four cases have one fresh trial each; no matching historical comparison is claimed.

네 문제 모두 후보 40회와 별도의 독립 최종 검증을 마쳤다. 유효 후보 118개, 실패 후보 42개이며 실패·수정도 동일한 예산에 포함했다. 후보 18개를 모은 뒤의 추가 탐색에서도 네 문제 모두 개선됐다. 아래 감소율은 이 시행의 고정 비용 O에 대한 값이며 공식 대회 점수의 증가율이 아니다.

| 문제 | 원본 대비 최종 비용 감소 | 18회 시점 대비 추가 감소 | 원본 대비 T 감소 | 원본 대비 raw H 감소 |
| --- | ---: | ---: | ---: | ---: |
| P06 | 55.61% | 44.10% | 65.65% | 45.57% |
| P13 | 90.83% | 25.35% | 86.72% | 94.94% |
| P14 | 95.75% | 23.35% | 92.82% | 98.69% |
| P15 | 91.40% | 28.61% | 94.03% | 88.77% |

P13은 후보18 시점의 원본 대비 비용 감소 약87.72%에서 최종90.83%로, P14는94.46%에서95.75%로, P15는87.95%에서91.40%로 더 내려갔다. 이미 원본보다 많이 좋아진 후보군을 출발점으로 삼아도 추가로 줄일 여지가 있었다.

- P06: 두 span 귀납의 반복된 명시적 술어와 곱 인자 주석을 추론으로 대체하고, calc 중간 단계 및 넓은 자동화를 줄인 것이 컸다. 최종적으로는 원래의 정렬·중심성·부호 논리 골격을 유지했다. 새로운 운반 정리를 찾았다고 주장하지 않는다.
- P13: 유한한 네 값 상태의 충돌에서 주기성을 전파했다. 상태 표현·강한 귀납·직접 주기 귀납·상태 전이 귀납을 실제로 비교했고, 최선은 유한 함수 상태와 강한 귀납 경로였다. 후반에 일반 선행항 보조 정리를 없애고 제한된 rewrite로 바꾸면서 다시 크게 개선됐다. 가장 짧은211토큰 후보는 HB 때문에 선택되지 않았다.
- P14: 여집합과 부분집합의 대응으로 집합 크기 절반을 직접 증명했다. 격자 정리로 점별 의무를 줄이고, cardinality와 거듭제곱 지수의 연결을 직접 처리했다. 142토큰의 넓은 자동화 후보는 HB가 크게 늘어 탈락했으며, 최종126토큰 후보는 둘을 함께 줄였다.
- P15: 자릿수 교체의 가중 합 불변식을 공통 보조 정리로 합쳤다. 조건문 분기와 합계 정리를 한 번에 정규화하고, 소수의 나눗셈 경우 분기를 3×7−2×10=1인 Bézout 증명과 서로소 약분으로 대체했다. 마지막에는 약분을 먼저 적용해 중간 목표를 없앴다.

이는 현재 후보군을 기준으로 후속 탐색할 가치가 있다는 관찰이다. 경쟁형 프롬프트 자체의 효과, 서로 다른 출발점의 효과, 추가22회 예산의 효과를 분리한 대조 실험은 아니다. 각 문제 한 번씩의 결과이며 일반화·통계적 우월성을 주장하지 않는다. 공통 원리를 공유하는 표현 변경과 실제 다른 수학적 경로도 구분했다. 상대비용50은 탐색 목표였고 선택·중단 조건으로 사용하지 않았다.

실행 중 활성 하위 에이전트는 최대2개였고 메모리 압력이 오르면1개로 줄였다. 이 실험의 모든 네이티브 검증은 공통 잠금으로1개씩 진행했다. 다른 작업의 Lean 프로세스가 따로 관찰됐으므로 호스트 전체의 네이티브 동시성을1로 통제했다는 뜻은 아니다.

호스트 디스크 부족으로 P06의39번과 P13의30번 측정이 중단됐다. 현재 열려 있지 않은7일 이상 된 npm 다운로드 payload896개(논리491,045,758바이트)만 정리한 후 같은 후보·시도 번호로 복구했다. 실험 증거와 Lean 환경은 보존했다. 중단된 두 시작은 추가 후보가 아니며, P06의 부분 증거와 P13의 생성되지 못한 디렉터리는 복구 기록 (`runs/competitive-search40-extra-20261101/recovery-evidence.json`, 원래 실행 자료)에 구분해 남겼다. 비용 표의 compile/bundle 시간에는 이 미완료 작업이 포함되지 않는다.

P15는 모델 사용량 한도로38회 완료 뒤 중단됐고, 사용자의 재개 요청 후 같은 merger 문맥으로39·40회만 이어갔다. 이후 독립 최종 검증을 실시했다. 중단·재개 시점과 자원 운영은 운영 기록 (`runs/competitive-search40-extra-20261101/resource-events.jsonl`, 원래 실행 자료), 모델·문맥·배분은 작업자 기록 (`runs/competitive-search40-extra-20261101/worker-manifest.json`, 원래 실행 자료)에 있다.

최종 기본 감사는160후보와4final을 포함한168개 main committed bundles 및546개 source/log 실행 쌍을 확인했다. 원본 전용 calibration4개/16쌍을 더하면172개 bundles/562쌍이다. 이는 중단된 두 시작을 완전한 검증으로 세지 않은 수치다. 감사 JSON (`runs/competitive-search40-extra-20261101/audit.json`, 원래 실행 자료)과 [독립 검토](competitive-search40-extra-20261101.md)에 범위와 보충 검사를 남긴다.

검증 범위는 공급된 고정 로컬 문맥이다. P06은Lean4.32.0, P13/P14/P15는Lean4.26.0이며, 특히 Putnam 세 문제의 축소된 imports/opens/options를 그대로 유지했다. 전체 공식 benchmark header와 다른 요구 버전은 검증하지 않았다. 원본·후보는 같은 로컬 환경에서 비교했고 raw HB는3회 중앙값이다.

## 원문: `runs/competitive-search40-extra-20261101/analysis.md`

네 문제 모두 후보 40회와 별도의 독립 최종 검증을 마쳤다. 유효 후보 118개, 실패 후보 42개이며 실패·수정도 동일한 예산에 포함했다. 후보 18개를 모은 뒤의 추가 탐색에서도 네 문제 모두 개선됐다. 아래 감소율은 이 시행의 고정 비용 O에 대한 값이며 공식 대회 점수의 증가율이 아니다.

| 문제 | 원본 대비 최종 비용 감소 | 18회 시점 대비 추가 감소 | 원본 대비 T 감소 | 원본 대비 raw H 감소 |
| --- | ---: | ---: | ---: | ---: |
| P06 | 55.61% | 44.10% | 65.65% | 45.57% |
| P13 | 90.83% | 25.35% | 86.72% | 94.94% |
| P14 | 95.75% | 23.35% | 92.82% | 98.69% |
| P15 | 91.40% | 28.61% | 94.03% | 88.77% |

P13은 후보18 시점의 원본 대비 비용 감소 약87.72%에서 최종90.83%로, P14는94.46%에서95.75%로, P15는87.95%에서91.40%로 더 내려갔다. 이미 원본보다 많이 좋아진 후보군을 출발점으로 삼아도 추가로 줄일 여지가 있었다.

- P06: 두 span 귀납의 반복된 명시적 술어와 곱 인자 주석을 추론으로 대체하고, calc 중간 단계 및 넓은 자동화를 줄인 것이 컸다. 최종적으로는 원래의 정렬·중심성·부호 논리 골격을 유지했다. 새로운 운반 정리를 찾았다고 주장하지 않는다.
- P13: 유한한 네 값 상태의 충돌에서 주기성을 전파했다. 상태 표현·강한 귀납·직접 주기 귀납·상태 전이 귀납을 실제로 비교했고, 최선은 유한 함수 상태와 강한 귀납 경로였다. 후반에 일반 선행항 보조 정리를 없애고 제한된 rewrite로 바꾸면서 다시 크게 개선됐다. 가장 짧은211토큰 후보는 HB 때문에 선택되지 않았다.
- P14: 여집합과 부분집합의 대응으로 집합 크기 절반을 직접 증명했다. 격자 정리로 점별 의무를 줄이고, cardinality와 거듭제곱 지수의 연결을 직접 처리했다. 142토큰의 넓은 자동화 후보는 HB가 크게 늘어 탈락했으며, 최종126토큰 후보는 둘을 함께 줄였다.
- P15: 자릿수 교체의 가중 합 불변식을 공통 보조 정리로 합쳤다. 조건문 분기와 합계 정리를 한 번에 정규화하고, 소수의 나눗셈 경우 분기를 3×7−2×10=1인 Bézout 증명과 서로소 약분으로 대체했다. 마지막에는 약분을 먼저 적용해 중간 목표를 없앴다.

이는 현재 후보군을 기준으로 후속 탐색할 가치가 있다는 관찰이다. 경쟁형 프롬프트 자체의 효과, 서로 다른 출발점의 효과, 추가22회 예산의 효과를 분리한 대조 실험은 아니다. 각 문제 한 번씩의 결과이며 일반화·통계적 우월성을 주장하지 않는다. 공통 원리를 공유하는 표현 변경과 실제 다른 수학적 경로도 구분했다. 상대비용50은 탐색 목표였고 선택·중단 조건으로 사용하지 않았다.

실행 중 활성 하위 에이전트는 최대2개였고 메모리 압력이 오르면1개로 줄였다. 이 실험의 모든 네이티브 검증은 공통 잠금으로1개씩 진행했다. 다른 작업의 Lean 프로세스가 따로 관찰됐으므로 호스트 전체의 네이티브 동시성을1로 통제했다는 뜻은 아니다.

호스트 디스크 부족으로 P06의39번과 P13의30번 측정이 중단됐다. 현재 열려 있지 않은7일 이상 된 npm 다운로드 payload896개(논리491,045,758바이트)만 정리한 후 같은 후보·시도 번호로 복구했다. 실험 증거와 Lean 환경은 보존했다. 중단된 두 시작은 추가 후보가 아니며, P06의 부분 증거와 P13의 생성되지 못한 디렉터리는 복구 기록 (`runs/competitive-search40-extra-20261101/recovery-evidence.json`, 원래 실행 자료)에 구분해 남겼다. 비용 표의 compile/bundle 시간에는 이 미완료 작업이 포함되지 않는다.

P15는 모델 사용량 한도로38회 완료 뒤 중단됐고, 사용자의 재개 요청 후 같은 merger 문맥으로39·40회만 이어갔다. 이후 독립 최종 검증을 실시했다. 중단·재개 시점과 자원 운영은 운영 기록 (`runs/competitive-search40-extra-20261101/resource-events.jsonl`, 원래 실행 자료), 모델·문맥·배분은 작업자 기록 (`runs/competitive-search40-extra-20261101/worker-manifest.json`, 원래 실행 자료)에 있다.

최종 기본 감사는160후보와4final을 포함한168개 main committed bundles 및546개 source/log 실행 쌍을 확인했다. 원본 전용 calibration4개/16쌍을 더하면172개 bundles/562쌍이다. 이는 중단된 두 시작을 완전한 검증으로 세지 않은 수치다. 감사 JSON (`runs/competitive-search40-extra-20261101/audit.json`, 원래 실행 자료)과 [독립 검토](competitive-search40-extra-20261101.md)에 범위와 보충 검사를 남긴다.

검증 범위는 공급된 고정 로컬 문맥이다. P06은Lean4.32.0, P13/P14/P15는Lean4.26.0이며, 특히 Putnam 세 문제의 축소된 imports/opens/options를 그대로 유지했다. 전체 공식 benchmark header와 다른 요구 버전은 검증하지 않았다. 원본·후보는 같은 로컬 환경에서 비교했고 raw HB는3회 중앙값이다.

## 원문: `runs/competitive-search40-extra-20261101/comparison-88.md`

### 대회 산식과 88점 제출본 비교

13·15번만 기존 제출본보다 좋다. 6·14번은 기존 제출본을 유지하는 편이 낫다. 기존 최종 후보만 사용하면15문제 평균 약+0.114점, 저장된40개 후보를 대회 분모로 재정렬하면 약+0.121점이다. 호환성 유지와 로컬 측정의 이전을 가정한 비교이며 공식 재평가 점수가 아니다.

공식 산식: `S = (길이 감소% + HB 감소% + 호환율%) / 3`, 전체는 warmup15문제 평균. [채점 구현](https://huggingface.co/spaces/delta-lab-ai/lean-refactor-arena/blob/88057731673d44e231788e3e87a9c797d585042a/leaderboard.py)

HB는 raw 중앙값을1000으로 나눈 몫이다. 아래 점수는 호환율100% 가정이며, 대회에서 고정한 원본 분모를 사용한다.

| 문제 | 88 T / HB | 기존 최종 T / HB | 88 점수 | 기존 최종 점수 | 문제 점수 변화 |
| --- | ---: | ---: | ---: | ---: | ---: |
| P06 | 422 / 11,133 | 418 / 22,877 | 79.65 | 70.49 | -9.1614 |
| P13 | 259 / 2,606 | 235 / 3,012 | 94.34 | 94.67 | +0.3308 |
| P14 | 55 / 821 | 126 / 1,071 | 98.75 | 97.34 | -1.4113 |
| P15 | 281 / 1,822 | 244 / 1,366 | 93.41 | 94.79 | +1.3776 |

| 문제 | 대회 고정 T0 / H0(HB단위) | 실험 로컬 T0 / H0(raw) | 대회식 재정렬 최선 | 재정렬 점수 |
| --- | ---: | ---: | --- | ---: |
| P06 | 1217 / 42,225 | 1217 / 42,028,705 | attempt-40 (418 / 22,877) | 70.49 |
| P13 | 1769 / 111,476 | 1769 / 59,565,018 | attempt-39 (211 / 4,156) | 94.78 |
| P14 | 1754 / 134,499 | 1754 / 81,958,833 | attempt-39 (126 / 1,071) | 97.34 |
| P15 | 4085 / 14,130 | 4085 / 12,170,290 | attempt-38 (244 / 1,366) | 94.79 |

P13은 선택이 바뀐다. 로컬 분모에서는235토큰/H3,012,079인40번이 최선이었지만, 대회 분모에서는211토큰/H4,156,941인39번이94.78점으로 앞선다. 대회가 고정한 원본HB111,476k는 로컬59,565,018raw보다 커서 길이 절감의 상대적 가치가 커진다. 이 후보는 기존 탐색의 검증된 증거만 사용했으며 final.lean을 교체하거나 추가 독립 검증하지 않았다.

| 교체 방식 | 15문제 평균 변화 | 동일 환경·공식 분모 proxy 총점 |
| --- | ---: | ---: |
| 기존 최종4개 모두 | -0.590946 | 87.575955 |
| 기존 최종 중13·15만 | +0.113898 | 88.280800 |
| 대회식 재정렬4개 모두 | -0.583602 | 87.583299 |
| 대회식 재정렬13·15만 | +0.121242 | 88.288143 |

88.14의 보관된 과거 문맥 지표를 재계산하면 88.136350997점이다. 같은88증명을 이번과 같은 로컬 환경에서 측정하고 공식 분모를 쓰면 88.166901356점, 이전 로컬 분모를 쓰면 88.089698128점이다. 위 총점 표는 두 번째 기준으로 통일했다. 서로 다른 문맥·분모의 절대 총점을 직접 섞지 않는다.

P13·P15는 각3개 버전 중 현재1개만 검증했다. 미검증을 실패로 간주하지도, 성공으로 간주하지도 않는다. 새 후보가 각각 추가 버전1개에서 실패하면15문제 평균 약0.741점씩 손해여서 이번 약+0.12점의 이익을 넘는다. 기존88의 이 네 문제는 보관된 버전 검사에서 모두 통과했지만, 전체15문제의 로컬 기록은33/36으로 불완전하다.

보관된88입력의 SHA와 개별 증명, cached reference 측정의 source/log 해시·3회 중앙값·컴파일러/템플릿 fingerprint를 확인했다. 현재 mutable submission 파일은88입력과 다르므로 사용하지 않았다. 새 Lean 평가·모델 호출·제출·160회 기록 변경은 없다.

한계:

- No new candidate, model call, Lean evaluation, promotion or submission; original160 and finals unchanged.
- Old reference environment JSON and compiler/project/template/command fingerprints match each current local environment.
- Measurement wrapper spelling difference in Name.toString is after the heartbeat finish counter; independently inspected.
- P13/P14/P15 preserve narrowed local imports; official full-header and extra-version transfer remain unverified for new candidates.
- P13 contest-ranked attempt39 has its existing plain+three measurement bundle; no independent final for that newly ranked source.
- 88.13635 historical-context proxy,88.16690 same-environment published-denominator proxy and88.08970 local-denominator proxy are distinct. Do not mix their absolute totals.
- Unrounded scores are reported for deltas; displayed problem scores also follow two-decimal axis rounding. Official total display can differ by rounding.

## 원문: `runs/competitive-search40-extra-20261101/audit-review.md`

### Independent offline evidence review

**PASS for the frozen supplied local scope.** The default `audit.py` exited 0 after all four cases had exactly 40 completed candidates, no inflight candidate, an independent final bundle and a solver report. Its unmodified JSON output is `audit.json`. No Lean, lake, model, network or controller execution phase was invoked by this reviewer, and no frozen/core/evaluator evidence was changed.

| Case | Candidate valid / invalid | Allocation a/b/c/merge | Committed main bundles | Source/log run pairs | Selected | Final T | Final raw H | Final O |
| --- | ---: | --- | ---: | ---: | --- | ---: | ---: | ---: |
| P06 | 25 / 15 | 6/6/6/22 | 42 | 123 | attempt-40 | 418 | 22877043 | 0.887787026692 |
| P13 | 30 / 10 | 6/6/6/22 | 42 | 138 | attempt-40 | 235 | 3012079 | 0.183411333267 |
| P14 | 30 / 10 | 6/6/6/22 | 42 | 138 | attempt-39 | 126 | 1071111 | 0.084904694206 |
| P15 | 33 / 7 | 6/6/6/22 | 42 | 147 | attempt-38 | 244 | 1366707 | 0.172029360888 |

The 160 candidate credits contain 118 valid and 42 invalid results. Main evidence is 4 baselines + 160 candidates + 4 fresh finals = **168 committed bundles and 546 source/log run pairs**. Four separate original-only calibration bundles add 16 pairs and consume zero candidate credits: **172 committed bundles and 562 pairs overall** (130 valid bundles and 42 invalid candidate bundles). Invalid bundles preserve their failed plain check; they are not promoted to successful four-run measurements. Two interrupted, uncommitted starts are additional bookkeeping, not additional completed bundles.

The audit checks per-case frozen file manifests, protocol/input/compiler fingerprints, candidate source hashes, ledger hash chains and state consistency; exact quotas and merger readiness; compiler scope; source/log hashes; valid plain-check-plus-three-measurement structure; allowed axioms (`propext`, `Classical.choice`, `Quot.sound`); logged raw samples and their median; final selection/source hash and fresh-final improvement. All four selected sources match the integer-ranked measured best and their final source hashes. Each independent final is valid and strictly improves its fresh baseline under fixed O. P15 final samples are [1366707, 1366666, 1366726], whose median is 1366707.

Supplemental read-only checks independently recomputed lexical T and checked the unchanged statement/declaration restrictions for all 168 main and 4 calibration bundles. Every one of the 562 archived sources exactly matches the frozen template rendered with its exact declaration; measured sources/logs match the target and their specific nonce. The 12 new input files' manifest hashes/byte counts and the preparation script hash match. Calibration's 56 frozen files and all four raw-three-HB medians match the frozen original-only normalizers: P06 (1217,42028705), P13 (1769,59565018), P14 (1754,81958833), P15 (4085,12170290). Published scaled benchmark values are not used as normalizers. `results.json` and the four solver reports agree with final state metrics; all 12 scout reports exist, and each scout-a input omits the original declaration. The protocol requires 16 fresh `gpt-6.1-sol`/high solver contexts; worker identity/model and active scheduling are host-recorded operational facts, not conclusions derivable from compiler logs alone.

#### Interrupted starts and recovery

`recovery-evidence.json` was independently checked against ledger reservations/start/result events, candidate hashes, earlier evidence inventory, byte counts, hashes and exact candidate inclusion. P06 attempt-39 has one reservation and two starts. Its first directory has seven files, no `evaluation.json` and no `measure-3.log`: **incomplete, uncommitted, not validated as a complete bundle**. P13 attempt-30 also has one reservation and two starts; its first measurement directory was never created. Its missing first evidence is likewise **not validated**. Each recovered measurement-2 commits the exact reserved candidate under its original single credit. Recovery adds zero candidates. Interrupted work is excluded from committed candidate timing totals.

#### Interpretation and limits

O is fixed T/T0 + H/H0, with lexical proof tokens and original-only local calibration median raw heartbeats frozen before solvers; raw heartbeats are not wall-clock time. P06 is checked only in supplied Lean v4.32.0; P13/P14/P15 only in supplied Lean v4.26.0 with their narrowed imports/opens/options. Full official benchmark headers and other compiler versions remain unverified. Search measurements and independent final remeasurements remain distinct. Four cases with one trial each support descriptive within-run results, not causal branch efficacy, statistical superiority or generalization.

The reviewed static policy and host resource log record one shared controller native lock, at most two active solver contexts, temporary future-dispatch reduction to one under memory pressure, and subsequent restoration. Disk recovery is recorded as removal of stale unopened npm download payloads; frozen evidence consistency passed afterward. This offline review does not independently observe host scheduling, solver visibility outside supplied artifacts, or cleanup process history. No blocking evidence-integrity issue was found within the audited scope.

#### Final reporting addendum

After the main review, `analysis.md`, `worker-manifest.json` and the experiment README completion statement were reviewed read-only. Every displayed original-to-final, evaluation-18-to-final and original-to-evaluation-18 percentage in the analysis agrees with `results.json`/ledger metrics to its stated two-decimal precision. The worker manifest has 16 unique solver identities; every case/role quota, completed/valid/invalid count and report path agrees with the corresponding ledger (160 candidates, 118 valid, 42 invalid; 12 scout reports and 4 merger reports). README bundle/run totals and the narrowed compiler/header scope agree with the audit.

The resource and usage-limit narratives are consistent with `resource-events.jsonl`: experiment-native concurrency is one, distinct from host-wide Lean activity; future context scheduling was reduced under pressure; P15 is recorded as resuming the same merger at 38 completed with only credits 39/40 remaining, followed by its final. Model identity, fresh-context/fork settings, same-context resumption, scheduling and cleanup remain host tool-dispatch/operational attestations, not facts inferred from Lean files. Local Git account configuration recovery and successful account/login rechecks were separately reported by the host and do not establish any proof-evidence property. No numerical, scope or bookkeeping contradiction was found in these final reporting artifacts. No core/native work or full-audit rerun was needed for this addendum.
