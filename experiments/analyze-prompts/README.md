# 유형별 전략 힌트 비교 조건 (PR B)

블록 종류 비중으로 고른 전략 문장을 예산 제한 API 실행기(`experiments/openrouter-budget-trial/run.py`)에 넣었을 때, 힌트가 없을 때보다 나아지는지와 손글씨 힌트(v4)에 얼마나 가까운지 비교하기 위한 조건 파일임. 실행기 코드는 바꾸지 않고 `--prompt`로 넘기는 프롬프트 JSON만 다름.

웜업 15문제를 train으로 보고 비중 기준과 전략 문장을 정한 뒤, 본 대회 50문제(test)에는 문장을 고치지 않고 그대로 적용하는 것이 목표임.

## 비교 조건

네 조건 모두 v4의 `common_prompt`를 그대로 쓰고 `case_prompts`만 다름.

| 조건 | 프롬프트 파일 | 문제별 힌트 |
| --- | --- | --- |
| `common` | `prompts-common.en.json` | 없음 |
| `type-hard` | `prompts-type-hard.en.json` | 가장 큰 블록 종류 하나의 전략 문장 |
| `type-soft` | `prompts-type-soft.en.json` | 블록 종류 비중 + 25% 이상인 종류의 전략 문장 모두 |
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

## 만들기

```bash
python experiments/analyze-prompts/make_prompts.py --packets experiments/problem-inputs \
    --base experiments/prompt-design/p01-p05-reasoning-prompts.v4.en.json --out experiments/analyze-prompts
```

## 실행 계획

이 PR에서는 비교 실행을 하지 않음. `run.py`가 리눅스·macOS 전용 기능(`fcntl`)을 써서 Windows에서 바로 돌릴 수 없어, 빌더님의 다음 실행에 조건을 끼워 넣는 방식으로 진행함.

- 1차(파일럿): P01에서 `common`과 `type-hard`를 같은 조건(백엔드 openai, 문제당 $1.5)으로 한 번씩 실행. `v4`는 빌더님이 같은 조건으로 이미 얻은 P01 결과를 참고값으로 씀. 한 번씩 돌린 결과이므로 효과를 판단하는 근거가 아니라 동작 확인과 첫 관찰로만 봄.
- 차이가 보이면 P03과 반복 실행으로 넓히고, 전략 문장을 고정한 뒤 held-out P02, P05를 마지막에 한 번 돌림.
- hard 대 soft는 두 종류 이상이 25%를 넘는 문제(예: 웜업 11번)에서 비교함. P01–P05에서는 두 방식의 전략 문장이 같음.
- 본 대회 문제가 공개되면 문장은 고치지 않고, 50문제의 블록 종류 비중 분포를 웜업과 비교함.

실행 예시 (조건마다 새 폴더):

```bash
for c in common type-hard; do
  python experiments/openrouter-budget-trial/run.py prepare --output runs/analyze-prompts/$c-p01 \
    --problems P01 --backend openai --budget-usd 1.5 \
    --prompt experiments/analyze-prompts/prompts-$c.en.json
done
# 각 폴더: check (API 없음) → run (유료)
```

## 한계

- 전략 문장은 웜업을 본 뒤 씀. calc 팁은 Week 2의 14·15번 풀이에서 나왔고 14번은 held-out임(이번 대상 P01–P05와는 무관).
- P01–P05는 모두 한 종류가 81% 이상이고 나머지는 25% 미만이라 hard와 soft의 전략 문장이 같음. 현재 실행기 입력이 준비된 문제(P01–P05) 중에는 두 방식을 가를 문제가 없음.
- heartbeat는 분류에 쓰지 않음.
- 비교 실행은 아직 하지 않음. 이 PR은 조건 파일과 생성 스크립트만 추가함.

코드는 Claude와 함께 작성.
