# v9 세 문제 유료 시행

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

원본 출발 P01/P10/P14에 같은 high reasoning·문제당$2.70·40평가 목표를 적용한다.

## 확인된 결과와 해석

선택3문제 조건부 평균69.21297, 목표40회 미달. 무작위 표본이나15문제 점수 추정이 아니다.

## 코드·Lean 보존 결정

v9 구현과 구분해 실험 시행·진단·지출을 보존한다.

## 보존 근거

아래는 당시 설계·실행 결과의 Markdown 본문이다. 당시의 진행 상태·경로·명령을 보존했으며, 현재 실행 지침이나 새 실행 요청이 아니다. 상충하는 중간 기록은 더 뒤의 완료 보고서와 본문 첫 요약을 우선한다. 결과 이해에 Lean·JSON·그림 열람은 필요하지 않다. 원시 로그를 다시 감사하거나 실행을 재현하려면 별도 원본·고정 환경이 필요하다.

| 원본 | 출처 | 원문 SHA256 |
| --- | --- | --- |
| `experiments/research-trial-20261031/README.md` | `로컬 작업본` | `a0c37308e072d5af7d6f8d42b91119de957e16a5aeab484ee592bcc35ee37488` |
| `runs/research-v9-threecase-20261031/comparison.md` | `로컬 작업본` | `57010a72a96de303366b494a654874e758847445683adb5b82a5e0ae1ca1b991` |
| `runs/research-v9-threecase-20261031/diagnosis.md` | `로컬 작업본` | `cae994f3913b0f8af2a5c9e5d4ad5eacd475dd0baa960a9a931dd097b692aa6d` |

## 원문: `experiments/research-trial-20261031/README.md`

### Three-case paid v9 trial

Completed: all three full golf runs and final source/proof/ledger audits passed,
but the search target failed at 11/2/24 of 40 evaluations. Total API cost was
$6.5364999, with 76.74% spent on inspection. Selected-three conditional mean:
69.21297. See `runs/research-v9-threecase-20261031/comparison.md`,
`diagnosis.md` and `final-cross-check.json`. The frozen trial was not changed to
hide its working-context regression or its source-losing legacy golf parser.

User request: operate subagents for three problems, forty attempts, measure time
and score. The existing $2.70/case cap remains authoritative. Selection was fixed
before dispatch: P01 (prior prompt benchmark), P10 (type extraction defect and
earlier timing pilot), P14 (imported API discovery). This is a selected-case probe,
not a randomized sample or a fifteen-case score estimate.

Three operator subagents each run exactly one unchanged v9 controller through
`case_worker.py prepare --problem Pxx`, then `run --problem Pxx`. Model proposals
come exclusively from the existing OpenAI API (`gpt-6.1-sol`, high reasoning).
Operators supply no proof hints, historical candidates or reference solutions.
Every case shares the same instruction hash. API inspection actions and preflight
rejections cost money but do not count as completed Lean proof evaluations.

The wrapper adds telemetry and a shared three-slot native-process semaphore. It
does not change candidate policy, prompts, budgets, sampling or golf. Per-case
roots, worker logs, requests/responses in SQLite, full Lean logs and sources are
preserved. `run` uses the normal key loader without logging credentials. Unknown
network responses must be reconciled, never automatically re-dispatched.

All three intermediate measurements, independent final checks, and the original
full golf algorithm are retained. No v8 forty-screen/180-second cap is used.
If the cost reservation policy stops before forty evaluations, report the actual
count and stop reason explicitly; API calls, inspections and golf screens are
separate counts and must not be substituted for forty proof attempts.

```sh
source /Users/jwkweon/00_work/00_project/env/use.sh 05_pseudolab/LeanAgent-LeanRefactorArena
python -B experiments/research-trial-20261031/case_worker.py prepare --problem P01
# Paid; run only an explicitly authorized case and do not duplicate a worker:
python -B experiments/research-trial-20261031/case_worker.py run --problem P01
# Read-only, no credentials or compiler work:
python -B experiments/research-trial-20261031/analyze.py
```

Study output: `runs/research-v9-threecase-20261031/`. Workflow roots are siblings
with `-p01`, `-p10`, `-p14` suffixes. `comparison.json` records separate preparation,
run, model-wait, native-slot-wait and candidate-evaluation wall times. Accounted
cost includes outstanding reservations while running; `settled_usd` includes only
receipted calls. Final dollar totals are usage-based estimates under verified
model/cache pricing, not an independent account invoice.

