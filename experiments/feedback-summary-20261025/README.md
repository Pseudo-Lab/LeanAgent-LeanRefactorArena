# 구조화 추출 vs 의미 보존 요약 실험

상태: complete (2026-10-25 KST). 새 브랜치 `exp/feedback-followup-20261025`에서 8개 독립 실행·80개 후보를 완료했습니다. 8개 최종 선택본·기록 replay·전체 기록 감사·라이브러리 전후 해시 확인을 모두 통과했습니다. [결과 표·해석·그래프](results/README.md), [전체 결과 JSON](results/results.json), [실행별 CSV](results/trial-results.csv)에 보존했습니다.

주 관측값인 3회차 개선 실행 수는 P01에서 S·M 모두 1/2, P13에서 모두 2/2였습니다. 10회차 평균 비용은 P01에서 S 0.586751·M 0.302502, P13에서 S 0.124305·M 0.139428입니다. 독립 요약 8건 중 실제 전달 내용이 S와 달랐던 것은 P01의 2건뿐이며 오류 설명 문장 자체를 바꾼 출력은 없었습니다. P13에서는 요약 내용 변경의 효과를 식별할 수 없습니다. 의미 보존 우려 1건과 원문 컴파일러 제안 잔존 1건도 기록했으며, 이 표본은 의미 보존 요약의 일관된 성능 우위를 입증하지 않습니다.

P01·P13에서 동일한 naive A 프롬프트와 첫 컴파일 오류 추출기를 사용합니다. S는 이전 `structured_v1` 필드 제한과 출력 형식을 그대로 사용합니다. M은 같은 첫 오류의 필드별 길이 제한 이전 추출 결과를 새 독립 모델이 요약합니다. 기존 추출기의 마지막 12개 문맥 줄 제한은 두 조건에 공통입니다. 모델에는 증명·문제·전체 로그·이력·라이브러리를 주지 않으며 수리 전략을 금지합니다.

두 조건의 `details` 상한은 canonical JSON 기준 1,600자입니다. M은 메시지를 요약하고, goal은 원문 연속 부분 문자열로, local_context는 순서를 유지한 원문 전체 줄로만 선택하며, location과 case는 바꾸지 않습니다. 전체 goal과 최소 envelope에 200자 여유를 더해 상한에 들어가면 전체 goal을 보존합니다. 타입/부분 문자열/길이 검사는 자동화하지만 의미 보존과 전략 비포함을 완전히 증명하지는 못하므로 입력과 원출력을 보존합니다. 요청당 새 요약 에이전트 1개이며 재시도하지 않습니다. 잘못된 응답·1800초 대기는 S로 fallback하고 사건을 기록합니다.

문제별·조건별 독립 solver 2개, 실행당 후보 10개, 최대 solver 동시 실행 2개로 8실행·80후보입니다. 초기 요청은 같은 문제의 네 실행에서 바이트 단위로 동일합니다. 성공/응답 거절/컴파일 이외 실패 피드백과 Lean 420초 제한·정상 컴파일+측정3회·최종 재검증·원본 분모는 동일합니다. 3/6/10회 비용, 초반 유효 후보, 최초 개선, 오류 노출, 요약 job 수·입출력·시간·fallback을 보고합니다. 정확한 backend model ID·내부 호출 수·비용은 unknown이며 0으로 간주하지 않습니다. 요약 receipt의 대기시간에는 코디네이터 배정 지연이 포함되며 모델 전용 추론시간이 아닙니다.

`coordinator.py setup runs/feedback-summary-20261025`는 설계·프로토콜·원본 입력을 동결하고 readiness 디렉터리를 만듭니다. `coordinator.py readiness COHORT`는 문제별 공유 런타임 전해시와 fresh original/imports 검사를 최대 2개 동시 실행합니다. `coordinator.py prepare COHORT`는 readiness 통과 후 8개 실행을 만들고 초기 요청의 동일성을 확인합니다. solver/요약 에이전트는 코디네이터가 명시적으로 배정하며 이 명령들은 solver를 자동 실행하지 않습니다.

`coordinator.py progress COHORT`는 중간 상태를 출력합니다. 모든 실행 완료 후 observer를 중지하고 `coordinator.py post-runtime COHORT`, `coordinator.py audit COHORT`, ReportLab이 있는 Python으로 `plot_results.py COHORT/cohort-summary.json experiments/feedback-summary-20261025/results`, `report.py COHORT experiments/feedback-summary-20261025/results`를 순서대로 실행합니다. audit는 80후보 기록/replay·입력/코드 해시·전후 런타임 해시·최종 상태·초기 요청·요약 준수·실제 오류 노출을 검사하며 미완료 상태는 결과로 내보내지 않습니다.

원본 baseline·project·runner·runtime은 이전 동결 origin에서 복사합니다. readiness의 새 측정은 실행 가능성 검사이며 원본 기준값을 갱신하지 않습니다. 라이브러리는 정책상 공유 읽기 전용이고 OS 격리는 없습니다. 조건당 두 반복과 개발에 사용한 두 문제이므로 통계적 우위나 일반화의 근거로 보지 않습니다. 기록 replay는 모델 재생성이 아닙니다. 각 실행은 부모 대화 없이 시작하지만 실행 안의 solver 대화는 유지되므로, 매 회차의 API 문맥을 완전히 통제한 실험은 아닙니다.

배정 기록은 `dispatch.py COHORT dispatch TRIAL_ID AGENT`와 `complete TRIAL_ID`로 남깁니다. `prepare`가 queue를 초기화하므로 별도 `init`는 필요하지 않습니다. 요약 job은 `dispatch.py COHORT summary-dispatch TRIAL_ID AGENT --step N`와 `summary-complete TRIAL_ID AGENT --step N`로 기록합니다. helper는 에이전트를 실행하지 않습니다. 실제 새 에이전트 ID를 기록하며 같은 요약 요청에 두 번 배정할 수 없습니다.
