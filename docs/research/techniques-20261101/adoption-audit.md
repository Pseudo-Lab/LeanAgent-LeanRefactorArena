# 반영 여부 감사

## 기준과 판정 절차

`git fetch origin`으로 확인한 main은 `7f9508a85d44c5369f9461222f9904d6a9c01486`이다. 감사 시각·브랜치 tip·파일별 Git blob/SHA256는 [git-audit.json](evidence/git-audit.json)에 고정했다. 이후 main이 이동해도 이 문서의 기준점은 자동으로 바뀌지 않는다.

1. 원래 체크아웃의 modified/untracked 코드·설정·문서를 열거했다. 자격 증명과 원시 실행 기록은 제외했다.
2. 실제 디스크 내용을 읽어 Git blob을 계산하고, main 및 알려진 branch tip의 같은 경로와 비교했다. 현재 HEAD가 모르는 untracked 파일은 `git diff origin/main`만으로 보면 삭제처럼 보일 수 있으므로, 그 출력을 신규 구현 판정에 사용하지 않았다.
3. 같은 기능이 다른 경로에 있거나 수학적 아이디어만 재사용된 경우에는 구현·증명 본문을 별도로 읽었다.
4. 채택된 제출 파일과 로컬 `final.lean`을 구분했다. “로컬 final”은 main 반영을 뜻하지 않는다.

## 이미 반영된 구현

| 항목 | 확정 근거 | 판정 |
| --- | --- | --- |
| 사전 점검·오류 피드백·상태 조회 | `1f51537` / PR #3; `src/lean_agent/preflight.py`, `diagnostics.py`, `status.py` | 기본 하네스에 반영 |
| 실제 문제/API 통합 | `84412c8` / PR #31 | 로컬 원래 HEAD `9323abd`와 SHA는 다르지만 main의 병합 커밋이 존재 |
| prepared hash의 opt-in stat cache | `7c5054f` / PR #33; [prepared.py](../../../src/lean_agent/prepared.py) | 로컬 파일과 main이 동일. 기본값은 full 검증이며 새 검증기를 만들어도 캐시가 전역 공유되는 것은 아님 |
| 사용량/비용 통합 | `ba3de4f` / PR #34; `usage_cost.py`, 가격 snapshot, `usage-cost.json`, replay | 반영. 로컬 옛 `harness.py` 전체를 덮어쓰면 오히려 이 기능을 잃음 |
| 단축 agent kit | `7f9508a` / PR #35 | 기본 budget runner, direct adapter, golf/verify/goals/floor, v4 prompt, skill이 이미 있음 |

동일한 로컬 파일은 `prepared.py`, HB profile/minimize 기본 파일 4개, budget report, v4 prompt, golf의 floor/goals/trial이다. 반면 다음 차이는 새 기능으로 그대로 합치면 안 된다.

- 로컬 `harness.py`의 stat-cache CLI 추가는 main에 이미 있다. 전체 파일에는 main의 후속 usage-cost 기능이 빠져 있다.
- 로컬 `tests/test_prepared_cache.py`는 main보다 캐시 격리·메타데이터 변경·읽는 중 변조 등 검사 5개가 적다. 신규 테스트 확장으로 분류할 수 없다.
- 로컬 기본 `golf.py`는 main의 `agent-input.json` 입력과 `--version` 선택이 빠진 옛 변형이다. 별도 v10 소스 구간 golf는 신규 구현이지만 이 파일과 동일하지 않다.
- 로컬 budget runner의 기본 경로·프롬프트는 과거 시행 값이다. main의 더 일반적인 입력 기본값을 덮어쓸 이유가 아니다.
- 로컬 direct adapter의 `select_model` 및 frozen model 선택 연결은 추가분이다. 그 파일에 적힌 과거 가격표를 현재 가격 검증 결과로 취급하지 않는다.

## 수학적 아이디어와 특정 후보의 반영은 다르다

