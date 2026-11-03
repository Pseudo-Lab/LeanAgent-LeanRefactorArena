# 유형별 전략 힌트 비교 조건 (PR B)

블록 종류 비중으로 고른 전략 문장을 예산 제한 API 실행기(`experiments/openrouter-budget-trial/run.py`)에 넣었을 때, 힌트가 없을 때보다 나아지는지와 손글씨 힌트(v4)에 얼마나 가까운지 비교하기 위한 조건 파일임. 실행기 코드는 바꾸지 않고 `--prompt`로 넘기는 프롬프트 JSON만 다름.

웜업 15문제를 train으로 보고 비중 기준과 전략 문장을 정한 뒤, 본 대회 50문제(test)에는 문장을 고치지 않고 그대로 적용하는 것이 목표임.

## 비교 조건

다섯 조건 모두 v4의 `common_prompt`를 그대로 쓰고 `case_prompts`만 다름.

| 조건 | 프롬프트 파일 | 문제별 힌트 |
| --- | --- | --- |
| `common` | `prompts-common.en.json` | 없음 |
| `type-hard` | `prompts-type-hard.en.json` | 가장 큰 블록 종류 하나의 전략 문장 |
| `type-soft` | `prompts-type-soft.en.json` | 블록 종류 비중 + 25% 이상인 종류의 전략 문장 모두 |
| `type-hard-route` | `prompts-type-hard-route.en.json` | type-hard 문장 + 경로 단서 + 토큰 손익 문장. 아래 "P01 결과와 type-hard-route" |
| `v4` | `../prompt-design/p01-p05-reasoning-prompts.v4.en.json` | 손글씨 (기존 파일 그대로) |

## 블록 종류 비중과 전략 문장

[proof-analyze](../proof-analyze/README.md)의 분류를 씀. 블록을 첫 단어로 `case`, `calc`, `have`, 기타로 나누고 종류별 토큰 비중을 잼. 원본 증명만 읽으며 모델 호출과 컴파일은 없음.

비중을 힌트로 바꾸는 방식을 두 가지로 나눔.

- hard: 가장 큰 종류 하나를 유형으로 보고 그 전략 문장만 넣음.
- soft: 종류별 비중을 먼저 보여 주고 "비중에 따라 노력을 나누라"고 한 뒤, 비중이 25% 이상인 종류의 전략 문장을 비중 순서대로 모두 넣음.

| 종류 | 전략 문장의 내용 |
| --- | --- |
| case | 분기를 하나씩 고치기 전에, 여러 분기가 같은 남은 목표에 도달하는지와 다른 분할로 공통 규칙 하나가 여러 분기를 닫을 수 있는지 확인. 자기만의 논증이 필요한 분기만 따로 둠 |
| calc | 계산 단축 팁을 먼저 적용: 같은 계산이 반복되면 일반 등식 하나로 증명해 재사용, 여러 산술 단계는 `ring` 등식 하나로, 라이브러리 정리에 값을 직접 넣어 쓰기, 공통 지시의 lexical 옵션. 모든 것을 펼쳐 자동화에 맡기지 않기 |
| have | 뒤에서 실제로 필요한 `have`는 남기고, 쓰이지 않거나 한 번만 쓰이는 것만 지우거나 합침 |

영어 원문은 `make_prompts.py`의 `STRATEGY`에 있음. calc의 계산 팁은 Week 2에서 14·15번을 줄일 때 쓴 방법과 v4 공통 지시의 lexical 옵션을 합친 것임.

| 문제 | 비중 | 들어가는 문장 (soft) |
| --- | --- | --- |
| P01 | case 97.4% | case |
| P02 | case 91.4% | case |
| P03 | case 83.9%, have 9.4% | case |
| P04 | have 95.1% | have |
| P05 | calc 81.2%, have 11.5% | calc |
| (참고) 웜업 11번 | have 71.1%, calc 28.2% | have, calc |

### hard와 soft를 나눈 이유

