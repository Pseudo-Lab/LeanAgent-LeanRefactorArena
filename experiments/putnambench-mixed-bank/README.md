# PutnamBench 혼합 Strategy Bank 실험 — 중간 확정 결과

2026-11-03에 실행한 PutnamBench 10문제 실험의 **최종 검증 완료 6문제**를 먼저 공유합니다.
진행 중인 F057–F060은 점수 표와 proof export에서 제외했습니다. 나머지는 각 문제의 최종
검증·비용 정산이 끝난 뒤 **이 PR 브랜치의 후속 커밋으로 보강**합니다. 이 자료는 부분 결과이며
10문제 전체 제출물이 아닙니다. 대회에 제출하거나 공식 서버에서 채점한 결과도 아닙니다.

## 확정 증명과 결과

`.lean` 파일은 정리 선언 전체를 담은 **replacement declaration**입니다. 독립 실행 모듈이
아니므로 원본의 지정 header·소스 문맥과 toolchain에서 검증해야 합니다.
`submission.partial.jsonl`은 확정 문제만 포함하는 로컬 부분 export입니다.

| 문제 / 증명 | 토큰 원본 → 최종 | Raw HB 원본 → 최종 | 버전 호환성 | 종합 점수(로컬 추정) | 토큰 감소율 | HB 감소율 | 사용 비용 / 종료 기준 | API 호출 |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| [putnam_1964_a4](proofs/putnam_1964_a4.lean) | 1,769 → 186 | 111,470,971 → 3,116,088 | v4.26.0, v4.27.0 전부 통과 | 95.5634 | 89.49% | 97.20% | $2.4391398 / $2.50 | 102 |
| [putnam_1995_a3](proofs/putnam_1995_a3.lean) | 4,085 → 410 | 14,127,586 → 1,762,265 | v4.26.0, v4.27.0 전부 통과 | 92.4965 | 89.96% | 87.53% | $2.5345832 / $2.50 | 82 |
| [putnam_1988_a2](proofs/putnam_1988_a2.lean) | 2,162 → 224 | 58,090,725 → 4,574,665 | v4.26.0, v4.27.0 전부 통과 | 93.9214 | 89.64% | 92.12% | $1.4621914 / $2.50 | 63 |
| [putnam_2001_b1](proofs/putnam_2001_b1.lean) | 3,178 → 213 | 50,251,248 → 3,960,512 | v4.26.0, v4.27.0 전부 통과 | 95.1388 | 93.30% | 92.12% | $1.9696948 / $2.50 | 70 |
| [putnam_1964_b2](proofs/putnam_1964_b2.lean) | 1,754 → 91 | 134,489,543 → 667,679 | v4.26.0 전부 통과 | 98.1051 | 94.81% | 99.50% | $2.5127760 / $2.50 | 112 |
| [putnam_2007_a1](proofs/putnam_2007_a1.lean) | 5,464 → 437 | 528,106,386 → 11,335,613 | v4.26.0, v4.27.0 전부 통과 | 96.6186 | 92.00% | 97.85% | $2.445598 / $2.50 | 57 |

확정 6문제 비용 합계 **$13.3639832**, 평균 점수 **95.3073**입니다.
진행 중 문제의 비용, Bank 작성 비용, 이전 실행 비용은 이 합계에 포함하지 않았습니다.

점수는 기존 레포의 `solutions/final20/README.md`와 같은 방식으로, 지정 버전 모두 통과한
경우 `100 - (100/3) × (T/T0 + H/H0)`로 계산합니다. 감소율은 각각
`100 × (1 - T/T0)`, `100 × (1 - H/H0)`입니다. 버전 통과율은 100%이며, 호환성 몫을
포함한 동일식을 적용했습니다. 공식 worker와 동일하다는 인증이나 Bank의 인과 효과는 아닙니다.
HB는 raw 카운터이며 벽시계 시간이 아닙니다. 대표 HB는 각 문제의 첫 지정 버전입니다.

## 실험 목적과 하네스 보강

기존 actions-v1 생성·수리·검증·best-proof·비용 장부에 선택적 Strategy Bank를 연결합니다.
임베딩·학습 없이 텍스트/정규식 신호로 최대 3개 카드를 추천하고, 추천 ID와 선택 선언,
후보 작성, Lean 검증을 분리해 기록합니다. `strategy_ids`는 실제 적용의 증명이 아닙니다.

이번 보강은 Bank가 탐색을 좁힐 가능성을 고려한 **alternating-v1**입니다.
각 scout/merge 문맥에서 첫 후보는 `free`, 이후 생성 또는 수리 후보가 생길 때마다
`guided`와 교대합니다. 도구 검색·분석 호출은 교대 횟수에 포함하지 않습니다.
실패 후보와 repair도 한 후보로 계산합니다. 원본을 숨기는 scout-a에는 항상 Bank를 차단합니다.
free 요청은 Bank 카드·신호와 과거의 명시적 전략 이름/ID를 제거하지만, 이미 생성된 증명과
검증 피드백은 공유합니다. 독립 초기화나 편향 제거를 보장하지 않습니다.
기존 설정에서 정책을 지정하지 않으면 이전 guided 동작을 유지합니다.

- Bank: `dashboard-mechanisms-v2-team-1`, 20개 카드, top_k=3, contextual=true.
- 카드 모두 `review_required`; 사람의 승인이나 독립 효과 측정을 주장하지 않습니다.
- 현재 최선 증명으로 추천하며 최근 proof_rejected에 선언된 ID는 추천에서 제외합니다.
- 성능 학습·성공률/버전 가산점·적응형 혼합 비율은 추가하지 않았습니다.
- 별도의 Planner–Worker 구조를 새로 추가한 것은 아닙니다.

