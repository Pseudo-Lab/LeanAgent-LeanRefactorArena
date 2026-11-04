# 공통 하네스의 native AutoSolver

`agent.autosolver`를 설정하면 컴파일에 실패한 모델 후보에 한해 고정 전술을 시도한다.
공통 `lean-agent run`과 Final 배치가 같은 `autosolver.py`와 후보 등록 경로를 사용한다.
추가 모델 호출, 별도 비용 장부, 재귀 LLM repair는 없다. 기존 설정은 동작을 유지한다.

## 실행 흐름

```text
모델 응답 → 기존 평가기 → 유효 후보: 기존 순위로 반영
                    └→ proof 실패
                        → native InfoTree 목표·지역 문맥·UTF-8 위치 추출
                        → 제한된 전술 시도 → 미해결: 진단과 실패 후보 보존
                                         └→ 전체 조립 완료
                                             → 기존 평가기로 원래 문맥 재검증·측정
                                             → cNNN-auto 등록 → 기존 순위로 best 선택
```

native 관측은 고정 프로젝트·컴파일러·라이브러리·setup·sandbox를 재사용한다.
진단 복사본에만 Lean helper를 삽입한다. 출력된 목표 문자열을 파싱해 위치를 추측하지 않고,
InfoTree와 syntax의 실제 위치를 대응한다. 실패 구간을 `exact (by <전술>)`로 감싸고,
그 범위의 오류가 없으며 native after-state가 비어 있을 때에만 해당 부분을 닫았다고 판단한다.
중첩 `have ... := by`, bullet, UTF-8 식별자의 범위를 유지한다.

부분 성공만으로 후보를 채택하지 않는다. 모든 오류가 사라진 조립 결과도 기존 평가기의
변경 없는 문맥 검사·axiom 검사·토큰/HB 측정을 통과해야 유효 후보가 된다.
추가 import로 진단이 성공해도 원래 문맥에서 실패하면 채택하지 않는다.
Final 배치에서는 대표 버전으로 탐색하고, 기존 최종 선택에서 모든 필수 버전을 확인한 뒤
캐시를 쓰지 않는 최종 측정을 한다.

## 설정과 한도

`agent.mode`는 `actions-v1`이어야 한다. `{}`는 아래 기본값을 사용한다.

```json
{
  "agent": {
    "mode": "actions-v1",
    "corpus": "action-corpus.json",
    "autosolver": {
      "tactics": ["rfl", "assumption", "trivial", "simp", "omega", "grind"],
      "max_attempts": 6,
      "max_sites": 3,
      "inspection_seconds": 30,
      "search_seconds": 120,
      "memory_mib": 4096
    }
  }
}
```

전술은 고정 집합의 일부를 순서대로 선택하며 임의 Lean 명령은 설정으로 받지 않는다.
`max_attempts`는 한 모델 후보 전체의 전술 시도 수, `max_sites`는 닫은 부분 증명 수다.
최초 목표 추출도 inspection 한 번이며 전술 시도 횟수에는 포함하지 않는다.
각 inspection은 남은 시간과 `inspection_seconds` 중 작은 값으로 제한한다.
`search_seconds`는 실제 측정한 native inspection 경과 시간의 합을 제한한다.
큐 대기·파일 기록과 별도의 전체 검증까지 포함한 실행 전체의 절대 마감시간은 아니다.
전체 검증에는 기존 평가기의 timeout·반복 수·메모리 정책이 적용된다.

지원 위치를 찾지 못하거나 진단 helper를 사용할 수 없으면 기존 실패 피드백을 보존한다.
유효 후보, 응답/선언 검증 실패, 비용 미확정, 평가 환경 실패·timeout에는 시작하지 않는다.
자동 조립 결과의 전체 검증에서 환경 실패가 나면 기존 중단 규칙을 적용한다.
현재 목표 요약은 **원래 실패 후보의 첫 미해결 native 상태**다. 모든 독립 목표의 목록이 아니며,
출처 후보 ID를 함께 기록한다.

