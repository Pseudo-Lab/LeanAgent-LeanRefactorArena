# v5 공통 지침 연구

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

같은 원본·paired controls에서 공통 지침 세 조건을 준비하고, 별도로 local-agent 40회 탐색을 수행했다.

## 확인된 결과와 해석

유료 matched-arm 연구는 유예, API 비용 $0. 별도 P01–P03 local-agent 120후보 중 100유효·20실패, 평균 O는 6회 0.870857→40회 0.369471. 두 연구를 합쳐 유료 비교 성공으로 읽지 않는다.

## 코드·Lean 보존 결정

공통 지침 후보와 local-agent 관찰만 보존. 신규 유료 비교·기본 전략 채택 근거로 삼지 않는다.


## 시행 상태 근거

`study-manifest.json`의 상태는 `deferred_after_user_scope_correction`, `api_cost_usd`는 `0`, `paired_controls_verified`는 `true`다. 준비된 $13.50 총상한은 실제 사용액이 아니다.

원본 SHA256: `c5cdf0f7bf3207ab462ebf4ecead017f00603e1dfd808339d1e1a7c664f1378e`.
