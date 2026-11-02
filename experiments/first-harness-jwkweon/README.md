# 첫 하네스: 실행 일관성과 기록 재생

브랜치: `exp/first-harness-jwkweon`

단일 에이전트가 개선 후보 하나를 제안하고, 하네스가 검증·측정·선택하는 최소 실험입니다.
Python 표준 라이브러리만 사용합니다. 기본 실행은 **미리 작성한 응답 + 실제 Lean 검증**입니다.
고정 응답의 성공을 모델의 문제 해결 능력이나 대회 성능으로 해석하지 않습니다.

## 목적과 범위

고정 조건, 실행 중 상태, 통제되지 않는 측정 변동을 분리합니다.
한 번 실행한 기록을 모델이나 Lean을 다시 호출하지 않고 재생해,
동일한 문맥·상태 변화·후보 선택이 만들어지는지 확인합니다.

현재는 설치된 Lean의 기본 라이브러리만 쓰는 작은 예제를 지원합니다.
Mathlib 등 외부 의존성이 있는 문제는 준비·무결성 확인이 가능한 환경 어댑터를 추가한 뒤 연결합니다.
기존 검증기의 명제 보존·공리 검사·토큰 측정·fresh-process 검증을 재사용합니다.
그 출처와 변경 사항은 `evaluator/provenance.json`에 있습니다.

## 파이프라인과 코드 읽는 순서

```text
load_config → snapshot → fingerprint
  → 원본 검증·3회 측정 → initial_state
  → make_request → models.query → parse_proof
  → LeanEvaluator.evaluate → advance → 반복
  → 최선 후보 재검증 → summarize → seal

replay: 해시 확인 → 저장된 응답·검증 결과 로드
  → 요청·상태·종료 조건·최종 선택 다시 계산 → 원래 기록과 비교
```

| 책임 | 구현 |
| --- | --- |
| 독립 실행·스냅샷 | `harness.py`: `snapshot`, `run` |
| 프롬프트·문맥 구성 | `prompt.txt`, `harness.py`: `make_request` |
| 모델 연결 | `models.py`: `payload`, `query`, `receipt` |
| 후보 검증·측정 | `evaluator/lean.py`, `evaluator/tokens.py` |
| 상태·선택 | `harness.py`: `initial_state`, `advance`, `ranking` |
| 기록 재생 | `harness.py`: `check_artifacts`, `replay` |

## 고정 규칙과 변하는 상태

| 고정 규칙 | 실행 중 상태 |
| --- | --- |
| 문제·명제·원본 증명·문맥 | 새 후보, 후보별 검증 결과 |
| Lean toolchain·명령·자원 옵션·측정 횟수 | 컴파일 출력, heartbeat 표본·중앙값 |
| 프롬프트 원문·문맥 구성 규칙 | 최선 후보, 직전 후보·피드백 |
| 모델 ID·provider·생성 설정 | 실제 응답, 실제 provider·사용량·청구 비용 |
| 최대 호출 수·요청 크기·후보 크기 | 현재 단계·호출 수·남은 호출 수 |
| 후보 점수·동점 처리·종료 규칙 | 현재 최선 후보와 종료 이유 |

메모리는 문제·원본·기준 지표·최선 후보·직전 시도·피드백·남은 호출 수로 제한합니다.
전체 대화 이력을 계속 누적하거나 모델로 요약하지 않습니다.
모델에는 측정 중앙값을 전달하고 원시 표본은 기록에 보존합니다.
오류의 실행 경로는 `<RUN>`으로 정규화해 폴더 이름이 다음 프롬프트를 바꾸지 않도록 합니다.
새 실행은 비용·상태·작업 공간을 공유하지 않으며 기존 출력 폴더는 덮어쓰지 않습니다.

## 실행: 고정 응답 + 실제 Lean

아래 명령은 저장소 루트에서 실행합니다. Python 3.10 이상과
이미 설치된 `leanprover/lean4:v4.26.0`이 필요합니다. 하네스가 도구를 설치하지는 않습니다.

```sh
python3 experiments/first-harness-jwkweon/harness.py run \
  --config experiments/first-harness-jwkweon/configs/smoke.json \
  --output runs/first-harness-jwkweon/trial-01

python3 -B experiments/first-harness-jwkweon/harness.py replay \
  runs/first-harness-jwkweon/trial-01
```

