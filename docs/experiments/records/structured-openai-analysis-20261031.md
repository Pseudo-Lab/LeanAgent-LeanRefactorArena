# 구조화 API 사후 분석

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

동결된 v6 API 실행과 사후88참조를 재집계해 점수 차이·문맥·비용을 진단한다.

## 확인된 결과와 해석

새 API·Lean 호출0. 호환성100% 가정의 평균점수 차이5.554732점 중 길이71.21%,HB28.79%;golf 이득0.039882점. 무작위 ablation이 아니다.

## 코드·Lean 보존 결정

입력 파서·반복 실패·예산 진단을 다음 설계에 활용한다.


## 사후 집계

| 항목 | 값 |
| --- | --- |
| `paid_API_calls` | 0 |
| `additional_Lean_calls` | 0 |
| `total_score_gap_points` | 5.554732281915513 |
| `length_component_points` | 3.9552858364486863 |
| `HB_component_points` | 1.599446445466826 |
| `golf_score_gain_points` | 0.03988203234844834 |
| `preflight_cost_usd` | 3.4572873 |
| `top_four_problems` | ['P07', 'P11', 'P10', 'P12'] |

입력 추출은 타입 안의 `:=`를 선언 본문의 시작으로 오인해 `let`을 포함하는 타입을 잘랐다. 원본 로그를 읽은 진단이며 수정 후 성능의 인과적 검증은 아니다.

원본: `runs/structured-openai-analysis-20261031/analysis.json`, SHA256 `6b1626fbe12f2f14705f740fb4f7720ea26e783b94c3be562c33c0d8c6227245`.