처음 규칙은 비중 50% 이상인 종류를 유형으로 정하고 없으면 `mixed`로 두는 것이었음. 하지만 웜업 15문제는 모두 가장 큰 종류가 70% 이상이라 50% 기준을 train 데이터로 정하거나 검증할 수 없음. 하나로 자르면 경계 근처에서 힌트가 통째로 바뀌므로, 비중대로 섞는 soft 방식이 본 대회 문제가 웜업과 다를 때 덜 위험할 수 있음. 반대로 문장이 여러 개면 산만해질 수 있어 어느 쪽이 나은지는 비교가 필요함. hard는 50% 대신 가장 큰 종류를 쓰므로 `mixed`는 따로 두지 않음. 25%는 4주차 분류 v1의 보조 유형 기준이며, 이것도 데이터로 정한 값은 아님.

## P01 결과와 type-hard-route

빌더님이 P01에서 조건마다 한 번씩, 문제당 1.5달러로 실행한 결과임. 평가값은 원본 대비 토큰 비율과 HB 비율의 합이고 낮을수록 좋음.

| 조건 | 최선 | 평가값 | golf 후 |
| --- | --- | ---: | --- |
| v4 | 35토큰 / 1,653k | 0.431 | 29 / 1,551k, 0.392 |
| common | 82토큰 / 1,335k | 0.520 | 변화 없음 |
| type-hard | 101토큰 / 1,021k | 0.520 | 변화 없음 |

v4의 golf 결과는 `../proof-golf/README.md`의 값이고, common과 type-hard는 같은 golf를 Lean 4.26, Strata 451e5f0 환경에서 돌린 결과임. 후보가 각각 101개, 135개였고 모두 컴파일에 실패함.

type-hard는 case 전략 문장대로 공통 보조 정리를 만들어 HB는 가장 낮췄지만, 보조 정리 토큰이 붙어 길이가 늘었음. v4는 `substOld`의 정의를 따라 나누는 경로로 짧아졌음. 이를 반영해 `type-hard-route`를 만듦. 블록 종류를 고르는 규칙은 type-hard와 같고, 문장만 다음처럼 바꿈.

| 구분 | 내용 | 붙는 문제 (웜업) |
| --- | --- | --- |
| case 전략 | 기존 문장 + 분기를 나눈 뒤 `rfl`, `assumption`, `exact`, `simp only`처럼 가장 싼 방법으로 먼저 닫고, 모든 가정에 `simp_all`이나 `grind`를 거는 것은 나중에 | case 6문제 |
| have 전략 | 기존 문장 + 이름이나 값만 다른 주장, 대칭인 두 방향은 일반형 `key` 하나로 한 번 증명해 재사용 (Week 2의 14·15번 풀이) | have 7문제 |
| calc 전략 | 그대로. 이미 일반 등식 재사용, `ring` 하나로 합치기, 라이브러리 정리 직접 쓰기를 담고 있음 | calc 2문제 |
| 경로 메뉴 | 시도할 경로 2–3개를 순서대로 주고, 앞의 두 경로는 완성 후보를 하나씩 만들어 보게 함. 연속 3번 평가값이 내려가지 않으면 다음 경로로 넘어가게 함. 아래 표 | 전부 |
| 중복 위치 | analyze가 찾은 비슷한 블록의 줄 범위를 알려 주고 일반형 하나로 재사용을 고려하게 함 | 6, 9, 11, 12, 13, 14, 15번 |
| 평가값 기준 | 가장 짧은 증명이 최선은 아님. 보조 정리나 넓은 자동화는 한쪽 비율의 이득이 다른 쪽 손해보다 클 때만 | 전부 |

경로 메뉴에는 증명이 아니라 시도할 방향만 들어감.

| 유형 | 메뉴 순서 |
| --- | --- |
| case | 1. `f`의 정의를 따라 나누기 (`fun_induction f ...`). 원본이 `induction x`로 나누고 `f`를 펼치며 명제가 `f`를 `x`에 적용할 때만 붙음 (웜업 1, 2번) 2. 귀납 없이 문맥의 보조 정리로 바로 조립 3. 원래 분할을 유지하고 분기 합치기 |
| have, calc | 1. 중복 블록이 있으면 일반형 `key` 하나로 재사용 2. 긴 연쇄를 라이브러리 정리 하나나 싼 자동화 한 번으로 대체 3. 구조를 유지하고 단계별로 줄이기 |

### type-hard에서 달라진 점

빌더님이 P01에서 돌린 `type-hard`와 비교해 바뀐 것만 정리함. 블록 종류를 고르는 규칙, v4 공통 지시, `prompts-type-hard.en.json` 파일은 그대로임. `type-hard-route`는 새 파일 `prompts-type-hard-route.en.json`으로 따로 만듦.

