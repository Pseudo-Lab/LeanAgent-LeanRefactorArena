# 첫 pilot의 부모 순서 수정

2026-10-25 10:47 UTC, 첫 P13-B 실행을 재생하면서 발견한 구현 결함을 수정했다.
당시 완료된 제안은 P01-A-r1 6개, P13-B-r1 6개, P01-B-r1 2개였다.
새 solver 배정을 잠시 멈추고 진행 중이던 solver도 현재 submit 이후에 대기시켰다.

## 원인과 영향

`parents` dictionary의 삽입 순서와 JSON의 key 정렬 순서가 달랐다.
예를 들어 메모리의 structure → representation → evidence 순서가 저장 후
evidence → representation → structure가 됐다. 요청의 alternatives는 list이므로
같은 후보 집합이어도 순서가 다르면 동일한 요청으로 볼 수 없다.
P13-B-r1의 기존 replay는 4번째 요청에서 이 차이로 실패했다.

평가 지표와 선택 상태는 일치했다. 그렇더라도 replay 실패를 무시하지 않고,
요청이 프로세스 경계를 넘어 동일하게 생성되도록 family 이름 정렬을 명시했다.
새 회귀 테스트는 최선 후보를 추가하는 경우와 비최선 부모를 추가하는 경우 모두에서
`packet(state) == packet(JSON roundtrip(state))`를 검사한다.

정렬은 마지막 세 family를 고르는 **앞**에서 일어난다. 따라서 아직 관측하지 않은
미래 상태에서는 순서뿐 아니라 노출되는 부모 구성도 바뀔 수 있다. 예를 들어 기존
representation/sharing/structure 뒤에 compression을 추가한 경우, 예전 방식은
sharing/structure/compression, 수정 방식은 representation/sharing/structure를 고른다.
이는 단순 표시 변경이 아니라 부모 선택을 결정적으로 만드는 정책 수정이다.
기존 요청 20개의 동일성이 미래 treatment 전체의 동일성을 증명하는 것은 아니다.

## 기존 측정을 보존한 방법

- 원래 trial의 code, manifest, 요청, 응답, 소스, 계측 로그를 수정하지 않았다.
- `policy.py`의 부모 순회 한 줄만 바꾼 사본과 bridge를 코호트의
  `amendments/canonical-parent-order/`에 별도로 고정했다.
- bridge는 자신과 정책의 SHA256을 검사하고, 정책 변경이 정확히 그 한 줄인지 확인한다.
  원래 worker의 평가·예산·선택·기록 코드를 그대로 호출한다.
- 당시 생성돼 있던 요청 **20개 전부**가 수정 정책과 동일함을 확인했다.
  비교 기록은 `existing-request-equivalence.json`에 있다.
- 완료된 P01-A-r1·P13-B-r1 모두 수정된 replay를 통과했다. 새 Lean 측정이나 모델
  재실행으로 결과를 바꾸지 않았다.
- 이후 A/B 모두 같은 bridge를 사용한다. 기존 P01-B-r1 solver는 자신의 3번째 요청부터
  계속하며, 6개라는 총 제안 예산과 원래 독립 실행 단위를 유지한다.
- bridge의 submit/finish 호출은 별도 invocation 로그로 남고, 집계기가 나머지 예산과 대조한다.

최초 고정 코드가 수정 없이 실험을 끝냈다고 주장하지 않는다. 이는 실행 중 발견한
정렬 결함에 대한 명시적인 수정이며, 모델에 이미 제공한 입력이나 관측 결과는 바꾸지 않았다.

## 실행 경로

새 코호트는 수정된 `policy.py`를 준비 단계에서 복사하므로 일반 `worker.py`를 쓴다.
이 첫 코호트는 보존된 구버전 스냅샷 대신 아래 entrypoint를 사용해야 한다.

```sh
python3 -B <cohort>/amendments/canonical-parent-order/canonical_order_bridge.py replay <trial>
```

submit과 finish도 같은 entrypoint를 사용한다. `report.py`는 이 수정이 있는 코호트에서
자동으로 bridge를 사용하고 기존 요청 hash·수정 코드 hash·후속 호출 수를 함께 감사한다.