Scores use the same original normalizers as v6 and the rechecked 88-line snapshot:
`100 - 100/3 * (T/T0 + H/H0)`, conditional on full required-version compatibility.
Only actually verified pins are listed. Historical timing had different queueing
and candidates, so elapsed differences are descriptive, not causal speedups.
The three-case mean is not the full fifteen-case result.

Any loops or defects observed during the paid run are recorded and left unchanged
until completion. Do not re-prepare the same case during the trial: the existing
native inventory cache rewrites gzip metadata at the same content-keyed path,
which can invalidate earlier prepared context hashes. This is a separate future
cache-integrity repair, not a reason to change the current solver mid-experiment.

## 원문: `runs/research-v9-threecase-20261031/comparison.md`

### V9 공통 하네스 3문제 실험

상태: complete. 모델: gpt-6.1-sol, 문제당 최대 $2.70, 목표 40회 평가, 전체 golf.

| 문제 | 평가(성공/실패) | 실행 시간 | 비용 | v9 점수 | v6 점수 | 88 라인 점수 |
|---|---:|---:|---:|---:|---:|---:|
| P01 | 11 (5/6) | 35분 58초 | $2.1758948 | 75.94 | 84.92 | 88.08 |
| P10 | 2 (0/2) | 3시간 27분 40초 | $2.1177435 | 33.33 | 79.84 | 87.51 |
| P14 | 24 (19/5) | 38분 18초 | $2.2428616 | 98.36 | 96.72 | 98.62 |

점수는 동일 원본 정규화값으로 계산하며 모든 필수 버전 호환을 가정한 조건부 로컬 값이다. 15문제 전체 점수 또는 공식 제출 점수가 아니다.
과거 실행과 동시 작업·큐 조건이 달라 시간 차이를 하네스의 인과적 개선으로 해석할 수 없다. 문제별 준비 시간·조회·호출·평가 수는 comparison.json에 기록한다.

## 원문: `runs/research-v9-threecase-20261031/diagnosis.md`

### V9 실제 실행에서 확인한 문제

세 문제의 API 탐색은 모두 종료됐다. 목표는 문제당 40회 Lean 평가였지만,
P01 11회, P10 2회, P14 24회로 합계 37/120회만 완료했다. 종료 사유는 모두
`budget_reservation`이다. 실제 비용이 상한을 초과한 것이 아니라, 남은 금액으로
다음 호출의 보수적 예약액을 충족하지 못했다.

총 251개 요청의 정산 비용은 $6.5364999였다. 조회 205회에 $5.0161778,
후보 평가 37회에 $1.2416722, 거절 9회에 $0.2786499를 사용했다.
조회 비중은 비용의 76.7410%다. 각 문제의 $2.70 및 전체 $8.10 상한을 지켰다.
요청/응답/원장/단가/전역 response_id 고유성은 독립 감사에서 확인했다.

#### 원장에 보존하는 것과 모델 문맥에 보존하는 것은 다르다

V9는 조회 원문을 상태 원장에 보존하지만, 반복되는 모델 입력에는 이전 조회의
요청·해시 요약만 넣었다. 전체 조회 결과는 `latest` 한 건에만 있다. 실패 후보의
전체 코드도 Pareto frontier에는 없으므로 별도 조회로만 가져올 수 있다.

특히 이전 v6 입력의 `recent_candidates`는 최근 실패 후보의 전체 코드도 포함했다.
V9에서 이를 경험 그래프와 유효 후보 frontier로 교체하면서, 활성 실패 후보 본문을
기본 입력에서 누락시킨 회귀가 생겼다. 입력 데이터 저장은 늘었지만 실제 수리
작업에 필요한 문맥의 완전성은 오히려 떨어졌다.

따라서 실패 후보 코드를 조회하면 앞서 본 타입 결과가 사라지고, 타입을 다시
조회하면 실패 후보 코드가 사라진다. 모델이 두 자료를 번갈아 재요청하는 현상이
실제 세 문제에서 나타났다. 성공 후보가 생긴 뒤에는 frontier에 그 코드가 남아
직접 수정이 늘었지만, 정확한 인과 효과는 별도 실험이 필요하다.

P01 call-037~073의 실제 API 요청 본문을 읽어 다음을 재현했다.

- 실패 부모 `attempt-03` 전체 코드와 observation-call-036의 타입 5개가
  한 요청에 함께 존재한 경우: **0회**.
