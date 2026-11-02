# 비교해 볼 모델

2026-11-01에 [OpenRouter 공식 모델 목록](https://openrouter.ai/api/v1/models)에서 아래 세 ID와 입력·출력 토큰 단가가 각각 0인 것을 확인했다. 실행 시점의 제공 여부·가격은 다시 확인한다. 용도는 비교 실험 제안이며 Lean 성능 순위나 검증 결과가 아니다.

| 모델·공식 링크 | 정확한 모델 ID | 비교할 용도 |
|---|---|---|
| [Nemotron 3 Ultra (free)](https://openrouter.ai/nvidia/nemotron-3-ultra-550b-a55b:free) | `nvidia/nemotron-3-ultra-550b-a55b:free` | 다른 증명 경로·편집 전략 제안 |
| [North Mini Code (free)](https://openrouter.ai/cohere/north-mini-code:free) | `cohere/north-mini-code:free` | 하네스의 Python 코드·오류 처리·자동화 코드 비교 |
| [Gemma 4 31B (free)](https://openrouter.ai/google/gemma-4-31b-it:free) | `google/gemma-4-31b-it:free` | 오류 설명·국소 수정 후보 비교 |

실험 설정에 선택한 ID를 명시한다. 이 참고 목록은 기존 모델 설정이나 기본 모델을 바꾸지 않는다. 비교할 때는 같은 개발용 입력·문맥·프롬프트와 명시한 호출/출력·시간 제한을 사용하고, 실제 Lean 결과·채택 여부·토큰·HB·사용량·시간을 기록한다. 모델 응답을 성공한 증명으로 간주하지 않는다. 평가 자료의 구분은 [evaluation.md](evaluation.md)를 따른다.

이 문서를 작성하며 수행한 것은 공식 페이지와 모델 메타데이터 조회다. 모델 생성 요청이나 Lean 성능 측정은 실행하지 않았다. 무료 경로를 사용할 수 없으면 중단 사유를 기록하고, 유료 모델로 자동 교체하지 않는다.