| 항목 | type-hard (P01 실행) | type-hard-route |
| --- | --- | --- |
| case 전략 | 공통 규칙으로 여러 분기를 닫을 수 있는지 보라 | 같음 + 분기를 나눈 뒤 `rfl`, `assumption`, `exact`, `simp only`처럼 싼 방법으로 먼저 닫기 |
| have 전략 | 쓰이지 않거나 한 번만 쓰이는 `have`만 지우기 | 같음 + 이름이나 값만 다른 주장은 일반형 `key` 하나로 재사용 |
| calc 전략 | 계산 팁 4가지 | 같음 |
| 중복 위치 | 없음 | analyze가 찾은 비슷한 블록의 줄 범위 |
| 경로 메뉴 | 없음 | 시도할 경로 2–3개와 전환 규칙. P01에는 `fun_induction substOld`가 1번 경로로 붙음 |
| 평가값 기준 | 없음 | 가장 짧은 증명이 최선은 아님. 한쪽 비율의 이득이 다른 쪽 손해보다 클 때만 보조 정리나 넓은 자동화를 씀 |

P01에서 type-hard가 낸 증명은 `combine` 보조 정리로 HB를 가장 낮췄지만(1,021k) 토큰이 101개로 늘었고, 원래 `induction post`를 유지했음. 경로 메뉴와 평가값 기준 문장은 이 두 점을 겨냥함.

### API 없이 한 확인

P02에서 경로 단서대로 `fun_induction extractOldExprVars`로 나누고 일반적인 마무리만 붙인 증명을 직접 써서 컴파일함. 같은 Lean 4.26, Strata 451e5f0 환경임.

| 증명 | 토큰 | HB | 평가값 |
| --- | ---: | ---: | ---: |
| 원본 | 222 | 2,695k | 2.00 |
| 경로 단서를 따른 증명 | 38 | 2,001k | 0.914 |
| 그 증명에 golf | 36 | 1,991k | 0.901 |
| 참고: 빌더님 P02 API 최선, 2.5달러 | 120 | 499k | 0.726 |

경로 단서로 길이는 크게 줄지만, 모든 분기를 `simp ... at *`와 `grind`로 한꺼번에 닫아 HB가 높음. case 전략의 "싼 방법으로 먼저 닫기"와 평가값 기준 문장은 이 결과에서 나옴. 손으로 쓴 증명이라 모델이 같은 증명을 찾는지는 보여 주지 않음.

### Claude 근사 실험

API 없이 효과를 가늠하려고, 이전 대화와 결과를 모르는 Claude 하위 에이전트에게 실행기와 같은 입력을 주고 비교함. 조건마다 문제 입력, 문맥, 컴파일 도구(Lean 4.26, Strata 451e5f0), 시도 10번 제한이 같고 프롬프트만 다름. 숫자는 도구가 남긴 기록에서 확인함.

| 문제 | 조건 | 유효 시도 | 최선 토큰 | 최선 HB | 평가값 |
| --- | --- | ---: | ---: | ---: | ---: |
| P03 | common | 5번 중 4 | 76 | 203k | 0.383 |
| P03 | type-hard-route | 6번 중 5 | 77 | 200k | 0.387 |
| P01 | common | 8번 중 4 | 26 | 4,954k | 1.041 |
| P01 | v4 | 10번 중 6 | 26 | 4,030k | 0.862 |
| P01 | type-hard-route | 10번 중 8 | 28 | 2,192k | 0.513 |

- P03: 두 에이전트가 같은 경로(귀납 없이 `updatedStatesComm` 등으로 조립)를 스스로 찾아 차이가 없음.
- P01: common과 v4는 10번 모두 원래 `induction post`를 유지함. type-hard-route는 메뉴대로 `fun_induction substOld`를 먼저 시도하고 원래 분할과 비교한 뒤 돌아와 HB를 낮춤.
- 모델이 혼자 좋은 경로를 찾는 문제에서는 차이가 없고, 첫 경로에 갇히는 문제에서 메뉴가 효과를 낸 것으로 보임.