예제는 `n + 0 = n`의 긴 원본 증명을 사용합니다. 고정 응답 3개는
컴파일 실패 → 유효한 개선 → `by rfl` 순서로 되어 있습니다.
호출 예산은 3회이며 후보마다 원래 문맥에서 컴파일한 뒤 계측 문맥에서 3회 측정합니다.
실제 모델 호출 수와 API 비용은 모두 0입니다. fixture의 토큰 사용량 0은 합성 값입니다.

독립 반복은 다른 출력 폴더로 동일 명령을 실행합니다. 실제 Lean 측정의 작은 변동은 숨기지 않습니다.
`final_median_matches_selection`과 `final_samples_match_selection`은 각각 중앙값과 전체 표본의 일치를 표시합니다.
이 둘이 다르더라도 컴파일·공리 검증의 성공 여부는 `final_valid`로 별도 확인합니다.

## 기록 구조와 재생 범위

```text
<run>/
├── manifest.json          # Git HEAD, 코드·입력 해시, 호스트, 실제 compiler 버전·해시
├── input/                 # 설정·문제·문맥·프롬프트·최소 Lean 프로젝트 복사본
├── code/                  # 실제 실행한 하네스·모델 어댑터·검증기 코드 복사본
├── baseline/              # 원본 검증과 raw heartbeat·공리·원문 로그
├── initial-state.json
├── steps/001/
│   ├── request.json       # 실제 API 요청 본문; 인증 헤더 제외
│   ├── response.json      # 원래 응답·usage·호출 ID
│   ├── candidate.lean     # 응답 형식이 올바른 경우
│   ├── evaluation/        # 후보별 Lean 소스·로그·결과
│   └── event.json         # 다음 상태와 응답 거절 사유
├── selected.lean
├── final/                 # 최종 선택 후보 재검증
├── summary.json
└── artifacts.json         # 산출물 목록과 SHA256
```

코드를 수정한 뒤 옛 실행을 재생하려면 보존된 코드를 실행합니다.
현재 코드가 다르면 일반 `replay`는 이를 안내하고 중단합니다.

```sh
python3 -B runs/first-harness-jwkweon/trial-01/code/harness.py replay \
  runs/first-harness-jwkweon/trial-01
```

기록 재생은 저장된 관측을 신뢰해 상태 전이와 선택을 검증하는 절차입니다.
Lean이나 모델을 다시 실행하지 않으며, proof validity를 새로 증명하는 절차도 아닙니다.
SHA256 목록은 손상·변경 확인용이지 작성자 인증이나 서명은 아닙니다.
로컬 전체 기록은 `runs/first-harness-jwkweon/`에 남고 Git에서는 제외합니다.
간결한 실행 검증 결과는 이 실험의 `validation.json`에서 확인합니다.

## 모델을 실제로 연결할 때

`configs/openrouter.example.json`을 같은 폴더의 로컬 설정으로 복사하고,
현재 사용 가능한 정확한 모델 ID와 provider slug, 생성 설정을 명시합니다.
API 키는 `OPENROUTER_API_KEY` 환경 변수로만 받습니다. `.env`를 자동 로드하지 않습니다.
키·인증 헤더는 실행 기록에 쓰지 않고 Lean 자식 프로세스에도 전달하지 않습니다.

실제 호출은 설정의 `backend`를 통해 명시적으로 선택합니다. 이 작업에서는 유료 API를 호출하지 않았습니다.
provider fallback과 자동 재시도를 끕니다. `seed`와 temperature 고정이 동일 응답을 보장하지는 않습니다.
거절된 모델 응답도 호출 횟수·비용에 포함합니다. `usage.cost`가 없거나 통신 결과가 불명확하면
`unknown_cost`로 중단하며, 비용을 0으로 간주해 계속 실행하지 않습니다.

**v1이 강제하는 예산은 호출 횟수와 요청·출력 크기입니다. 달러 비용의 사전 상한은 아직 구현하지 않았습니다.**
실제 비용은 응답의 usage와 함께 보존합니다. 대회용 실행에 사용하기 전에 호출별 비용 예약과 정산을 추가해야 합니다.
OpenRouter 어댑터는 요청 구성·오류 처리의 로컬 검증까지만 했으며 실제 서비스 연결 검증은 남아 있습니다.

