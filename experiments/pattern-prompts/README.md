# 공통 패턴 기반 힌트 조건 (pattern)

토큰 수 감소를 겨냥한 조건임. 웜업 리더보드에서 상위 7팀의 HB 감소율은 88.8–90.8%로 거의 차이가 없었고, 순위는 길이 감소율(85–92%)이 갈랐음. 그래서 문제 유형이 달라도 반복되는 증명 단축 패턴을 뽑아 토큰 수를 줄이는 데 초점을 둠. 다만 우리 팀은 HB 감소율도 84.6%로 상위권보다 낮으므로, 평가값 기준 문장은 그대로 둬서 HB를 늘리는 단축은 피하게 함.

[analyze-prompts](../analyze-prompts/README.md)의 type-hard와 다른 점은 블록 유형을 쓰지 않는다는 것임. 원본 증명에서 패턴의 신호가 보이면 그 패턴 문장을 붙임. 실행기 코드는 바꾸지 않고 `--prompt`로 넘기는 프롬프트 JSON만 다름.

## 패턴을 뽑은 방법

웜업 15문제의 원본과 팀의 88점 제출본(빌더님이 10월 28일 공유한 `submission.jsonl`)에서 신호 전술의 개수를 셈. `mine_patterns.py`가 [mined.md](mined.md)를 만듦. 빌더님 보고서의 문제별 "최종 후보의 핵심" 설명도 함께 봄.

| 패턴 | 원본 → 최종에서 보인 변화 | 나온 문제 |
| --- | --- | --- |
| 기존 정리로 대체 | 원본이 직접 증명하던 내용을 정리 하나로 | 2, 3, 4, 9, 12, 13, 14, 15 |
| `have` 연쇄 제거 | 4번 25→2, 10번 28→3, 11번 27→2, 12번 22→1, 13번 55→2, 14번 83→0, 15번 76→3 | 4, 10–15 |
| 넓은 자동화 축소 | `simp_all` 1번 20→0, 2번 10→0, 13번 13→0, 14번 16→0. `omega` 10번 27→1, 11번 40→1 | 1, 2, 3, 6, 10, 11, 13, 14 |
| 결합자로 한 번에 닫기 | 분기마다 쓰던 것을 `<;>`, `all_goals`, `first`, `repeat`로 | 7, 8, 9 |
| 정의를 따라 나누기 | `induction` 뒤 함수 펼치기를 `fun_induction`으로 | 1, 2 |
| 탐색 대신 정확한 형태 | 증인, 정규화 순서, 범위를 명시. `decide`를 기존 정리로 바꿔 HB 97% 감소 | 5, 6, 8, 10 |

5번은 `have`가 4→11로 늘어난 예외임. 전술 개수는 대략적인 신호임.

## 붙이는 규칙

`make_pattern_prompts.py`가 원본 증명과 명제 텍스트만 읽음. 구체적인 신호를 먼저, 일반적인 "기존 정리로 대체"를 마지막에 둠.

| 순서 | 패턴 | 신호 |
| ---: | --- | --- |
| 1 | 정의를 따라 나누기 | `induction x` 뒤 `f`를 펼치고 명제가 `f`를 `x`에 적용 (analyze-prompts의 `route_cue`) |
| 2 | `have` 연쇄 제거 | `have` 5개 이상 |
| 3 | 넓은 자동화 축소 | `simp_all`, `omega`, `linarith`, `grind`, `aesop`, `norm_num` 중 하나가 5번 이상 |
| 4 | 탐색 대신 정확한 형태 | `decide`, `calc`, `norm_num`이 있음 |
| 5 | 결합자로 한 번에 닫기 | `case`와 `cases`가 합쳐 4번 이상 |
| 6 | 기존 정리로 대체 | 항상 |

뒤에 "앞의 두 패턴은 완성 후보를 하나씩 만들어 볼 것, 연속 3번 평가값이 안 내려가면 다음으로"와 평가값 기준 문장을 붙임. 웜업 15문제에서 붙는 패턴 수는 문제당 2–4개임.

## Claude 근사 실험

[analyze-prompts의 근사 실험](../analyze-prompts/README.md)과 같은 방식임. 이전 결과를 모르는 Claude 하위 에이전트에게 같은 입력, 같은 컴파일 도구(Lean 4.26, Strata 451e5f0), 시도 10번을 줌. 실험에 쓴 문제별 문장은 `prompts-pattern.en.json`과 같음을 확인함.

| 문제 | common | v4 | type-hard-route | pattern |
| --- | ---: | ---: | ---: | ---: |
| P01 | 1.041 | 0.862 | 0.513 | 0.588 |
| P03 | 0.383 | - | 0.387 | 0.398 |

- P01: pattern도 첫 시도부터 `fun_induction`으로 경로를 바꿨고, 24토큰으로 네 조건 중 가장 짧았음. type-hard-route와의 차이는 마무리의 HB(2,192k 대 2,647k)에서 남.
- P03: 네 조건 모두 귀납 없이 `updatedStatesComm`으로 조립하는 같은 경로를 찾아 차이가 없음.
- 유형 분류 없이도, 원본 신호를 보고 구체적인 다음 수를 알려 주면 경로 고착이 풀린 것으로 보임.

한계: GPT가 아니라 Claude가 읽었고 조건마다 한 번씩임. 정의를 따라 나누기는 P01에서 v4 결과를 보고 만든 신호임. 패턴은 웜업 최종 증명에서 뽑았으므로 웜업 문제로는 효과를 판단할 수 없고, 본 대회 문제에서 확인해야 함.

## 만들기

```bash
python experiments/pattern-prompts/mine_patterns.py --originals benchmark_data_warmup.jsonl \
    --final submission.jsonl --out experiments/pattern-prompts/mined.md
python experiments/pattern-prompts/make_pattern_prompts.py --packets experiments/problem-inputs \
    --base experiments/prompt-design/p01-p05-reasoning-prompts.v4.en.json --out experiments/pattern-prompts
```

`make_pattern_prompts.py`는 `../analyze-prompts/make_prompts.py`의 `route_cue`와 평가값 기준 문장을 불러 씀. 그래서 PR #36에 의존함.

## 실행 계획

본 대회에서 `common`, `type-hard-route`, `pattern`을 포트폴리오로 두고, 문제마다 평가값이 가장 좋은 증명을 고름.

```bash
python experiments/openrouter-budget-trial/run.py prepare --output runs/pattern-prompts/p01 \
    --problems P01 --backend openai --budget-usd 1.5 \
    --prompt experiments/pattern-prompts/prompts-pattern.en.json
```

코드는 Claude와 함께 작성.
