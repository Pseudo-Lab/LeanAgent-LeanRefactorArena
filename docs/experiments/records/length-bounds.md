# Final 길이 하한 정적 분석

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

고정 Final60문제의 로컬 토큰 계산과 by-only 후보 언어의 조건부 최소 길이를 분석한다.

## 확인된 결과와 해석

API·Lean·proof search 0회. 2토큰 floor는 각 문제가 2토큰으로 풀린다는 뜻이 아니며 최단 증명을 인증하지 않는다. term proof 허용 시 보편 하한도 아니다.

## 코드·Lean 보존 결정

정적 진단으로만 보존하고 공식 대회 전체의 최적성 주장으로 사용하지 않는다.


## 정적 분석의 출처

원본: `3ee67de:experiments/length-bounds/final60-length-bounds.json`. 고정 데이터셋 SHA256은 `d53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682`다. 제공 참조 길이의 합은 85,453, 로컬 tokenizer 합은 85,451이다. 이 차이와 text gate 제약 때문에 참조 길이를 공식 검증된 상한이나 문제별 최단 길이로 인증하지 않는다.
