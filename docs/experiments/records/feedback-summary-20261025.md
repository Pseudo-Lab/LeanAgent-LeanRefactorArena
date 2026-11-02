# 오류 요약 후속 비교

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

같은 오류에서 구조화 추출 S와 의미 보존 요약 M을 비교한다.

## 확인된 결과와 해석

8실행·80후보, 8 final/replay 감사 통과. 3회차 개선 수는 두 조건이 같았다. 요약8건 중 전달 내용이 달라진 것은 P01의2건뿐이어서 일반 효과를 식별하기 어렵다.

## 코드·Lean 보존 결정

결과와 노출량을 Markdown에 보존하고 구형 실행기·중복 후보는 반입하지 않는다.

## 보존 근거

아래는 당시 설계·실행 결과의 Markdown 본문이다. 당시의 진행 상태·경로·명령을 보존했으며, 현재 실행 지침이나 새 실행 요청이 아니다. 상충하는 중간 기록은 더 뒤의 완료 보고서와 본문 첫 요약을 우선한다. 결과 이해에 Lean·JSON·그림 열람은 필요하지 않다. 원시 로그를 다시 감사하거나 실행을 재현하려면 별도 원본·고정 환경이 필요하다.

| 원본 | 출처 | 원문 SHA256 |
| --- | --- | --- |
| `experiments/feedback-summary-20261025/README.md` | `3ee67de` | `ecd2e1e13d2e7a92fcb480b31d729bf910b35e20e4b7fc9e3f0d323cda4ee050` |
| `experiments/feedback-summary-20261025/results/README.md` | `3ee67de` | `69faef12c62acb11f4b25ab1ea58fa056c85f523a901b433cfb3d901ffc28521` |

## 원문: `experiments/feedback-summary-20261025/README.md`

### 구조화 추출 vs 의미 보존 요약 실험

상태: complete (2026-10-25 KST). 새 브랜치 `exp/feedback-followup-20261025`에서 8개 독립 실행·80개 후보를 완료했습니다. 8개 최종 선택본·기록 replay·전체 기록 감사·라이브러리 전후 해시 확인을 모두 통과했습니다. [결과 표·해석·그래프](feedback-summary-20261025.md), [전체 결과 JSON](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/experiments/feedback-summary-20261025/results/results.json), [실행별 CSV](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/experiments/feedback-summary-20261025/results/trial-results.csv)에 보존했습니다.

주 관측값인 3회차 개선 실행 수는 P01에서 S·M 모두 1/2, P13에서 모두 2/2였습니다. 10회차 평균 비용은 P01에서 S 0.586751·M 0.302502, P13에서 S 0.124305·M 0.139428입니다. 독립 요약 8건 중 실제 전달 내용이 S와 달랐던 것은 P01의 2건뿐이며 오류 설명 문장 자체를 바꾼 출력은 없었습니다. P13에서는 요약 내용 변경의 효과를 식별할 수 없습니다. 의미 보존 우려 1건과 원문 컴파일러 제안 잔존 1건도 기록했으며, 이 표본은 의미 보존 요약의 일관된 성능 우위를 입증하지 않습니다.

P01·P13에서 동일한 naive A 프롬프트와 첫 컴파일 오류 추출기를 사용합니다. S는 이전 `structured_v1` 필드 제한과 출력 형식을 그대로 사용합니다. M은 같은 첫 오류의 필드별 길이 제한 이전 추출 결과를 새 독립 모델이 요약합니다. 기존 추출기의 마지막 12개 문맥 줄 제한은 두 조건에 공통입니다. 모델에는 증명·문제·전체 로그·이력·라이브러리를 주지 않으며 수리 전략을 금지합니다.

두 조건의 `details` 상한은 canonical JSON 기준 1,600자입니다. M은 메시지를 요약하고, goal은 원문 연속 부분 문자열로, local_context는 순서를 유지한 원문 전체 줄로만 선택하며, location과 case는 바꾸지 않습니다. 전체 goal과 최소 envelope에 200자 여유를 더해 상한에 들어가면 전체 goal을 보존합니다. 타입/부분 문자열/길이 검사는 자동화하지만 의미 보존과 전략 비포함을 완전히 증명하지는 못하므로 입력과 원출력을 보존합니다. 요청당 새 요약 에이전트 1개이며 재시도하지 않습니다. 잘못된 응답·1800초 대기는 S로 fallback하고 사건을 기록합니다.

문제별·조건별 독립 solver 2개, 실행당 후보 10개, 최대 solver 동시 실행 2개로 8실행·80후보입니다. 초기 요청은 같은 문제의 네 실행에서 바이트 단위로 동일합니다. 성공/응답 거절/컴파일 이외 실패 피드백과 Lean 420초 제한·정상 컴파일+측정3회·최종 재검증·원본 분모는 동일합니다. 3/6/10회 비용, 초반 유효 후보, 최초 개선, 오류 노출, 요약 job 수·입출력·시간·fallback을 보고합니다. 정확한 backend model ID·내부 호출 수·비용은 unknown이며 0으로 간주하지 않습니다. 요약 receipt의 대기시간에는 코디네이터 배정 지연이 포함되며 모델 전용 추론시간이 아닙니다.