| 문제 | main에서 직접 확인한 것 | 새로 문서화한 차이 | 채택 상태 |
| --- | --- | --- | --- |
| P01 | 구조적 귀납과 membership/Subset 정규화 | 함수 귀납의 인자 생략·목표/귀납가정 정규화 정렬 | 새 예제 미채택 |
| P02 | `NormalizedOldExpr` 증거 귀납과 `Subset` | 정규화 전제를 버리고 더 강한 `Sublist`를 직접 합성 | 미반영 |
| P03 | `updatedStatesComm`에 의한 전체 update 교환 | 중간 상태에서 disjointness 연결, 길이 사실 공유·표현 압축 | 핵심 경로는 이미 반영; 새 후보는 미채택 |
| P06 | 두 span 귀납과 공통 정렬·중심성 계산 | 쌍선형 사상 등식 + 두 번의 기저 ext | 미반영; main은 450토큰, 수동 후보는 528토큰 |
| P11 | 별도 0/1 평가·긴 fiber 차이 계산 | `Fin 2` 일반화·선형성 또는 기존 one-level fiber 정리 직접 사용 | 미반영; main 1,656토큰, 수동 후보 1,120토큰 |
| P13 | 유한한 4개 연속항 상태의 충돌과 강한 귀납 | 일반 `hprev` 보조정리 제거, 제한된 rewrite/simp로 연결 | 핵심 아이디어는 반영; 187토큰 후보 미채택 |
| P14 | 여집합 쌍으로 절반을 세는 논증 | `Set.Intersecting.is_max_iff_card_eq`에 직접 연결 | 기본 조합론은 반영; 31토큰 후보 미채택 |
| P15 | 입력 둘을 받는 자릿수 합 항등식과 `(3,-2)` Bézout 증명 | 관계→나눗셈 보조정리 통합, `sum_erase_eq_sub`, 약분 선적용, `rfl` | 기본 불변식·약분은 반영; 181토큰 후보 미채택 |

main의 P13/P14/P15 증명 길이는 각각 259/364/283토큰이다. 로컬 88점 참조의 259/55/281 등과 같다고 가정하지 않았다. “기존 제출본”이라는 이름으로 서로 다른 snapshot을 섞지 않는 것이 중요하다.

## 다른 브랜치에 이미 커밋된 작업

`origin/codex/verification-repair-design`, `origin/codex/verification-repair-policy`, `origin/codex/verification-repair-evaluation`에는 main 이후의 설계·오프라인 평가·bounded recursive repair 구현이 있다. 예를 들어 policy tip은 `14968c2`이며 `experiments/verification-repair-policy/repair.py`, `native.py`, `runtime.py` 등이 존재한다. 현재 main에는 그 디렉터리가 없다.

따라서 이는 **이미 커밋됐지만 main에는 미병합**인 관련 연구다. 로컬 v7–v11 전체가 그 브랜치에 반영됐다는 뜻도, 새로 발견한 미커밋 기법이라는 뜻도 아니다. 이 문서 브랜치가 해당 구현을 재병합하지는 않는다.

## 과거 문서의 커밋 번호를 그대로 신뢰하지 않은 이유

미커밋 `docs/experiment-log-2026-10-28-29.md`는 `7d624d3`, `2f7e0c6`, `cbc56b6` 등을 코드 커밋으로 인용한다. 조회한 8개 객체는 존재하지만 감사 시점의 main 조상이 아니며 포함하는 branch ref도 없다. 해당 번호만으로 현재 main 반영 여부를 확정할 수 없다. 일부 코드는 PR #33·#35의 다른 SHA로 이미 들어왔다.

이 묶음은 과거 실행의 날짜·수치는 실험 기록으로 인용하되, 채택 판단은 위의 최신 main 코드와 실제 병합 커밋을 기준으로 다시 했다. 오래된 문서를 현재 상태로 가장해 복사하지 않았다.

## 아직 기본 하네스로 들어오지 않은 것

`workflow.py`, `proof_experience.py`, cached-verification worker, 공통 v5 연구, structured v6, v7–v11, 경쟁형 탐색 및 수동 P06/P11 실행기는 해당 구현 경로가 main에 없다. 로컬 README의 “current/recommended”는 해당 실험 계열 내부의 안내이며 저장소 기본 실행 경로로 배포됐다는 증거가 아니다.

기본 평가기의 `Name.toString`은 아직 한정되지 않았다. 일부 실험이 `Lean.Name.toString`으로 우회한 것을 공통 평가기의 수정 완료로 표시하지 않는다. `#(term)` cardinality 표기를 허용한 실험 guard 역시 현재 공통 guard와 다르다.