## 평가·선택 규칙

`0.5 × (proof_tokens / baseline_tokens + raw_heartbeats / baseline_raw_heartbeats)`를 최소화합니다.
부동소수점 비교 대신 분모가 공통인 정수 분자
`tokens × baseline_raw + raw × baseline_tokens`로 비교합니다.
동점은 토큰 수, 선언 SHA256 순서로 결정합니다. 유효한 원본이 기본 fallback입니다.
무효 후보는 선택하지 않으며 최종 후보도 별도 재검증합니다.
로컬 점수·토큰 규약은 공식 대회 점수와 구분합니다.

## 확인한 동작과 남은 작업

```sh
python3 -m unittest discover -s experiments/first-harness-jwkweon -p 'test_*.py' -v
```

테스트는 Lean·API 없이 잘못된 후보 배제, 비용 미확정 중단, 요청·상태 일치,
실행 간 상태 분리, 기록 손상, 종료 조건 위조, 최종 재검증 실패 등을 확인합니다.
실제 Lean 통합 검증과 구체적인 수치는 `validation.json`을 봅니다.

첫 통합 검증에서는 독립 실행 2회가 모두 `by rfl`을 선택하고 최종 검증·기록 재생을 통과했습니다.
두 실행의 단계별 요청 본문도 모두 같았습니다. 원본은 14토큰, 최종 후보는 2토큰이었으며,
최종 재측정의 raw heartbeat 중앙값은 각각 23,213과 23,214였습니다.
고정 응답을 사용해도 측정값 전체가 비트 단위로 같지는 않았다는 관측입니다.
실제 모델의 성능 일관성을 입증하는 결과는 아닙니다.

하네스 테스트 17개는 모두 통과했습니다. 기존 저장소 테스트 15개 중 12개는 통과했고,
웜업 제출 관련 3개는 로컬 `benchmark_data_warmup.jsonl`이 없어 실행 오류가 났습니다.
해당 테스트·제출 exporter는 이 작업에서 변경하지 않았습니다.

P01·P13을 각각 두 번 실행하는 실제 서브에이전트 실험의 조건·어댑터·제약은
[서브에이전트 반복 프로토콜](subagent-trials.md)에 별도로 기록합니다.
[P13 예산 10회 실험](p13-budget10.md)은 새 에이전트 두 개로 후보 예산 증가 효과를 비교합니다.
두 실행의 탐색 중 최선은 개선됐지만 최종 재검증은 모두 시간 제한으로 실패했습니다.
[결과와 실패 기록](p13-budget10-results.json)을 함께 보존합니다.

다음 [프롬프트 개별 효과 실험 정의](prompt-ablation-v1/design.json)는 기존 A와 지침 하나씩 추가한
B1~B4를 비교합니다. 모든 실행의 예산은 10회이고 3·6·10회차의 누적 최선을 관측합니다.
프롬프트·입력 스냅샷을 저장했습니다. 2026-10-24 P13에서 조건당 두 번씩 총 10개 실행,
후보 100개를 완료했습니다. 최대 두 solver를 병렬 실행하고 빈자리에 다음 독립 실행을 배정했습니다.
이번 비교에서는 원본 기준값을 공통으로 고정하고 모든 조건에 검증 제한 420초를 적용합니다.
시작 전 두 병렬 환경의 원본 검증과 공유 컴파일러·라이브러리 95,212개 파일의 전후 해시 검사를 통과했습니다.
선택본 10개 모두 최종 검증과 기록 replay를 통과했고, 후보 80개가 유효했으며 20개는 일반 컴파일 단계에서 거절됐습니다.
[결과·반복별 수치·그래프](prompt-ablation-v1/results/README.md)에서 전체 비교를 확인할 수 있습니다.
이번 표본의 10회차 평균 비용은 A 0.147828, B1 0.144100, B2 0.111758, B3 0.149909, B4 0.134457이었습니다.
B2가 세 관측 회차 모두 평균 비용이 가장 낮았으며 10회차에서 A보다 24.40% 낮았습니다.
조건당 두 번의 결과이므로 통계적 우위를 입증한 것은 아닙니다.
원문 기록은 `runs/first-harness-jwkweon/p13-prompt-ablation-20261024/`에 보존합니다.

