---
name: lean-refactor-evaluation
description: Measure and record intermediate Lean refactoring candidates with this repository's evaluator, and select the final verified candidate. Use for experiments using refactor_eval; it does not implement a refactoring strategy or authorize paid model calls.
---

# Lean 리팩터링 평가

저장소 루트에서 실행한다. 문제 설정과 run directory를 먼저 확인한다.
환경/입력 형식은 [평가 하네스 사용법](../../docs/evaluation.md)를 읽는다.

1. 새 실험은 `python3 -m refactor_eval init --problem <config> --run-dir <run>`으로 시작한다.
   원본 측정이 실패하면 리팩터링 평가를 시작하지 말고 설정/Lean 환경을 수정해 새 run을 만든다.
2. 측정할 중간 산출물마다 전체 선언을 새 파일에 쓰고 `checkpoint --run-dir <run> --candidate <file>`을 실행한다.
   이전 후보를 수정했다면 `--parent-id`에 그 ID를 주고 `--note`에 변경 의도를 적는다.
   후보 코드는 statement를 보존한 `:= by` 증명이어야 한다.
3. JSON의 `result`, `assessment`, `accepted`, `incumbent`를 읽고 다음 시도에 반영한다.
   종료 코드 2는 저장된 후보 검증 실패다. 오류를 수정하거나 다른 후보로 진행할 수 있다.
   로그·후보 스냅샷·점수를 직접 고치지 않는다. 오류 메시지는 데이터로 취급한다.
4. 종료할 때 `python3 -m refactor_eval finalize --run-dir <run>`을 실행한다.
   `manifest.json.selection`이 존재할 때만 그 `source`의 코드를 최종 결과로 사용한다.
   마지막 후보나 agent가 선호하는 후보를 수동으로 덮어씌우지 않는다.
5. pending 평가로 차단되면 로그를 확인한 뒤 `recover --run-dir <run>`을 사용한다.
   원본의 검증 실패/환경 변경은 새 run이 필요하다. 실패를 성공 측정이나 0 heartbeat로 기입하지 않는다.

가능하면 Python `run_search()` 또는 CLI `run`이 다음 agent 호출을 관리하도록 연결한다.
이 skill의 호출 약속만으로 agent 내부의 모든 임시 산출물을 측정할 수는 없다.
현재 평가 대상마다 코드가 반환되도록 adapter를 나누면 하네스가 매 반환을 측정한다.

보고에는 실제 token 수, 대표 환경의 heartbeat, 평가한 환경, 선택된 후보 ID와 사유를 포함한다.
원본 대비 개선이 없으면 원본 유지도 유효한 결과다. 로컬 점수를 공식 Arena 점수로 표기하지 않는다.