`coordinator.py setup runs/feedback-summary-20261025`는 설계·프로토콜·원본 입력을 동결하고 readiness 디렉터리를 만듭니다. `coordinator.py readiness COHORT`는 문제별 공유 런타임 전해시와 fresh original/imports 검사를 최대 2개 동시 실행합니다. `coordinator.py prepare COHORT`는 readiness 통과 후 8개 실행을 만들고 초기 요청의 동일성을 확인합니다. solver/요약 에이전트는 코디네이터가 명시적으로 배정하며 이 명령들은 solver를 자동 실행하지 않습니다.

`coordinator.py progress COHORT`는 중간 상태를 출력합니다. 모든 실행 완료 후 observer를 중지하고 `coordinator.py post-runtime COHORT`, `coordinator.py audit COHORT`, ReportLab이 있는 Python으로 `plot_results.py COHORT/cohort-summary.json experiments/feedback-summary-20261025/results`, `report.py COHORT experiments/feedback-summary-20261025/results`를 순서대로 실행합니다. audit는 80후보 기록/replay·입력/코드 해시·전후 런타임 해시·최종 상태·초기 요청·요약 준수·실제 오류 노출을 검사하며 미완료 상태는 결과로 내보내지 않습니다.

원본 baseline·project·runner·runtime은 이전 동결 origin에서 복사합니다. readiness의 새 측정은 실행 가능성 검사이며 원본 기준값을 갱신하지 않습니다. 라이브러리는 정책상 공유 읽기 전용이고 OS 격리는 없습니다. 조건당 두 반복과 개발에 사용한 두 문제이므로 통계적 우위나 일반화의 근거로 보지 않습니다. 기록 replay는 모델 재생성이 아닙니다. 각 실행은 부모 대화 없이 시작하지만 실행 안의 solver 대화는 유지되므로, 매 회차의 API 문맥을 완전히 통제한 실험은 아닙니다.

배정 기록은 `dispatch.py COHORT dispatch TRIAL_ID AGENT`와 `complete TRIAL_ID`로 남깁니다. `prepare`가 queue를 초기화하므로 별도 `init`는 필요하지 않습니다. 요약 job은 `dispatch.py COHORT summary-dispatch TRIAL_ID AGENT --step N`와 `summary-complete TRIAL_ID AGENT --step N`로 기록합니다. helper는 에이전트를 실행하지 않습니다. 실제 새 에이전트 ID를 기록하며 같은 요약 요청에 두 번 배정할 수 없습니다.

## 원문: `experiments/feedback-summary-20261025/results/README.md`

### 구조화 추출 vs 의미 보존 요약 결과

동일한 naive A 프롬프트·첫 오류 추출기·1,600자 상한에서 S(기존 structured_v1)와 M(독립 모델 요약)을 비교했다. M에는 메시지 요약과 goal·context의 원문 선택을 요청하고 수리 전략 생성을 금지했다. 문제별·조건별 두 독립 solver, 실행당 10후보, 총 8실행·80후보다.

주 관측값은 3회차에 원본보다 낮은 비용을 찾은 실행 수다. 로컬 실험 비용은 `0.5 × (tokens/원본tokens + rawHB/원본rawHB)`이며 낮을수록 좋다. 3·6회는 처음부터 고지된 10회 예산 내 중간 관측이다.

| 문제 | 조건 | 3회차 개선 | 초반 유효 평균/3 | 3회 비용 | 6회 비용 | 10회 비용 | 최종 검증 |
|---|---|---:|---:|---:|---:|---:|---:|
| P01 | S | 1/2 | 1.00 | 0.977516 [0.955033, 1.000000] | 0.665453 [0.330907, 1.000000] | 0.586751 [0.330907, 0.842595] | 2/2 |
| P01 | M | 1/2 | 1.50 | 0.761812 [0.523623, 1.000000] | 0.346941 [0.314401, 0.379480] | 0.302502 [0.280821, 0.324182] | 2/2 |
| P13 | S | 2/2 | 2.50 | 0.167318 [0.160344, 0.174292] | 0.138004 [0.127862, 0.148147] | 0.124305 [0.111257, 0.137353] | 2/2 |
| P13 | M | 2/2 | 1.50 | 0.192549 [0.180034, 0.205064] | 0.177963 [0.166146, 0.189780] | 0.139428 [0.127681, 0.151176] | 2/2 |

비용 셀은 평균 [두 실행의 최솟값, 최댓값]이다. 최종 검증은 탐색 중 비용과 구분한다.

P01의 주 관측값(3회차 개선)은 S 1/2, M 1/2다. 10회차 평균 비용의 M 대 S 상대 차이는 -48.44%다. 이는 두 실행씩의 관측 차이이며 인과 효과 추정치가 아니다.

P13의 주 관측값(3회차 개선)은 S 2/2, M 2/2다. 10회차 평균 비용의 M 대 S 상대 차이는 +12.17%다. 이는 두 실행씩의 관측 차이이며 인과 효과 추정치가 아니다.

