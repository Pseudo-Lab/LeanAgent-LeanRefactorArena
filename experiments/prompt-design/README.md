# 프롬프트 설계

`p01-p05-reasoning-prompts.v4.en.json`은 `run.py`의 기본 프롬프트다. 구성은 다음과 같다.
- `common_prompt`: 공통 지시
- `case_prompts`: P01–P05 문제별 지시
- `controller_policy`: 실행기 쪽에 제안한 정책. 아직 구현되지 않았다.
- metadata: 근거 자료. 에이전트에는 전달되지 않는다.

v4가 v3에 더한 것은 다음과 같다.
- J 단위(`J = T + H/r`)와 토큰 계산 규칙
- `H/r`와 `T`를 비교해 길이와 HB 중 무엇을 줄일지 고르는 phase 규칙
- 경로 비교, 후반 블록 단위 최적화, lexical 선택지(`$`, 등식에 대한 `cases`, 이름 없는 `have` 등)

같은 조건(OpenAI, 문제당 $1.5)에서 v4는 v3보다 P01–P03 모두 좋았다. 88점 제출본을 넘은 것은 P03(74 / 229k) 하나다.
v1–v3 초안은 원본 작업 브랜치의 이력에 남아 있다.
