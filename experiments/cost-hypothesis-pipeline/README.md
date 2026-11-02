# 비용 가설과 후보 선택 정책

공통 하네스의 후보 평가·순위를 사용하는 순수 상태 정책과 비교용 prompt를 보존한다.
부모 후보·T/H Pareto·경로별 최선·중복 후보·단계별 입력을 구성하며 직접 모델이나 Lean을 호출하지 않는다.

- `policy.py`: 상태 전이, 부모/Pareto 후보와 단계별 입력.
- `prompts/control.txt`, `prompts/treatment.txt`: 비교 조건의 지침.
- `test_policy.py`: 후보 선택·부모 보존·중복 측정·결정적 입력의 회귀 검사.

```sh
PYTHONPATH=src python3 -B -m unittest discover \
  -s experiments/cost-hypothesis-pipeline -p 'test_*.py' -v
```

과거 실험 준비기·수동 worker·보고서·복구 패치·결과 파일은 업로드 대상에서 제외했다.
그 기록은 원본 커밋 `3ee67de1707d712321e403da5cf1d064dc4240f9`에 남아 있다.
이전 동결 실행을 새 정책 코드로 덮어쓰거나 재생하지 않는다.

현재 단계 선택은 과거 파일럿의 단순 규칙이다. 새 공통 하네스의 넓은 탐색·합류·
환율 기반 전환 정책이 완성됐다는 뜻은 아니다.