[P01 동일 프롬프트 실험](prompt-ablation-p01-v1/design.json)은 A·B1~B4의 프롬프트 바이트와
10회 예산·3/6/10회 관측·조건당 두 반복·최대 두 solver 실행 방식을 그대로 사용합니다.
P01의 Strata 원본 기준값은 313토큰 / 5,173,306 raw HB로 공통 고정했습니다.
총 10개 실행과 후보 100개를 완료했습니다. 67개 후보가 유효했고 33개는 증명 오류로 거절됐습니다.
최종 선택본 10개 모두 검증·replay를 통과했으며 timeout은 없었습니다.
원본 검증 두 환경과 공유 런타임 11,532개 파일의 전후 해시가 일치했습니다.
검증 전에 발생한 응답 경로 오타 1건은 후보·재검증을 추가하지 않고 수정했으며 별도 기록했습니다.
[P01 결과·반복별 편차·그래프](prompt-ablation-p01-v1/results/README.md)에서 비교를 확인할 수 있습니다.
10회차 평균 비용은 A 0.302901, B1 0.324489, B2 0.304787, B3 0.330444, B4 0.756616이었습니다.
B2는 6회차 평균이 가장 낮았지만 10회차에서는 A가 가장 낮았습니다. 조건당 두 번의 탐색 결과입니다.
원문은 `runs/first-harness-jwkweon/p01-prompt-ablation-20261024/`에 별도 보존합니다.
P01은 일부 지침을 도출할 때 사용한 개발 문제이므로 새로운 문제에 대한 일반화 검증으로 해석하지 않습니다.

[오류 피드백 구조화 실험](feedback-ablation-v1/README.md)은 P01·P13의 naive 프롬프트를 고정한 채
실패 컴파일의 피드백 선택·구조화 정책만 L/S로 비교합니다. 상한은 두 조건 모두 1,600자입니다.
문제별·조건별 두 번, 실행당 후보 10개로 총 8개 실행·80개 후보를 완료했으며 최대 두 solver를 사용했습니다.
63개 후보가 유효했고 17개는 컴파일 오류로 거절됐습니다. 선택본 8개 모두 최종 검증·replay를 통과했고
전체 기록 감사와 두 문제 런타임의 전후 해시 비교도 통과했습니다.
[결과·반복별 수치·그래프](feedback-ablation-v1/results/README.md)에서 확인할 수 있습니다.
P01의 3회차 개선은 L 0/2, S 1/2였지만 초반 유효 후보 수는 두 조건 모두 평균 1.5/3이었습니다.
P13의 3회차 개선은 두 조건 모두 2/2였습니다. 10회차 평균 비용은 P01 L 0.418380·S 0.358837,
P13 L 0.119328·S 0.140107로, 구조화 조건이 두 문제에서 일관되게 개선되지는 않았습니다.
사용량 제한으로 중단된 두 실행은 같은 solver 문맥에서 예산 추가 없이 재개했고 사건 기록을 보존했습니다.
원문은 `runs/first-harness-jwkweon/feedback-ablation-20261025/`에 별도 보존합니다.

이 구현은 로컬 학습·기능 실험입니다. 프로세스·OS 수준의 파일·네트워크 격리는 아직 없습니다.
금지 구문 검사와 환경 변수 제한은 격리의 대체가 아닙니다.
공유 Lean 설치·표준 라이브러리의 불변성을 OS 수준으로 보장하지도 않습니다.
외부 의존성 고정, 달러 예산 예약, 불명확한 요청의 조정과 중단·재개,
직접 API 어댑터에서 모델 설정까지 고정한 독립 반복 성능 비교는 후속 작업입니다.

## 참고

- [기존 아키텍처 초안](../../docs/architecture.md)
- [OpenRouter 요청 형식](https://openrouter.ai/docs/api_reference/overview)
- [OpenRouter 사용량·비용](https://openrouter.ai/docs/cookbook/administration/usage-accounting)
- [OpenRouter provider 고정](https://openrouter.ai/docs/guides/routing/provider-selection)
