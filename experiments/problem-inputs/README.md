# 문제 입력 묶음

`PXX/agent-input.json`(문제, 문맥, 문제별 전략 문장)과 `PXX/original.lean`(원본 선언)은 기계와 무관하다.
문맥은 정리 직전까지의 관련 정의와 API 시그니처를 손으로 고른 것이다. 88점 제출본이나 이전 후보는 넣지 않았다.
P01–P03 묶음은 v4 실행에 쓴 입력이고, P04·P05 묶음은 프롬프트 실험에 쓴 입력이다.

`environment.json`은 Lean 경로가 들어가므로 커밋하지 않는다. `make_environment.py`로 각 기계에서 만든다.
만드는 방법은 [lean-proof-shortening skill](../../skills/lean-proof-shortening/SKILL.md)의 2절에 있다.
