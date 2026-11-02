# 탐색용 단일 프로세스 검증

`fast_probe.py`는 기존 확정 평가기를 대체하지 않는다. 동결된 run의 adapter·원본·환경을 읽고, 같은 전체소스 동기 HB 측정 뒤에 타깃 공리 검사를 덧붙여 한 Lean 프로세스에서 실행한다. 기존 `state.json`, 후보 평가 receipt, baseline은 수정하지 않는다.

## 사용하는 이유

기존 후보 검증은 plain Check, 독립 Audit, Measure를 각각 새 프로세스로 실행한다. 탐색에서는 전체소스의 반복 로드가 큐를 길게 만든다. 단일 프로세스 탐색은 세 실행 중 두 번의 반복 로드를 줄이고, 최선 후보만 기존 평가기로 재검증한다. 큰 Lean은 동일한4GiB 독점 lease 아래 하나씩 실행한다.

## 증거의 단계

1. `fast-probes/*/result.json`의 `valid_fast=true`: 전체 프로세스 성공, fresh nonce HB 한 개, 허용 공리만 확인. **탐색용 잠정 결과**다.
2. frozen `search_exclusive4.py`의 Check + 별도 Audit +3회 Measure: 확정 후보용 근거다.
3. 요구 버전 전체 호환성: 제출 안전본으로 승격하기 위한 별도 근거다.

동일 프로세스 공리 검사는 독립 import Audit와 다른 증거다. fast 결과만으로 `validated/`에 넣지 않는다. 원본·seed 재초기화 없이 기존 같은환경 baseline을 탐색 순위의 기준으로 사용한다. 새 run이나 adapter 환경으로 바뀌면 baseline을 새로 확인해야 한다.

## 초기 교차 확인

P05의 이미 검증된419-token 후보를 그대로 넣었다. 기존 Measure raw8,224,894에 대해 fast raw8,224,897을 얻었다. 차이는3 raw이고, 전체 실행은20.86초였다. 이는 한 후보/한 환경에서의 초기 확인이며 모든 후보의 동등성을 일반적으로 증명한 것은 아니다.

이미 실패한 `finish-congr3` 후보는 raw HB marker가 출력되었음에도 returncode1로 정확히 거부됐다(`valid_fast=false`, `raw=null`). 로그에는 sorryAx도 나타나며 성공 결과로 선택하지 않았다. returncode가0이 아니거나 공리·nonce·환경·도구 해시가 일치하지 않으면 `valid_fast=false`이고 raw는 채택하지 않는다.

## 호출

```sh
python3 experiments/portfolio-94/fast_probe.py \
  runs/portfolio-94/p05-432 \
  experiments/portfolio-94/candidates/p05/trim-unused.lean \
  --label descriptive-name
```

다른 문제도 해당 frozen run과 그 환경에서의 전체 선언 후보를 전달한다. 결과를 비교해 유망한 후보를 선택한 다음 기존 runner로 확정한다. 실행 도중 이 파일의 의존 코드나 fast_probe.py를 수정하지 않는다.

P11도280-token 후보를 교차 확인했다. fast6,657,202에 대해 기존 독립3회 중앙값6,657,166으로 차이는36 raw였다. P05/P11 두 환경에서의 근접성은 확인했지만 최종 독립 검증 의무는 유지한다.
