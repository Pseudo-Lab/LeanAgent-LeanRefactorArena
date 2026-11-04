# Strategy Retriever (규칙 기반)

원본 증명의 정적 특징으로 Strategy Bank에서 전략 2~3개를 골라 Planner 입력용 텍스트로 만든다. 모델 호출과 Lean 컴파일은 없다.

```sh
python experiments/strategy-retriever/retriever.py --jsonl benchmark_data_final.jsonl --out retrieved.json
python -m unittest discover -s tests -p 'test_strategy_retriever.py'
```

```python
from retriever import load_bank, retrieve, render
planner_text = render(retrieve(statement, original, load_bank(), k=3, problem=name))
```

| 파일 | 내용 |
|---|---|
| `features.py` | tactic 개수, 블록 종류 비율(#25 `proof-analyze`), 경로 단서(#36 `route_cue`), 태그 |
| `bank/strategies.json` | bank-v1, 전략 11개, Strategy Bank 제안서 스키마 |
| `retriever.py` | 태그·개수 조건 매칭, 상위 k개, 부족하면 일반 전략으로 채움 |

## Bank v1 출처

본선 문제의 증명은 쓰지 않고 웜업 자료만 사용했다. 각 전략의 `origin`에 출처가 있다.

- #36 type-hard-route 경로 메뉴
- #38 웜업 원본과 최종 제출 증명 비교에서 나온 패턴
- #43·#44 편집 패턴 표(`skills/lean-arena-harness/references/passes.md`)

## 매칭 규칙

- 검색 키는 원본 증명의 특징뿐이며 문제 이름은 쓰지 않는다.
- `all_tags`는 모두, `any_tags`·`tactic_min`은 하나 이상 만족해야 한다. 조건이 없는 항목은 일반 전략으로, 구체적인 전략이 k개보다 적을 때만 채운다.
- leave-one-out: 근거(`evidence.source_problem_ids`)가 지금 푸는 문제 하나뿐인 전략은 그 문제에서 제외한다.

## 적중 검증 (`eval/`)

실제로 효과가 있었던 전략을 Retriever가 고르는지 확인한다. Lean·모델 호출 없음.

```sh
python experiments/strategy-retriever/eval/evaluate.py --jsonl benchmark_data_final.jsonl
```

- 정답: 지연님 ArkLib·PutnamBench 20문제 리포트(main #60에 포함)의 문제별 실제 개선 내용을 bank S01–S09로 분류(`eval/ground_truth.json`). 분류는 Retriever 출력을 보기 전에 했고, 사람 검토는 아직이다.
- 비교: Retriever 상위 3개(일반 전략 S10·S11 제외), 문제와 상관없이 가장 흔한 3개를 고르는 고정 선택, 무작위 3개 기댓값.

| 방법 | 적중 (정답 전략 1개 이상 포함) |
|---|---|
| Retriever | 12 / 13 |
| 고정 선택 S05·S04·S06 | 12 / 13 |
| 무작위 3개 (기댓값) | 5.08 / 13 |

- Retriever는 고정 선택과 같은 결과다. 본선 증명은 길어서 `have_main`·`repeated_automation`·`repeated_blocks`·`simp_lists` 태그가 거의 모든 문제에 붙고, 20문제 중 19문제에서 S04를 고른다. 문제별로 구분하는 정보가 없다.
- 20문제 중 7문제는 bank의 어떤 편집에도 해당하지 않았다(새 수학 경로, 라이브러리 정리로 대체). 토큰 감소가 큰 putnam_1970_b5(−84%), putnam_1991_b1(−77%), putnam_1964_a4(−72%)가 여기에 속한다.
- 표본이 13문제로 작다.

판단: 현재 규칙으로는 공통 하네스 입력에 넣을 근거가 없다. 큰 감소는 원본 편집보다 경로 재구성에서 나왔다.

## 범위 밖

- Planner(#37·#40) 연결
- 전략별 효과 측정 (모든 전략 `status: provisional`)