한계: GPT가 아니라 Claude가 읽었고, 조건마다 한 번씩임. 같은 v4 힌트로 GPT는 빌더님 실행에서 `fun_induction`을 찾아 0.431을 냈으므로 힌트 효과는 모델마다 다를 수 있음. P01은 경로 단서를 v4 결과를 보고 만든 문제이고, 메뉴의 "귀납 없이 조립"은 P03 결과를 보고 넣었음. GPT 실행으로 다시 확인해야 함.

### 주의

경로 단서는 P01, 분기 마무리 문장은 P02를 보고 만들었음. 그래서 경로 단서가 붙는 웜업 문제(1, 2번)는 이 조건의 효과를 판단하는 데 쓸 수 없음. 효과는 본 대회 문제에서 확인해야 함.

## 만들기

```bash
python experiments/analyze-prompts/make_prompts.py --packets experiments/problem-inputs \
    --base experiments/prompt-design/p01-p05-reasoning-prompts.v4.en.json --out experiments/analyze-prompts
```

## 실행 계획

이 PR에서 직접 비교 실행은 하지 않음. `run.py`가 리눅스·macOS 전용 기능(`fcntl`)을 써서 Windows에서 바로 돌릴 수 없어, 빌더님의 다음 실행에 조건을 끼워 넣는 방식으로 진행함.

- 1차(파일럿): P01에서 `common`과 `type-hard`를 같은 조건(백엔드 openai, 문제당 $1.5)으로 한 번씩 실행. `v4`는 빌더님이 같은 조건으로 이미 얻은 P01 결과를 참고값으로 씀. 한 번씩 돌린 결과이므로 효과를 판단하는 근거가 아니라 동작 확인과 첫 관찰로만 봄.
- 차이가 보이면 P03과 반복 실행으로 넓히고, 전략 문장을 고정한 뒤 held-out P05를 마지막에 한 번 돌림. P02는 type-hard-route를 만들 때 직접 컴파일해 봤으므로 이 조건에서는 held-out으로 쓰지 않음.
- hard 대 soft는 두 종류 이상이 25%를 넘는 문제(예: 웜업 11번)에서 비교함. P01–P05에서는 두 방식의 전략 문장이 같음.
- 본 대회 문제가 공개되면 문장은 고치지 않고, 50문제의 블록 종류 비중 분포를 웜업과 비교함. `profile.py`가 출처, 가장 큰 블록 종류, 그 비중, hard와 soft가 다른 문제 수, 원본 길이를 두 집합에서 나란히 보여 줌. 모델 호출과 컴파일이 없고 웜업 15문제 기준 1초 걸림.

```bash
python experiments/analyze-prompts/profile.py --train benchmark_data_warmup.jsonl \
    --test benchmark_data.jsonl --out runs/profile-main
```

실행 예시 (조건마다 새 폴더):

```bash
for c in common type-hard; do
  python experiments/openrouter-budget-trial/run.py prepare --output runs/analyze-prompts/$c-p01 \
    --problems P01 --backend openai --budget-usd 1.5 \
    --prompt experiments/analyze-prompts/prompts-$c.en.json
done
# 각 폴더: check (API 없음) → run (유료)
```

2차: P03, P04, P05처럼 경로 단서를 만들 때 보지 않은 문제에서 `common`과 `type-hard-route`를 같은 조건으로 한 번씩 실행하고, 각 최선 증명에 `../proof-golf/golf.py`를 돌린 뒤 평가값을 비교함.

```bash
for c in common type-hard-route; do
  python experiments/openrouter-budget-trial/run.py prepare --output runs/analyze-prompts/$c-p03-p05 \
    --problems P03 P04 P05 --backend openai --budget-usd 1.5 \
    --prompt experiments/analyze-prompts/prompts-$c.en.json
done
```

## 한계

- 전략 문장은 웜업을 본 뒤 씀. calc 팁은 Week 2의 14·15번 풀이에서 나왔고 14번은 held-out임(이번 대상 P01–P05와는 무관).
- P01–P05는 모두 한 종류가 81% 이상이고 나머지는 25% 미만이라 hard와 soft의 전략 문장이 같음. 현재 실행기 입력이 준비된 문제(P01–P05) 중에는 두 방식을 가를 문제가 없음.
- heartbeat는 분류에 쓰지 않음.
- P01 비교는 조건마다 한 번씩 돌린 결과라 효과를 판단하는 근거로는 약함.

코드는 Claude와 함께 작성.