## 후보 계보·scout 할당량·기록

- 원래 실패 후보 `c001`은 그대로 남고, 완성된 조립 결과는 `parent_id: c001`인 `c001-auto`가 된다.
  전체 검증에 실패한 자동 후보도 무효로 남는다. best와 접근 정책의 개선 여부는 검증된 결과를 따른다.
- 자동 후보는 원래 후보와 같은 scout에 속한다. scout 평가 장벽이 다음 역할로 넘어간 순간에도
  원래 scout의 소유권을 유지한다. merger는 장벽 이후 자동 후보도 읽고 합성 출처로 지정할 수 있다.
- 모델 호출·비용·scout/merger 할당량은 원래 모델 제안 평가 한 번만 센다.
  native 시도와 파생 후보의 전체 검증은 별도로 기록하며 `autosolver.model_calls`는 0이다.
- `steps/<번호>/autosolver/`에 inspection source/log/report, `search.json`, 완성 후보와 전체 평가를 남긴다.
  summary의 검색 수·시도 수·inspection 수·native 시간·검증 성공 후보 수를 통해 추가 계산량을 확인한다.
- 공통 runner는 코드와 Lean helper도 snapshot한다. offline replay는 저장한 관측·시간으로 탐색 결정을
  재구성하고 후보 계보·상태를 검증하며 Lean/API를 다시 호출하지 않는다. Final 배치는 checkpoint와
  저장한 검색을 재사용하며 report에서 계보·소유권·추가 계산량을 감사한다.

## 실행과 검사

고정 응답 smoke는 API를 호출하지 않는다. 설정에 고정한 Lean 4.26이 PATH에 있어야 한다.
프로젝트 공통 환경·캐시 설정 후 새 output 경로에서 실행한다.

```sh
PYTHONPATH=src python3 -B -m lean_agent run --config configs/autosolver-smoke.json --output runs/autosolver-smoke
PYTHONPATH=src python3 -B -m lean_agent replay runs/autosolver-smoke
```

Final 배치는 새 배치 root의 `inputs` 또는 `prepare` 단계에 `--autosolver`를 추가한다.
이때 기본 설정 `{}`를 입력과 함께 동결한다. 이미 실행 중인 root의 정책은 바꾸지 않는다.
사용자 지정 한도는 Python `configuration` / `prepare_inputs` / `prepare`의
`autosolver_settings`로 전달할 수 있다. 이 옵션은 배치의 기존 API 실행 승인을 대신하지 않는다.

```sh
python3 -B scripts/check_common_harness.py
AUTOSOLVER_LEAN=/absolute/path/to/lean AUTOSOLVER_LEAN_VERSION=v4.26.0 \
  PYTHONPATH=src python3 -B -m unittest discover -s tests -p test_autosolver_native.py -v
```

실제 Lean 검사는 4.26.0·4.27.0·4.31.0에서 각각 자동 해결→전체 재검증→후보 등록→리플레이,
여러 bullet과 Unicode 위치를 확인한다. CI에도 이 세 버전의 native 검사를 추가한다.
이는 모든 Final 문제를 자동으로 해결하거나 성능을 개선한다는 결과가 아니다.
실제 F001 원문 문맥에서는 세 버전의 목표 추출 호환성을 별도로 확인했다.

## 출처와 후속 범위

지연님 [PR #41](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/pull/41)과
[PR #42](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/pull/42)의
`experiments/verification-repair-policy/{Support.lean,native.py,repair.py}`를 참고했다.
기준 revision은 `9fe17e58e78a1cbf67b171e01dc01b274e9d68ea`이며, native 위치 선택·부분 증명 삽입·
InfoTree collector를 공통 모듈로 옮겼다. helper의 보조 정의에 `meta`를 표시해
Lean 4.27/4.31의 모듈 검사에서도 작동하게 했다.

원본 PR의 fixture Controller·provider·예산 루프·대형 실험 폴더는 반입하지 않았다.
재귀 Worker/repair와 API에서의 MD 스킬 자동 로딩은 후속 범위로 남긴다.
