# 공통 행동 프로토콜 예시

`actions-v1`의 검색·조회·제안·후보 계보·실패 부모 편집·종료를 확인하는 고정 입력이다.
문제·Lean 문맥은 `examples/first-harness`를 공유한다.

- `prompt.txt`: 공통 행동 지침. Final 배치도 이 지침에 문제 문맥을 추가한다.
- `corpus.json`: 작은 검색·inspect 대상.
- `responses.json`: 도구 조회, 실패 proof와 편집, 다른 부모의 후보, 종료를 포함한 합성 응답.
- `configs/actions-smoke.json`: 공통 runner로 실행하는 설정.

```sh
PYTHONPATH=src python3 -B -m lean_agent run --config configs/actions-smoke.json --output runs/actions-smoke
PYTHONPATH=src python3 -B -m lean_agent replay runs/actions-smoke
```

이 명령은 실제 Lean이 필요하다. API 호출이나 별도 실험 실행기는 사용하지 않는다.
Lean 없이 제어·기록 계약을 검사하려면 `scripts/check_common_harness.py`를 실행한다.
scout→merger 예시는 `configs/portfolio-smoke.json`을 사용한다.

이전 비교 실행기와 구형 정책은 Git 이력 `6cd8ba7`에 보존한다.
여기서 `repair`는 모델이 실패 proof를 편집하는 행동이며 native AutoSolver는 후속 PR 대상이다.
