# 디스크 사전 검사 중단과 안전한 재개

2026-10-25 UTC, 공유 머신의 여유 공간이 1GiB 아래로 내려갔다. 기존 worker의
`evaluate()`는 코호트 Lean 잠금을 얻은 뒤 디스크를 확인하고, 부족하면 Lean을
실행하기 전에 중단한다. 이번 worktree 전체는 약 40MB였다. 다른 작업의 파일은
삭제하지 않았고 1GiB 기준도 낮추지 않았다.

## 복구 결과

공간 확보 후 두 저장 후보의 복구 평가를 완료했다. 원래 파일 hash와 완료된 복구 호출을 대조하는 감사도 통과했다. 동일한 solver가 다음 요청부터 이어서 진행했다. 아래 명령은 이미 실행된 절차이며 다시 실행하지 않는다.

## 중단된 두 후보

| 실행 | 저장된 후보 | 마지막 완료된 상태 |
|---|---:|---:|
| P01-B-r2 | 005 | 004 |
| P13-A-r2 | 004 | 003 |

두 pending step에는 `response.json`과 `candidate.lean`만 있고 `evaluation/`,
`event.json`, 다음 상태·요청은 없었다. 기존 worker가 응답 파일을 먼저 쓰기 때문에
같은 `submit`을 그대로 다시 호출하면 exclusive write에서 실패한다.

`runs/cost-hypothesis-pipeline/pilot-20261025/amendments/storage-preflight-recovery/`
아래에 복구 스크립트와 manifest를 별도로 고정했다. manifest에는 두 후보의 응답,
원래 요청, 이전 상태, 생성된 Lean 소스의 SHA256과 원래 실패 호출을 기록했다.

복구 스크립트는 다음을 확인한 후 기존 `evaluate()`부터 같은 후보를 이어서 평가한다.

- 고정된 복구 코드와 canonical bridge의 SHA256이 같다.
- pending 파일이 저장 당시와 같고, 이전 상태가 여전히 최신이다.
- 평가 폴더나 다음 상태가 없다. 이미 시작된 평가를 중복 실행하지 않는다.
- 원래 응답을 다시 파싱한 결과가 저장된 후보와 정확히 같다.

원래 trial 코드·manifest·응답·후보를 수정하지 않는다. 디스크 기준, 세 번의 계측,
피드백, 정책 전이, 예산은 그대로다. 실패한 사전 검사 호출은 남기며, 알려진 두
호출만 결과 감사에서 별도로 다룬다. proof 실패나 실제 Lean 평가 실패를 지우는
복구 방식이 아니다.

## 공간 확보 후 재개 순서

먼저 실제 여유 공간을 확인한다. 다음 두 명령은 coordinator가 **각각 한 번** 실행하고
완료까지 기다린다. 아래 경로는 worktree 루트 기준이다.

```sh
python3 -B runs/cost-hypothesis-pipeline/pilot-20261025/amendments/storage-preflight-recovery/resume_preflight.py runs/cost-hypothesis-pipeline/pilot-20261025/P01-B-r2
python3 -B runs/cost-hypothesis-pipeline/pilot-20261025/amendments/storage-preflight-recovery/resume_preflight.py runs/cost-hypothesis-pipeline/pilot-20261025/P13-A-r2
```

복구가 성공하면 같은 solver `/root/cost_p01_b_r2`에 `requests/006.json`,
`/root/cost_p13_a_r2`에 `requests/005.json`부터 계속하도록 알린다. 새 solver로
바꾸거나 pending 응답을 다시 생성하지 않는다. 이후 제출·finish·replay는 기존
`amendments/canonical-parent-order/canonical_order_bridge.py`로 실행한다.

두 실행 완료 후 계획된 순서대로 새 독립 solver에 P01-A-r2, P13-B-r2를 배정한다.
dispatch 로그에는 현재 두 실행을 아직 완료로 기록하지 않는다. 모든 Lean 작업이
끝난 후에만 runtime의 after inventory와 최종 report를 만든다.

복구가 다시 실패하면 기록을 보존하고 원인을 확인한다. 특히 `evaluation/`이 생긴
뒤의 실패는 이 사전 검사 복구 경로를 반복 호출해서 해결하지 않는다.