- 실패 부모 코드만 온전히 존재한 경우: 14회.
- 조회 타입 5개만 온전히 존재한 경우: 15회.
- 이전 조회 요약에는 결과 원문이 없었다.

이는 완전한 원문 문자열의 존재 여부 검사이며, 원래 문맥에 의미상 동치인 다른
서술이 있었는지까지 판정하지 않는다. 문맥 누락은 결정적으로 재현되지만 모델
선택에 대한 효과 크기는 통제된 ablation으로 입증한 수치는 아니다.
근거는 `fact-retention-repro.json`과 각 문제의 inspection 분석 파일에 있다.

원문 JSON 요청 기준으로 P01은 조회 61회에 고유 요청 9개,
P10은 74회에 9개, P14는 70회에 29개였다. 검색어 대소문자를 동일하게 처리하면
P14의 고유 요청은 28개다. P10은 조회 비용만 $1.9818894로 전체의 약 93.6%였다.

P01의 거절 8회는 모두 repair 메타데이터 연결 규칙 위반이었다.
진단 ID 연결 7회, 실패 부모 evidence 연결 1회다. P10 거절 1회도 부모 evidence
연결 문제였다. 이 후보들이 Lean 자체에서 성공했을 것인지는 아직 확인하지 않았다.

#### 후처리와 실행 대기가 실패 비용을 확대했다

P10은 탐색에서 유효 후보를 얻지 못해 1,463토큰 원본을 golf 시작점으로 넘겼다.
기존 전체 알고리즘이 첫 라운드에 생성한 짧은 고유 변형만 1,965개다.
따라서 후처리 완료에 오래 걸리는 것은 단순 API 대기와 다른 비용이다.
실행 시간은 탐색/독립 최종 검증/전체 golf로 구분해야 한다.

동일한 frozen golf 코드로 기존 v6 P10 시작 후보와 이번 후보의 첫 라운드
변형 수를 다시 열거했다. v6는 457토큰에서 515개, 이번은 1,463토큰에서
1,965개로 **3.8155배**다. 이 분석은 compiler/API 호출 없이 수행했고,
과거 후보를 실행 중 solver/golf에 제공하지 않았다. 결정적인 검사량 차이이며
전체 실행 시간의 인과적 배율을 뜻하지 않는다(`P10-golf-workload-comparison.json`).
또한 뒤에서 확인한 파서의 본문 유실 때문에, 이 3.8155배를 순수한 시작 증명 길이의
효과로 해석하면 안 된다. 더 큰 원본과 파서 훼손이 각각 얼마를 기여했는지는
정정한 파서의 통제 비교 없이 분리할 수 없다.

측정용 공유 슬롯은 전체 native 프로세스를 3개로 제한한다. 그러나 nonblocking
flock 폴링에는 FIFO 보장이 없다. 일찍 시작한 golf가 슬롯을 재획득하면서 P14
검색이 기다렸다. 실제 P14 attempt-16은 전체 286.32초, 컴파일 합계 5.48초였다.
공유 슬롯 대기 합계도 별도로 기록했다. 이 스케줄링 계층은 이번 3개 운영
서브에이전트를 위한 wrapper이므로 v9 전략 자체의 시간 효과와 혼동하면 안 된다.

완료된 P01은 전체 golf 신규 변형 88개를 검사했지만 개선하지 못했다.
P14도 신규 변형 77개에서 개선을 채택하지 못했다. P10도 신규 변형 1,965개 전체를
끝까지 검사했고 첫 라운드에서 개선을 채택하지 못해 종료했다. 최종 출력은 원본과
바이트 동일하며, 실행 3시간 27분 40초 중 golf가 3시간 17분 43초였다.

선택한 세 문제의 최종 조건부 평균은 69.21297점이다. 동일 세 문제의 v6는
87.15826점, 88 라인 snapshot은 91.40537점이다. 이는 15문제 전체 점수나 공식
제출 점수가 아니다. 원장·소스·런타임·출력 증명 해시와 3회 측정 대조는
`final-cross-check.json`에서 전부 통과했다. 전체 준비 시작부터 마지막 실행
종료까지 3시간 30분 59.55초가 걸렸다.

#### 별도로 확인한 frozen golf 파서의 원문 훼손