| 실행 | 첫 유효 | 첫 개선 | 3회 전 오류 노출 | 요약 jobs | fallback | 최종 검증 |
|---|---:|---:|---:|---:|---:|---|
| P01-S-r1 | 4 | 7 | 2 | 0 | 0 | 통과 |
| P13-M-r1 | 2 | 2 | 1 | 2 | 0 | 통과 |
| P13-S-r1 | 1 | 1 | 0 | 0 | 0 | 통과 |
| P01-M-r1 | 3 | 4 | 2 | 3 | 0 | 통과 |
| P01-M-r2 | 2 | 3 | 1 | 1 | 0 | 통과 |
| P13-S-r2 | 2 | 2 | 1 | 0 | 0 | 통과 |
| P13-M-r2 | 2 | 2 | 1 | 2 | 0 | 통과 |
| P01-S-r2 | 2 | 3 | 1 | 0 | 0 | 통과 |

요약 요청 8건, 관측 가능한 독립 요약 job 8개, fallback 0건이다. 요약 원문 입출력·응답 해시·대기시간·목표/가정 보존 길이는 results.json에 보존했다. 정확한 모델 ID·내부 호출 수·요금은 unknown이다.

초기 요청 동일성·80후보 기록/replay·최종 상태·전체 공유 런타임 전후 SHA256·요약 스키마/원문 선택 검사를 통과했다. 의미 보존과 전략 비포함은 기계 검사만으로 완전히 입증할 수 없다. 실제 오류 노출과 fallback을 함께 해석해야 한다.

조건당 두 번과 개발에 사용한 두 문제의 탐색 결과이며 통계적 우위나 일반화를 입증하지 않는다. 오류 이후 후보 유효성은 서로 다른 탐색 경로의 관측이다. 기록 replay는 모델 재생성이 아니다. 실행 안의 solver 대화는 유지되므로 매 회차 API 문맥이 완전히 통제된 실험은 아니다. 라이브러리는 정책상 공유 읽기 전용이며 OS 격리는 없다.

[전체 결과](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/experiments/feedback-summary-20261025/results/results.json) · [사전 설계](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/experiments/feedback-summary-20261025/results/design.frozen.json) · [전후 런타임 검사](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/experiments/feedback-summary-20261025/results/runtime-checks.json) · [실행 프로토콜](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/experiments/feedback-summary-20261025/results/execution-protocol.json)

원문 실행: `/Users/zzu0203/projects/01_가짜연구소/.worktrees/arena-feedback-summary-20261025/runs/feedback-summary-20261025`

이번 실행의 Lean 컴파일 호출: 후보 검증 260회, 최종 검증 32회, 원본·imports 사전 검증 10회다. `--version`/`--print-prefix` 조회와 재사용한 과거 baseline의 컴파일은 제외했다. 컴파일 횟수·증명 후보 수·요약 job 수·관측 불가능한 내부 모델 호출 수는 서로 다르다.

동일 오류를 S로 포맷한 출력과 실제 전달 내용이 달랐던 것은 2/8건이고, 더 짧게 전달된 것은 1/8건이다. 이는 같은 저장 로그를 다시 포맷한 조작 확인이며 추가 solver·Lean 실험이 아니다.

추출 원문 대비 오류 설명 문장을 바꾼 경우 0건, 동일 오류의 S 출력 대비 목표 선택이 달랐던 경우 1건, 가정 선택이 달랐던 경우 2건이다. 이 범주는 중복될 수 있으며, 모델 호출 자체와 실제 문장 요약·정보 선택의 발생을 구분한다.

사후 입력·출력 검토에서 의미 보존 우려 1건, 추가 수리 전략 관측 0건을 기록했다. 이 검토는 형식 검사와 별개이며 solver 피드백을 수정하지 않았다. [사례별 품질 검토](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/experiments/feedback-summary-20261025/results/semantic-review.json)에서 근거를 확인할 수 있다.

원문 컴파일러의 제안을 그대로 남긴 경우는 1건이며, 엄격한 제안 비포함 조건에 대한 우려는 1건이다. 모델이 새로 추가한 수리 전략과 원문 제안의 잔존을 각각 기록했다.

P01 M 실행별 실제 변경 피드백 노출(3회차 이전/전체): P01-M-r1 1/1, P01-M-r2 1/1. 오류 노출이 있어도 S와 동일한 내용이면 변경된 정보에 대한 노출로 세지 않았다.

P13 M 실행별 실제 변경 피드백 노출(3회차 이전/전체): P13-M-r1 0/0, P13-M-r2 0/0. 오류 노출이 있어도 S와 동일한 내용이면 변경된 정보에 대한 노출로 세지 않았다.

P13에서는 M이 solver에게 전달한 오류 내용이 모두 같은 오류의 S 출력과 같았다. 따라서 조건 간 성능 차이로 요약 내용 변경의 효과를 식별할 수 없다.

P01 평균과 실행 간 범위 (과거 그림; 수치는 본문 표 참조)

P13 평균과 실행 간 범위 (과거 그림; 수치는 본문 표 참조)
