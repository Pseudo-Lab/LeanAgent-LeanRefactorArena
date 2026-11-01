# 실험

앞으로 진행할 에이전트 전략·하네스 실험을 실험별 하위 폴더에 둡니다.
각 실험에는 목적·방법·실행법·결론을 기록하고, 실행 후보·측정값·로그는 `runs/`에 저장합니다.
실험 파일은 작업 브랜치에서 먼저 커밋한 뒤 삭제 커밋으로 정리합니다. main에는 최종 후보·재현 코드·검증 요약을 반영하고, 실험 이력은 해당 브랜치에서 복구합니다. 실험 커밋을 main 이력에 넣지 않으려면 최종 변경을 squash merge하고 작업 브랜치를 보존합니다.

기존 코퍼스 수집·분석 및 Refactor90 코드는 커밋 `13e4072`에 보존한 뒤 제거했습니다.
코퍼스 분석 결과는 `runs/corpus-survey/`에 남아 있습니다.
팀원 웜업 최종 후보는 `../submissions/warmup/`, 표시용 결과는 `../dashboard/public/data/`에서 관리합니다.

## Auto Solver → Recursive Repair

[실험 설계](verification-repair-policy/README.md)는 [#40](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/issues/40)에 따라
[#37](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/issues/37)의 Controller·Planner·Worker 위에
자동 전술과 재귀적 하위 목표 수리를 연결하는 하네스를 설계합니다.
기준·자동 수리·재귀 수리 조건으로 복구율과 최종 token·heartbeat 개선을 구분합니다.
PR A는 설계, PR B는 native 목표 수집·재귀 수리 구현과 API 예산 USD 0의 실제 Lean·고정 응답 검증,
PR C는 효과 평가를 담당합니다. [PR B 실행 안내](verification-repair-policy/IMPLEMENTATION.md)를 참고하세요.
[PR C 무과금 평가](verification-repair-policy/evaluation/README.md)는 고정 실패 후보의 재현·자동 수리와 미측정 범위를 보고합니다.
#37의 공개 구현에 대한 실제 통합은 별도 확인이 필요합니다.

## 팀원 웜업 결과 재검증

팀원 후보의 출처와 재검증 절차는 `../submissions/warmup/README.md`에서 관리합니다.
옛 `warmup-team-results/` 및 환경 복구의 상세 로그는 작업 브랜치의 실험 기록 커밋에 보존한 뒤 제거합니다. 과거 후보와 실행 로그는 독립적인 에이전트 풀이 탐색의 입력에서 제외합니다.
