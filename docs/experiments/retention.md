# 아카이브 원본과 정리 문서의 보존 기준

[실험 목록](README.md)

이 문서 묶음은 **실험 원본을 유지하는 아카이브에 설명을 추가**한다. 기준은 `archive/common-harness-build-3ee67de`의 원본 커밋 `3ee67de1707d712321e403da5cf1d064dc4240f9`이다. PR #47의 최종 변경은 `docs/experiments/*.md`와 하위 Markdown 문서 추가뿐이다.

## 이번 PR에서 유지하는 것

| 대상 | 보존 결정 |
| --- | --- |
| 기준 아카이브의 모든 추적 파일 | 경로·파일 모드·Git blob을 동일하게 유지한다. 코드·설정·테스트·기존 문서·검증 기록을 수정하거나 삭제하지 않는다. |
| `experiments/proof-analyze/results/P01_focus.lean`부터 `P15_focus.lean` | 원본 15개를 유지한다. 최초 main 대상 초안에서 제안한 삭제·ignore 변경은 이번 아카이브 PR에서 철회했다. |
| `examples/basic/*.lean`, `submissions/warmup/best/*.lean` | 원본 그대로 유지한다. 제출 후보를 교체하지 않는다. |
| 구형 실험 실행기·문제별 adapter·공식 앱 사본·과거 후보 | 기준 아카이브에 들어 있는 원본은 그대로 남긴다. main에 필요한 실행 코드의 선별과 별개다. |
| `docs/common-harness`의 기존 문서·manifest·validation | 아카이브 원본을 유지한다. PR #46의 정리된 구현으로 덮어쓰지 않는다. |
| `.gitignore`, CI workflow, runtime, 테스트 | 기준 아카이브와 동일하다. 새로운 공통 하네스 기능을 이 PR에서 통합하지 않는다. |

처음 PR #47은 main 후속 정리로 시작했지만, 이후 실험 보관용으로 목적과 base를 바꿨다. 이에 맞춰 충돌은 기준 아카이브 원본을 우선해 해결했고 정리 문서만 더했다. 이 아카이브에 병합해도 main은 바뀌지 않는다.

## 정리 문서의 역할

실험 39종의 목적·방법·실제 결과·한계·코드 반영 여부를 Markdown으로 읽는다. 당시 Markdown 원문 70개의 출처와 SHA256, 코드 복구 커밋을 기록한다. [연구 기법](research-techniques.md)의 설명용 코드와 수치도 별도 Lean·JSON·그림을 열지 않고 읽을 수 있다.

문서의 원문 인용에는 당시의 진행 중 상태·경로·명령이 남아 있다. 현재 아카이브의 보존 결정은 이 문서와 각 기록 첫 요약을 우선한다. main의 PR #46 구현과 기존 실험 아카이브는 서로 다른 snapshot이다.

향후 main 정리에서는 실행·제출·회귀 검증에 필요한 Lean을 남기고, 재생성 가능한 분석 출력·중복 후보는 문서로 설명하는 기준을 사용할 수 있다. **이 기준은 향후 선택 기준이며 이번 아카이브 원본을 삭제하는 근거가 아니다.**

## 별도 로컬 자료

미커밋 실험 실행기와 원시 `runs/` 전체를 이 PR에 추가하지 않았다. Markdown 요약은 원시 영수증·로그를 이용한 독립 재감사나 동일 환경 실행을 대체하지 않는다. Git에 없는 파일이 모두 `3ee67de`에 들어 있다는 뜻도 아니다.

앞선 워크트리 정리에서 Git이 무시하던 실행 기록·입력 사본·로컬 배포 설정 313개 파일은 다음 저장소 밖 로컬 보관처로 옮기고 SHA256 일치를 확인했다. 비밀값의 내용은 문서나 커밋에 넣지 않았다.

```text
05_pseudolab/LeanAgent-LeanRefactorArena-archives/worktree-cleanup-20261102/
  <원래 워크트리 이름>/<원래 상대경로>
```

이 폴더는 원본 증거·로컬 설정의 보관처이며 캐시나 새 Git 저장소가 아니다. 중앙 env/cache와 기존 브랜치는 유지했다. [당시 워크트리 감사](worktree-audit-2026-11-02.md)에 근거가 있다.

## 원본 조회

```sh
git show 3ee67de:experiments/portfolio-94/submission-round/README.ko.md
git show 3ee67de:experiments/proof-analyze/results/P01_focus.lean
git show 5fc7bff:docs/research/techniques-20261101/evidence/proofs/p02-portfolio40.lean
```

새 워크트리를 만들 때는 프로젝트 공통 Git 계정 검사와 해당 프로젝트 키의 중앙 환경 설정을 적용한다. 실험을 재현할 때는 당시 코드·입력·compiler·library revision을 함께 사용한다.