## 실행 계획과 현재 범위

1. 고정 데이터의 F051–F060, `source=putnambench` 원본에서 시작합니다.
2. Bank/코드/설정/모델/가격을 고정하고 혼합 정책 **한 조건만** 실행합니다.
3. scout-a/b/c 각 6개, merge 22개 평가 한도를 사용합니다. 도구 호출은 평가 한도를
   소비하지 않지만 API 비용은 소비합니다. 첫 성공 이후에도 예산 또는 할당량까지 탐색합니다.
4. 원본 비교 기준은 사전 오프라인 준비에서 검증한 원본 3회 HB 측정과 호환성 자료를
   재사용했습니다. 새로 생성한 후보나 모델 이력을 재사용하지 않았습니다.
5. 최종 후보는 지정 버전 전부 검증하고 대표 버전에서 **새로운 3회 HB 측정** 후 확정합니다.
6. 확정된 문제만 proof와 표에 추가합니다. F057–F060은 후속 커밋으로 추가합니다.

모델은 **OpenAI direct `gpt-6.1-sol`, reasoning high, seed 42**, 직렬 worker 1개입니다.
문제당 종료 기준은 **$2.50**으로 마지막 호출이 초과할 수 있으며 hard cap이 아닙니다.
비용은 응답 토큰 사용량 × 고정 공시 단가로 계산하며 청구서 대조 전입니다.
가격표는 `pricing.json`, 세부 호출별 토큰/비용 근거는 `evidence/*/costs.json`에 있습니다.
OpenRouter 요청은 이 결과에 포함하지 않았습니다. 초기 잘못된 transport의 연결/401 실패는
별도 로컬 실행에 보존돼 있으며 이 직접 API 실행의 후보·장부와 섞지 않았습니다.
Lean은 지정 4.26/4.27 환경, 단일 스레드, 8 GiB 한도이며 network/write 차단 하에서 실행합니다.

시간 제약으로 Bank OFF / 항상 ON / 혼합의 비교 실험은 하지 않았습니다.
관측된 감소는 이 시스템 전체 실행의 결과이고 Bank 단독의 효과로 해석할 수 없습니다.
Bank가 같은 Final 문제에서 도출되었으므로 **final adaptation**, 미지 문제 일반화가 아닙니다.

## 파일과 재현

- `proofs/`: 확정된 정리 선언의 정확한 bytes.
- `results.json`: 반올림 전 수치와 증명 해시, 종료 사유, 비용.
- `evidence/`: 공개용 압축 근거. 측정/호환성 receipt 요약·원본 해시·호출별 사용량과
  계산 비용·실행 설정·프롬프트. API 키와 원본 대화 전문은 포함하지 않습니다.
- `runtime/`: **실행 당시 동결 코드**. 최신 main의 공통 하네스를 덮어쓰지 않습니다.
- `runtime-manifest.json`: 실행 코드 해시. `mixed-search.patch`는 첨부 구현 원본에 대한
  혼합 정책 차이이며, 현재 main에 그대로 적용되는 패치라고 주장하지 않습니다.
- `export_completed.py`: 원본 실행 아카이브에서 검증 완료 행만 다시 추출하는 도구.

원본 데이터 SHA-256: `d53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682`.
원본 실행에는 모든 요청·응답·실패 후보·compiler source/log·환경 fingerprint가 로컬 보존돼
있습니다. 공개 요약만으로 그 원본 기록 전체를 재검증할 수는 없습니다. 완전한 재실행에는
데이터·지정 라이브러리 소스/빌드·환경 registry·자신의 API 키와 비용이 필요합니다.
절대 경로를 그대로 복사해 실행하지 말고 환경을 새로 준비하고 새 run root를 사용해야 합니다.

```sh
# 저장된 원본 아카이브를 다시 감사·추출: 모델/Lean 호출 없음
python experiments/putnambench-mixed-bank/export_completed.py \
  --runtime /path/to/frozen-runtime --run /path/to/original-run

# 혼합 정책·직접 API 계측의 오프라인 검사
PYTHONPATH=experiments/putnambench-mixed-bank/runtime/src python -m unittest discover \
  -s experiments/putnambench-mixed-bank/runtime/tests -p test_strategy_mixed.py -v
PYTHONPATH=experiments/putnambench-mixed-bank/runtime/src python -m unittest discover \
  -s experiments/putnambench-mixed-bank/runtime/experiments/putnambench-bank-pilot \
  -p test_openai_transport.py -v
```

확정 행의 export에서는 선언 정책·proof hash·토큰 재계산·3회 표본·전 버전 통과·compiler
source/log 해시·추천/portfolio 감사·모든 호출의 원본 응답 기반 비용 재계산을 확인했습니다.
이번 PR 작성 중에는 유료 API나 Lean 재실행을 추가하지 않았습니다.

후속 갱신: 5번 `putnam_1964_b2`의 최종 검증·정산을 완료해 증명과 결과표에 추가했습니다. F057–F060은 계속 실행 중이며, 최종 확정 후 후속 커밋으로 보강합니다.

후속 갱신: 6번 `putnam_2007_a1`의 최종 검증·정산을 완료해 증명과 결과표에 추가했습니다. F057–F060은 계속 실행 중이며, 최종 확정 후 후속 커밋으로 보강합니다.
