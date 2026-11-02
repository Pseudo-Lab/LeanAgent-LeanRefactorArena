# 실험 코드와 Lean 보존 기준

[실험 목록](README.md)

실험의 판단 근거는 Markdown에 남긴다. 실험이 끝났다는 이유로 모든 후보를 소스 트리에 유지하지 않는다. **현재 실행·제출·회귀 검증에 필요한 Lean은 유지하고, 생성 가능한 분석 출력·중복 후보는 기본적으로 Git에 추가하지 않는다.**

## 남기는 것

| 대상 | 결정과 이유 |
| --- | --- |
| `examples/basic/*.lean` | 유지. 유효·무효·단축 예제를 실제 평가 경로에서 사용한다. |
| `submissions/warmup/best/*.lean` | 유지. 현재 제출 후보이며 실험 부산물이 아니다. 이번 정리로 후보를 교체하지 않는다. |
| 문제의 원본·고정 문맥·데이터셋 | 원본 자산으로 관리한다. 캐시로 취급하거나 일괄 삭제하지 않는다. |
| 컴파일러 조회용 `native.lean`, `native_type_search.lean` 등 | 파일 확장자로 폐기하지 않는다. 실행 도구 구현이면 유지하고 공통 통합 여부를 따로 판단한다. 현재 미커밋 연구 폴더에서도 그대로 보존했다. |
| 최소 회귀 fixture | 현재 테스트가 필요로 하는 것만 유지. 목적·호출 위치를 설명할 수 있어야 한다. |
| `experiments/final-environment`, `experiments/final-batch-next` | PR #46 runtime의 실제 의존성이므로 유지. 이름이 experiments라는 이유로 제거하지 않는다. |

## Git에 남기지 않는 것

| 대상 | 대체 기록과 복구 |
| --- | --- |
| `experiments/proof-analyze/results/P01_focus.lean`부터 `P15_focus.lean` | 자동 생성된 편집 위치 표시 파일 15개를 제거. 정적 결과 표는 [분석 기록](records/proof-analyze.md)에 보존. 원본 생성기 `analyze.py`로 15개 모두 기존 Git 파일과 byte 단위로 동일하게 재생성됨을 확인했으며 출력은 Git에서 무시한다. |
| 과거 후보·attempt·check·measure·golf 사본 | 새 문서 묶음에 추가하지 않는다. 기법·최종 지표·검증 범위·필요한 작은 코드는 Markdown에 기록한다. |
| 연구 문서 브랜치의 Lean 예제 14개 | 별도 파일로 복제하지 않는다. [기법 문서](research-techniques.md)에 설명과 비교를 보존하고 원본 `5fc7bff`에서 복구한다. |
| 흡수된 구형 실행기·문제별 adapter·공식 앱 사본 | PR #46에 다시 반입하지 않는다. 원본 `3ee67de`와 원격 archive 브랜치에 남아 있다. |
| 빌드·색인·설치 캐시 | 중앙 env/cache 규칙을 따른다. 원본 실험 결과와 API 영수증을 캐시로 분류하지 않는다. |

Lean을 Markdown 코드 블록으로 옮기는 것은 설명 보존이다. 실행·회귀 검증에 필요한 파일을 코드 블록만으로 대체하지 않는다. 지정 버전 검증을 완료한 제출 후보의 교체·폐기는 별도 판단이다.

## 이번 로컬 정리의 범위

미커밋 실험과 원시 `runs/`는 이번에 일괄 삭제하지 않았다. Git에 없는 실행기는 커밋 해시만으로 복구할 수 없고, Markdown 요약만으로 원시 영수증·독립 측정을 재감사할 수도 없기 때문이다. 여기서의 기본값은 **새 문서·PR에 불필요한 Lean을 추가하지 않는 것**이다.

정리한 워크트리의 무시된 실행 기록·입력 사본·로컬 배포 설정은 저장소 밖의 다음 로컬 폴더에 옮긴다. 비밀값의 내용은 문서나 커밋에 넣지 않는다.

```text
05_pseudolab/LeanAgent-LeanRefactorArena-archives/worktree-cleanup-20261102/
  <원래 워크트리 이름>/<원래 상대경로>
```

이 보관 폴더는 원본 증거·로컬 설정의 보관처이며 캐시나 새 Git 저장소가 아니다. 재생성 가능한 `node_modules`, `dist`, 빌드 출력은 워크트리와 함께 정리한다. 외부의 중앙 env/cache 대상은 삭제하지 않는다.

## 원본 코드 복구

브랜치는 삭제하지 않았다. 워크트리만 제거하므로 기존 커밋에서 파일을 읽거나 필요한 브랜치를 다시 열 수 있다.

```sh
git show 3ee67de:experiments/portfolio-94/submission-round/README.ko.md
git show 5fc7bff:docs/research/techniques-20261101/evidence/proofs/p02-portfolio40.lean
git show 7f9508a:experiments/proof-analyze/results/P01_focus.lean
```

새 워크트리를 만들 때는 프로젝트 공통 Git 계정 검사와 해당 프로젝트 키의 중앙 환경 설정을 먼저 적용한다. 과거 실행을 재현할 때는 당시 코드·입력·compiler·library revision을 함께 사용한다.