진행 중인 P10 원본에 아무 변형도 하지 않고
`assemble(statement, parse(original, statement))`만 적용했다. 원본은 209줄,
1,463토큰이었는데 재조립 결과는 43줄, 554토큰이 됐다. 주석을 제외한 실제 코드
토큰도 달라졌으며 `h_exp_lt` 등 코드가 사라졌다. `parse`가 들여쓴 줄들을 공백으로
합치면서 `--` 뒤에 오는 코드까지 같은 줄 주석으로 처리되게 만든 것이 한 원인이다.
줄바꿈·배치 자체도 Lean 문법의 일부이므로 일반적인 공백 정규화로 다뤄선 안 된다.

정상 원본이 이미 baseline의 순수 문맥 check와 3회 측정을 통과한 상태에서,
재조립본을 동일 원본 문맥의 plain Lean으로 별도 1회 검사했다. 12.546184초 후
exit code 1로 실패했고 `unsolved goals`와 `unexpected identifier`가 발생했다.
근거는 `P10-roundtrip-analysis/report.json` 및 그 아래 `native/summary.json`,
`native/check.log`다. 원문 재조립이 의미를 보존하지 않는다는 반례를 확보했다.

이 진단은 추가 API 0회, 별도 native 1회다. 본 실험의 모델 제안 37회 평가와
golf 화면 수에는 합산하지 않는다. 공유 3개 슬롯 중 하나에서 동시 실행했으므로
실제 worker wall time에 미친 가능성은 남기며 12.55초를 임의로 빼지 않는다.
실행 중 frozen golf 코드나 worker는 수정·재시작하지 않았다.

따라서 이번 P10의 후처리 무개선을 골프 탐색 전략 자체의 무효성으로 일반화할 수
없다. 후보 생성에서 원문을 훼손한 회귀도 섞여 있다. 최종 선택 증명의 유효성은
독립 check/측정과 해시로 검증하므로, 잘못된 변형이 유효한 증명으로 채택되었다는
뜻은 아니다. 다음 수정에는 무변형 원문 보존 검사와 문법 스팬 기반의 국소 변경이
필요하다. 이를 실행 중 실험에 소급 적용해서 결과를 바꾸지 않는다.

초기 pool 전체를 추가로 정적 열거했다(`P10-roundtrip-analysis/pool-admission.json`).
1,965개 중 1,230개는 주석을 제거하고 공백으로 나눈 소스 조각열이 무변형 재조립본과
같았고, 1,300개는 재조립본의 554토큰보다도 짧지 않았다. 원본의 1,463토큰과 비교한
shortening 필터는 모두 통과했다. 이는 원문 유실 자체가 후보 승인과 검사량을
부풀릴 수 있음을 구체적으로 보여준다. 이 문자열 비교는 Lean 배치나 문자열의
의미적 동치 검사가 아니며, 해당 1,230개를 의미적으로 동치라고 단정하지 않는다.

#### 다음 수정이 겨냥해야 할 공통 원인

실행 중 전략·프롬프트·golf 범위는 변경하지 않았다. 다음 수정은 반복 조회를
횟수로 금지하는 방식보다, 조회된 고유 사실과 활성 후보·진단을 함께 유지하는
작업 문맥을 만드는 쪽이어야 한다. 전체 호출 이력은 원장에 보존하되 모델에는
중복 결과의 별칭을 정리한 사실 집합과 그 출처를 주는 방법을 검증할 수 있다.
가설·확인된 compiler 사실·검증된 증명은 구별해야 한다.

부가적으로 repair 계획 주석의 연결 오류 때문에 실제 Lean 검사를 막는 규칙과,
검색/golf 사이의 자원 큐 정책도 별도 검토 대상이다. 새 유료 실험은 추가 승인된
범위 없이 시작하지 않는다.

같은 native inventory를 다시 준비하면 내용 키가 같은 gzip 경로를 다시 쓰면서
압축 메타데이터가 변해 이전 준비 파일의 해시를 무효화하는 문제도 확인했다.
이는 향후 캐시를 불변·원자적으로 보존해야 할 이유다. 이번 세 실행은 서로 다른
캐시 키를 사용했고, 실행 중 재준비하지 않았다.

최종 점수·시간은 `comparison.json`/`comparison.md`가 기준이다. 점수 비교에는
동일 원본 정규화값을 사용하며, 필수 버전 전체가 검증되지 않은 문제는 전체
호환을 가정한 조건부 값이다. 과거 실행과 큐/경합이 달라 인과적 속도 개선이나
15문제 전체 점수 개선을 주장하지 않는다.
