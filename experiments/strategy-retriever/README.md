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

## 범위 밖

- Planner(#37·#40) 연결
- 전략별 효과 측정 (모든 전략 `status: provisional`)
