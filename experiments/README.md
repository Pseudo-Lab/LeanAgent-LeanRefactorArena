# 실험

앞으로 진행할 에이전트 전략·하네스 실험을 실험별 하위 폴더에 둡니다.
각 실험에는 목적·방법·실행법·결론을 기록하고, 실행 후보·측정값·로그는 `runs/`에 저장합니다.

- [첫 하네스 · 권주원](first-harness-jwkweon/README.md): 단일 에이전트의 후보 생성·Lean 검증·상태 기록·기록 재생을 확인하는 최소 실험.
- [행동·후보 기억](action-candidate-memory/README.md): 공통 하네스의 actions-v1과 후보 계보·예산 비교.
- [오류 요약 비교](feedback-summary-20261025/README.md): 구조화 추출과 의미 보존 요약의 기록·감사.
- [비용 가설](cost-hypothesis-pipeline/README.md), [로컬 탐색](offline-proof-search/README.md), [포트폴리오](portfolio-94/README.ko.md): 후보 탐색·평가·자원 관리 연구.
- [최종 환경](final-environment/README.md), [최종 배치](final-batch/README.md), [검증 캐시 배치](final-batch-next/README.md): 고정된 최종 60문제의 준비·실행·검증.

통합 범위와 역사적 runtime 의존성은 [공통하네스 구축](../docs/common-harness/README.md)을 참고하세요.

실험 파일은 작업 브랜치에서 먼저 커밋한 뒤 삭제 커밋으로 정리합니다. main에는 최종 후보·재현 코드·검증 요약을 반영하고, 실험 이력은 해당 브랜치에서 복구합니다. 실험 커밋을 main 이력에 넣지 않으려면 최종 변경을 squash merge하고 작업 브랜치를 보존합니다.

기존 코퍼스 수집·분석 및 Refactor90 코드는 커밋 `13e4072`에 보존한 뒤 제거했습니다.
코퍼스 분석 결과는 `runs/corpus-survey/`에 남아 있습니다.
팀원 웜업 최종 후보는 `../submissions/warmup/`, 표시용 결과는 `../dashboard/public/data/`에서 관리합니다.

## 팀원 웜업 결과 재검증
팀원 후보의 출처와 재검증 절차는 `../submissions/warmup/README.md`에서 관리합니다.
옛 `warmup-team-results/` 및 환경 복구의 상세 로그는 작업 브랜치의 실험 기록 커밋에 보존한 뒤 제거합니다. 과거 후보와 실행 로그는 독립적인 에이전트 풀이 탐색의 입력에서 제외합니다.
