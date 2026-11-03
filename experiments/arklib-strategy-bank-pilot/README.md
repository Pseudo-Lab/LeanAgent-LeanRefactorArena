# ArkLib Strategy Bank 파일럿 — 10문제 확정 결과

[PR #69](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/pull/69)의 실험/증명/근거 분리 구성을 참고해 ArkLib 결과를 공유합니다.
**9개 개선 증명과 1개 원본 유지 결과**입니다. 10개 replacement declaration, 원본, diff, 지표 JSON/CSV와 실행 당시 하네스 보강 코드를 보존합니다.
공식 서버에 제출하거나 공식 worker로 채점한 결과는 아닙니다. 최신 main의 `src/`를 이 PR에서 교체하지 않습니다.

## 최종 파일과 문제별 결과

`.lean`은 정리 선언 전체의 replacement declaration입니다. 독립 모듈이 아니므로 지정 header·원본 파일 문맥·toolchain에서 검사해야 합니다.
7번은 두 차례 탐색의 생성 후보들이 지정 버전을 모두 통과하지 못해 **원본과 동일한 파일**입니다. 10개 모두 수정됐다는 의미가 아닙니다.

| 문제 / 최종 Lean | 상태 | 토큰 원본 → 최종 | Raw HB 원본 → 최종¹ | 지정 버전 | 종합 점수² | 토큰 감소율 | HB 감소율² | 사용 비용 / 실행별 예산 | API 호출 |
|---|---|---:|---:|---|---:|---:|---:|---|---:|
| [interleaved_affine_gaps_imply_tensor_gaps](proofs/interleaved_affine_gaps_imply_tensor_gaps.lean) | 개선 확정 | 1,353 → 427 | 9,185,435 → 3,421,286 | 4.34.0, 4.33.1, 4.31.0, 4.30.0: 전부 통과 | 76.9047 | 68.44% | 62.27% | $1.3313948 / $2.50 | 40 |
| [Binius.BinaryBasefold.fold_advances_evaluation_poly](proofs/Binius.BinaryBasefold.fold_advances_evaluation_poly.lean) | 개선 확정 | 1,906 → 418 | 45,488,466 → 8,952,006 | 4.31.0, 4.30.0: 전부 통과 | 86.1384 | 78.07% | 80.35% | $1.4552396 / $2.50 | 40 |
| [Binius.BinaryBasefold.fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius](proofs/Binius.BinaryBasefold.fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius.lean) | 개선 확정 | 1,463 → 672 | 15,886,419 → 6,671,017 | 4.31.0, 4.30.0: 전부 통과 | 70.6834 | 54.07% | 57.98% | $1.6471116 / $2.50 | 40 |
| [Combine.master_lemma](proofs/Combine.master_lemma.lean) | 개선 확정 | 546 → 406 | 282,474,830 → 6,977,010 | 4.33.1, 4.31.0, 4.30.0: 전부 통과 | 74.2640 | 25.64% | 97.15% | $1.0146596 / $2.50 | 40 |
| [JohnsonBound.johnson_bound_alphabet_free](proofs/JohnsonBound.johnson_bound_alphabet_free.lean) | 개선 확정 | 2,440 → 1,733 | 84,137,861 → 22,065,084 | 4.31.0, 4.30.0: 전부 통과 | 67.7725 | 28.98% | 74.34% | $2.2047912 / $2.50 | 40 |
| [ProximityToRS.dir_close_of_many_close_pts](proofs/ProximityToRS.dir_close_of_many_close_pts.lean) | 개선 확정 | 5,128 → 1,428 | 105,831,625 → 14,143,202 | 4.31.0, 4.30.0: 전부 통과 | 86.2523 | 72.15% | 86.60% | $1.9397206 / $2.50 | 30 |
| [ProximityGap.RS_exists_nonzero_kernelVec_of_det_eq_zero_natDegree_le_one](proofs/ProximityGap.RS_exists_nonzero_kernelVec_of_det_eq_zero_natDegree_le_one.lean) | 원본 유지 | 2,122 → 2,122 | 163,599,734 → 163,599,734 | 4.31.0, 4.30.0: 전부 통과 | 33.3333 | 0.00% | 0.00% | $3.2558052 / $2.50 × 2회 | 80 |
| [ProximityGap.RS_jointAgreement_of_goodCoeffs_card_gt](proofs/ProximityGap.RS_jointAgreement_of_goodCoeffs_card_gt.lean) | 개선 확정 | 5,538 → 2,108 | 60,935,224 → 18,076,989 | 4.31.0, 4.30.0: 전부 통과 | 77.3186 | 61.94% | 70.02% | $1.9865501 / $2.50 | 37 |
| [Sumcheck.Spec.SingleRound.Simple.reduction_perfectCompleteness](proofs/Sumcheck.Spec.SingleRound.Simple.reduction_perfectCompleteness.lean) | 개선 확정 | 1,426 → 615 | 44,259,801 → 27,896,928 | 4.31.0, 4.30.0: 전부 통과 | 64.2301 | 56.87% | 35.82% | $1.3892044 / $2.50 | 40 |
| [ps_coprime_case_constant](proofs/ps_coprime_case_constant.lean) | 개선 확정 | 1,105 → 674 | 43,924,817 → 6,828,906 | 4.34.0, 4.33.1, 4.31.0, 4.30.0: 전부 통과 | 74.5917 | 39.00% | 84.77% | $1.2087816 / $2.50 | 40 |

- 문제별 점수 평균: **71.1489점**. 문제별 토큰 감소율 평균 **48.52%**, HB 감소율 평균 **64.93%**.
- 총 토큰: **23,027 → 10,603**. 지정 버전 **25/25 조합 통과**.
- 초기 10문제 API 계산액 **$15.8040339**, 7번 독립 재실행 **$1.6292248**, 합계 **$17.4332587 / 427회**.
- 초기 OpenRouter 인증 실패는 성공한 생성/사용량 영수증이 없어 비용을 0으로 확정하지 않았습니다. **$0.258152 미확정 예약액**을 별도 보존하며, 이를 포함한 예산 점유액은 **$17.6914107**입니다.
- 7번 비용은 초기 $1.6265804 + 재실행 $1.6292248 = **$3.2558052**입니다. 각각 별도로 승인·관리한 $2.50 실행 두 번이며, 한 번의 $2.50 실행 비용이라고 표기하지 않습니다.

¹ 표의 대표 Raw HB는 **Lean 4.31.0**에서 각 증명을 새 프로세스로 3회 측정한 중앙값입니다. 벽시계 시간이 아닙니다.
² 점수와 HB 감소율은 **각 지정 버전에서 원본 대비 비율을 계산한 뒤 문제 안에서 평균**합니다. #69의 대표 버전 HB 방식과 이 집계 차이를 구분합니다.

```text
L = 100 × (1 − T/T0)
H = mean_v[100 × (1 − HB_v/HB0_v)]
C = 100 × 통과 버전 수 / 지정 버전 수
종합 로컬 추정 점수 = (L + H + C) / 3
```

최종 확정 파일은 모두 C=100입니다. 원본 유지인 7번은 L=H=0이므로 33.3333점입니다.
생성 후보의 50% 호환성을 원본의 100%로 바꿔 성공으로 집계하지 않습니다. 생성 후보 실패와 최종 원본 유지 상태를 분리합니다.
[버전별 Raw HB CSV](metrics-by-version.csv), [문제별 CSV](results.csv), [반올림 전 JSON](results.json)에 계산 근거가 있습니다.

## 실험 목적과 하네스 보강

기존 actions-v1의 생성·수리·검색·best 갱신에 **선택적 Strategy Bank**를 연결해 실행 가능한 측정 경로를 확인했습니다.
같은 benchmark의 before/after 관찰에서 만든 20개 카드(`dashboard-mechanisms-v2-team-1`)를 contextual/top-1로 사용했습니다.

- 목표·현재 증명의 표현·전술·사용 정리 단서를 정규식 신호로 추출하고 카드의 필수/선택 조건으로 추천합니다. 임베딩·학습 기반 retriever가 아닙니다.
- 현재 문제 자신의 관찰은 전이 근거에서 제외합니다. 원본을 숨기는 scout에는 Bank 힌트를 주지 않습니다. 이번 실행은 일반 actions 탐색입니다.
- 카드 metadata, 분리된 evidence, current-best/goal/failure 문맥, `strategy_hints`, 추천/선택 선언/후보 생성/검증 trace를 연결했습니다.
- `strategy_ids`는 모델의 선택 선언입니다. 실제 적용이나 효과의 증거로 자동 승격하지 않으며, 모든 카드는 `review_required`입니다.
- 검증된 카드별 성공률·버전 가산점을 새로 학습하지 않았습니다. 전체 후보의 지표 개선은 여러 변환의 공동 효과입니다.
- OpenAI direct transport, 토큰 사용량 기반 비용 영수증, **호출 전 예약 ledger**를 연결했습니다. 비용 미확정/중복 전송/예약 초과 시 추가 호출을 차단합니다.
- temp3의 전체 원본 파일 문맥·버전/커밋 packet을 기존 evaluator에 연결하고 Name.toString을 명시적으로 한정했습니다. Finset/Aesop의 정상 구문을 처리하는 동결 intake gate를 사용했습니다.
- Lean은 준비된 소스/빌드를 읽기 전용·네트워크 차단으로 사용합니다(`/dev/null` 제외). 라이브러리를 다시 빌드하거나 toolchain을 올리지 않았습니다.

`runtime/src/lean_agent`는 실제 실행의 byte-exact 스냅샷입니다. 모든 초기 10개 실행과 재실행에서 같은 공통 모듈을 사용했음을 비교했습니다.
[`snapshot-integration.patch`](snapshot-integration.patch)는 main `a517db26…` 대비 보강 차이를 검토하기 위한 패치이며, 이 PR 자체는 main 공통 하네스를 수정하지 않습니다.

## 실행 계획과 실제 수행 내용

1. 공식 `benchmark_data_final.jsonl`에서 `source=arklib` 10개와 버전/commit, 원본·statement SHA를 고정했습니다.
2. 원본에서 시작해 20-card/contextual/top-1 **한 조건**으로 실행했습니다. 모델은 **OpenAI direct `gpt-6.1-sol`, reasoning high, seed 42**입니다. 과거 개선 증명은 생성 입력에 넣지 않았습니다.
3. 초기 총예산 $25, 실행별 문제당 $2.50, 최대 모델 호출 40회입니다. 검색/분석/실패/수리 호출도 비용과 호출 수에 포함됩니다.
4. 다음 호출 최대 예상 비용까지 예약합니다. 초기 인증 실패 예약액 때문에 첫 OpenAI 실행의 실제 가용 상한은 $2.241848, 배치 가용 상한은 $24.741848이었습니다. #69의 응답 후 soft stop과 다릅니다.
5. 생성은 Lean 4.31.0에서 check + HB 1회로 탐색합니다. 공통 핵심은 유효 후보의 토큰/HB 비율합으로 best를 갱신합니다. 최종 선택·버전 검사는 아래처럼 별도 단계로 보존했습니다.
6. 채택 파일은 모든 지정 버전에서 원본/후보의 check + 3회 계측 기록을 확인했습니다. statement·소스 문맥·허용 공리·소스/로그 hash·원본 비용 응답·replay를 감사했습니다.

### 선택 정책과 중간 보완의 공개

초기 파일럿 컨트롤러는 원본을 기본 선택으로 둔 뒤 공통 탐색 순위의 유효 후보를 검사해,
**전체 버전 통과 + T/T0와 버전별 HB 비율 평균의 합 < 2**인 첫 후보를 채택했습니다.
이는 공통 핵심의 선택 함수 그 자체가 아닌 **실험용 사후 선택 조건**입니다. 핵심 하네스를 그대로 실행한 단일 조건 결과라고 표현하지 않습니다.

4번에서 primary 최고 후보가 다른 버전에 실패해 호환되는 c023을 선택했습니다.
이후 검증된 소스/로그/명령/계측 영수증만 재사용하고, 실패 버전이 나오면 나머지 버전 검사를 생략했습니다.
7번에서 반복적으로 실패한 버전을 먼저 검사하도록 CPU 검사 순서를 조정했으나 후보 순위·전체 버전 통과 조건은 유지했습니다.
환경 오류/timeout을 증명 실패로 간주해 다음 후보로 넘기지 않습니다.

8–10번은 시작 전에 중복 `original`/`reference` 중 `original`을 제거하고 공식 `version_info`를 추가했습니다.
원본·statement는 같지만 1–7번과 wire 입력이 동일한 조건은 아닙니다. 변경 hash와 범위는 `evidence/input-policy-update.json`에 보존했습니다.

### 7번 재실행과 점수순 호환성 검사

| 단계 | 모델 호출 / 계산 비용 | 결과 |
|---|---|---|
| 초기 실행 | 40 / $1.6265804 | 탐색 버전 유효 후보 15개가 필수 버전 검사에서 모두 탈락, 원본 유지 |
| 기존 best 재검증 | 0 / $0 | 732토큰 후보: 4.31.0 통과, 4.30.0 실패 |
| 독립 $2.50 재실행 | 40 / $1.6292248 | 공통 핵심 선택 함수·best 갱신·최종 저장 유지. best c039, 715토큰 |
| 새 best 사후 검사 | 0 / $0 | 4.31.0 통과, 4.30.0 실패. 이 단계에서는 best를 교체하지 않음 |
| 요청에 따른 순차 호환성 선택 | 0 / $0 | 유효 생성 후보 18개를 공통 점수순으로 검사, 모두 4.30.0 탈락. 19위 원본 c000이 두 버전 통과 |

재실행은 새 원본에서 시작했으며 이전 후보를 주입하지 않았습니다. `metrics/candidate/ranking/initial_state/advance`와 최종 selected 저장 부분을 main `a517db26…`와 AST로 비교했고, 실행 도중 핵심 파일이 바뀌지 않았음을 확인했습니다.
그 뒤 별도 순차 호환성 선택은 사용자 요청에 따라 적용했으며, 기존 `final-batch-next`의 **점수순 첫 전체 버전 통과 후보 선택**과 같은 방향입니다.
원본은 전체 순위 목록에 포함된 후보이며 생성 후보를 건너뛰는 조기 fallback이 아닙니다.
[evidence/problem07-ranked-checks.json](evidence/problem07-ranked-checks.json)에 전체 순위와 각 탈락 결과가 있습니다.

## 해석 범위와 다음 비교실험

이번은 하네스 연결과 실측 근거를 확보한 탐색적 파일럿입니다. 9/10 개선은 모델·피드백·Bank가 함께 있는 실행의 결과이며,
**Bank 자체의 인과 효과, 5개 대비 20개 Bank의 우위, retriever 개선 효과를 입증하지 않습니다.** Bank가 같은 Final 문제의 diff에서 도출됐으므로 독립 holdout이 아닌 final adaptation입니다.
8–10번 입력 보정과 사후 검증 컨트롤러 보완이 있어 엄밀한 비교실험의 한쪽 arm으로 그대로 재사용하지 않습니다.

다음은 보정된 공통 입력과 같은 선택/검증 정책을 사전 고정하고, **5개/20개 Bank × 기존/개선 retriever** 2×2를 실행하는 계획입니다.
문제·모델·reasoning·예산·호출 한도·top-k·seed·환경을 맞추고 반복/순서를 통제해야 합니다. Bank OFF arm은 Bank 자체 효과를 따로 보는 추가 조건입니다.
이번 비용에는 이 후속 비교실험을 실행한 금액이 없습니다.

## 파일·감사·재현

- `proofs/`, `originals/`, `diffs/`: 최종 선택과 원본의 정확한 선언 bytes. 7번 diff는 비어 있습니다.
- `results.json/csv`, `metrics-by-version.csv`, `submission.jsonl`: 10개 최종 파일·지표·문제별 예산 및 비용. JSONL은 로컬 export이며 공식 제출 완료를 뜻하지 않습니다.
- `bank/`: 실제 사용 20개 카드·관찰 링크, 참고용 기존 5개 카드. 카드별 독립 성과 인증이 아닙니다.
- `evidence/`: 3회 표본/버전·소스/로그 hash·호출별 usage와 계산 비용·설정·프롬프트·7번 순차 검사 요약. 절대 경로를 치환했고 API 키/원본 대화 전문은 제외했습니다.
- `runtime/`: 실행 코드·평가기 adapter·과거 driver와 단위 테스트. 과거 실험 스크립트의 로컬 홈 경로는 치환했으므로 그대로 유료 재실행하는 진입점이 아닙니다.
- `export_run.py`: 원래 로컬 아카이브를 읽기 전용으로 감사·추출합니다. 모델/Lean을 새로 호출하지 않습니다.
- `verify_public.py`: 공개 자료만으로 증명 hash·토큰·지표 산술·usage 기반 비용·예약 한도·manifest 일관성을 확인합니다. 공개 요약으로 원본 compiler 로그나 API 응답 본문 전체를 재감사할 수 있다는 뜻은 아닙니다.

원본 dataset SHA-256: `d53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682`.
완전한 새 실행에는 본인 API 키·새 run root·고정 라이브러리/빌드·환경 packet이 필요합니다. raw archive는 로컬에 보존돼 있습니다.

```sh
# 공개 자료 검사: API/Lean 호출 없음
python experiments/arklib-strategy-bank-pilot/verify_public.py
# 예산 경계/중복 전송/검증 캐시 변조/버전 검사 순서 테스트: API/Lean 호출 없음
python -m unittest discover -s experiments/arklib-strategy-bank-pilot/runtime/experiments/strategy-bank-pilot -p 'test_*.py'
# 공개 Bank 힌트/자기 문제 근거 제외 계약 검사
python -m unittest discover -s experiments/arklib-strategy-bank-pilot/tests
# 원래 아카이브에서 다시 감사·추출
python experiments/arklib-strategy-bank-pilot/export_run.py \
  --initial /path/to/initial-run --rerun /path/to/problem07-rerun \
  --ranked /path/to/ranked-checks --dataset /path/to/benchmark_data_final.jsonl \
  --output /path/to/new-export
```

이번 PR 준비에서는 유료 모델 호출이나 Lean 실행을 추가하지 않았습니다. 이전 로컬 전체 회귀 검사 339개(333 통과·6 skip)와 별개로,
이 패키지의 공개 자료 검사·포함된 오프라인 단위 테스트를 다시 실행합니다. 상세 원본 감사 결과는 `audit.json`에 있습니다.
