# Lean Refactor Arena — 평가 모듈

[HTML 개요 문서](docs/evaluation-overview.html): 평가 흐름·점수 기준·검증 결과·연결 방법을 정리한 문서.

[가안: 문제별 환경 고정 — HTML 문서](docs/environment-proposal.html): 구조도, 2문제·4환경 파일럿 결과, 미검증 범위와 구현 순서.
HTML을 내려받아 브라우저에서 열면 외부 서비스 없이 볼 수 있다. [Markdown 원문](docs/environment-architecture.md) · [검증 요약](docs/environment-pilot-results.json).

리팩터링 전략과 모델 API에서 독립된 Python 평가 하네스다. Python 3.10+ 표준 라이브러리만 사용하며,
실제 검증에는 문제별로 준비된 Lean/Lake 환경이 필요하다. 현재 실행기는 macOS/Linux를 지원한다.

두 가지 용도로 같은 평가 코드를 사용한다.

1. **실험 중:** 원본을 측정하고, agent가 반환하는 각 후보를 저장·검증·측정한 뒤 다음 시도의 피드백으로 돌려준다.
2. **실험 종료:** 원본과 모든 후보를 다시 검증·측정하고, 자격을 갖춘 후보 중 최고점의 코드를 자동으로 내보낸다.

```text
문제 + 원본 + 고정 환경/정책
  → 원본 측정
  → propose(feedback) → 후보 스냅샷 → 검증/측정 → manifest 기록
  → 오류 수정 또는 새 후보 제안 → 반복
  → 원본 + 모든 후보를 모든 지정 환경에서 재검증/반복 측정
  → 최고점 후보 선택 → selected.lean + selection.json
```

`run_search()`가 제어하는 루프에서는 **측정 완료 및 기록 전에는 다음 propose 호출이 없다.**
에이전트 내부의 비공개 사고 과정이나 반환하지 않은 임시 파일까지 감시하지는 않는다.
측정할 중간 산출물마다 한 번 반환하도록 agent adapter를 구성한다.
직접 CLI를 사용하는 agent용 [skill](skills/lean-refactor-evaluation/SKILL.md)도 제공하지만,
skill 지시 준수와 코드로 제어하는 루프의 강제성은 구분한다.

## 빠른 실행

저장소 루트에서 실행한다. 예제는 `leanprover/lean4:v4.26.0`이 이미 설치되어 있어야 한다.
실험 전에 필요한 의존성을 별도로 준비한다. 평가기는 설치·빌드 명령을 실행하지 않지만
`lake env`는 Lake의 통상적인 환경 준비를 수행할 수 있다.

```sh
python3 -m refactor_eval run \
  --problem examples/basic/problem.json \
  --run-dir runs/demo \
  --max-attempts 3 \
  -- python3 examples/replay_agent.py
```

위 adapter는 실패 후보 → 수정 후보 → 종료를 재생한다. 모델이나 유료 API를 호출하지 않는다.
새 실행에는 새 `--run-dir`을 사용한다. 설치가 필요하면 `python3 -m pip install -e .` 후
`lean-refactor-eval` 명령을 사용할 수 있다.

개별 호출 및 이미 만들어진 후보의 일괄 평가:

```sh
python3 -m refactor_eval init --problem examples/basic/problem.json --run-dir runs/manual
python3 -m refactor_eval checkpoint --run-dir runs/manual --candidate examples/basic/broken.lean
# 실패도 기록된다. checkpoint의 종료 코드 2는 수정 가능한 후보 검증 실패다.
python3 -m refactor_eval checkpoint --run-dir runs/manual --candidate examples/basic/short.lean \
  --parent-id candidate-0001 --note '실패 후보를 rfl 증명으로 수정'
python3 -m refactor_eval finalize --run-dir runs/manual
```

후보 1…k가 이미 있으면 각각 `checkpoint`에 넣고 마지막에 `finalize`를 호출한다.
CLI stdout은 JSON이다. 종료 코드 0은 명령 성공, 1은 설정·실행 오류, 2는 checkpoint 후보 검증 실패다.
컴파일에 성공했어도 점수/정책 때문에 기각될 수 있으므로 `assessment.eligible`, `accepted`를 확인한다.

## 점수와 선택 규칙

기본값은 다음 **로컬 실험 점수**다. 대회의 공식 점수라고 주장하지 않는다.

```text
token_gain     = 1 - candidate_tokens / baseline_tokens
heartbeat_gain = (baseline_hb - candidate_hb) / max(baseline_hb, 1)
score          = 100 × (token_weight × token_gain + heartbeat_weight × heartbeat_gain)
                     / (token_weight + heartbeat_weight)
```

기본 가중치는 각각 0.5이며 원본 점수는 0이다. heartbeat가 0으로 반올림된 원본은 개선 여지가 0이며,
양수 heartbeat 후보는 위 식에 따라 감점한다. 토큰 수와 heartbeat는 작을수록, score는 클수록 좋다.

| 설정 | 의미 |
| --- | --- |
| `token_weight`, `heartbeat_weight` | 0 이상의 가중치. 둘의 합은 양수 |
| `minimum_gain` | 원본 대비 이 점수보다 **엄격히 큰** 후보만 자격 부여. 기본 0 |
| `require_non_regression` | true면 토큰 또는 평가한 환경의 heartbeat가 원본보다 증가한 후보 제외. 기본 false |
| `scoring_environment` | heartbeat 점수를 계산할 대표 환경. 다른 환경의 heartbeat와 섞거나 평균내지 않음 |
| `checkpoint_runs` | 중간 평가의 독립 compiler process 반복 수. 기본 1 |
| `final_runs` | 최종 평가의 독립 compiler process 반복 수. 기본 3 |

기본 정책은 토큰/heartbeat 사이의 상충을 종합 점수로 판단한다. 두 지표 모두 비증가를 요구하려면
처음부터 `require_non_regression: true`로 설정한다. 정책·문제 문맥은 init에서 고정된다.
변경하려면 새 run을 만든다. 중간의 `accepted`는 당시 최고점 후보라는 뜻이며 최종 제출 자격을 보장하지 않는다.

최종 후보는 **모든 지정 환경에서 검증 성공 + 정책 통과**가 필요하다. 그중 최고점을 선택한다.
동점은 먼저 기록된 후보를 유지하며 원본이 가장 먼저 기록된다.
유효한 개선이 없으면 재검증된 원본을 선택한다. 원본의 최종 검증이 실패하면 선택 자체가 실패한다.
새 checkpoint가 추가되면 이전 selection은 현재 결과에서 해제되고, 과거 선택 파일은 이력으로 남는다.

## 문제와 Lean 환경 연결

[problem.json](examples/basic/problem.json)을 복사해 경로·이름·환경을 지정한다.
모든 입력 경로는 설정 파일의 디렉터리 기준이다. `name`은 완전히 한정된 선언 이름이다.
`statement_file`은 proof의 `:=` 앞까지 정확히 보존할 선언문이며, 파일 마지막 줄바꿈만 제거한다.
후보는 `:= by ...`를 포함한 **전체 선언**이다. 원본과 다른 명제나 term-style 증명은 v1에서 거절한다.

각 환경의 `template_file`은 원래 전체 파일 문맥을 보존하고 다음 세 줄만 배치한 템플릿이다.

```lean
-- module 파일이면 module 헤더 뒤에 HARNESS_IMPORT를 둔다.
{{HARNESS_IMPORT}}
import YourProject.Dependencies
{{HARNESS_COMMANDS}}

namespace OriginalNamespace
-- 기존 variable, open, 앞선 정리 등을 여기에 보존한다.
{{DECLARATION}}
-- 대상 정리를 제외한 나머지 선언도 그대로 보존한다.
end OriginalNamespace
```

세 마커는 각각 정확히 한 번, 독립된 들여쓰기 없는 줄에 등장해야 한다.
`HARNESS_IMPORT`는 import 구역, `HARNESS_COMMANDS`는 모든 import 뒤의 전역 문맥,
`DECLARATION`은 원래 대상 선언의 위치다. 대상에 붙은 docstring, attribute, `omit ... in` 등은
선언문에 포함해 statement/baseline/candidate가 함께 보존하도록 한다. 계측기가 다른 명령을 감싸지 않게 하기 위함이다.
`module`에서는 `public import Lean`을 주입하며 일반 파일에서는 `import Lean`을 주입한다.

`environments`에 버전별 프로젝트·템플릿을 여러 개 등록할 수 있다. 중간 평가는 대표 환경,
최종 평가는 모든 환경을 사용한다. 모든 환경은 init 시 실행 가능해야 한다.
`command`는 기본 `["lake", "env", "lean"]`이고 고정된 Lean executable/옵션 argv로 교체 가능하다.
쉘 문자열은 받지 않는다. 임의의 모델/API adapter 역시 별도 프로세스로 붙인다.
`lake env lean`은 lakefile의 모든 `leanOptions`를 자동 적용하는 빌드 호출이 아니므로 필요한 옵션을
argv에 명시한다. 예를 들어 Lean 4.26의 module 프로젝트는
`["lake", "env", "lean", "-Dexperimental.module=true"]`를 사용한다.

### 측정과 검증 범위

- 먼저 계측 import/옵션을 넣지 않은 전체 문맥을 컴파일한다. 이후 계측 사본을 독립 프로세스에서 실행한다.
- 명제를 그대로 보존하고 보수적인 금지 구문 검사를 통과해야 한다.
- 대상 선언의 `Elab.async`를 끈 상태에서 `IO.getNumHeartbeats` 차이를 기록한다. raw와 `raw // 1000`을 모두 보존하고 scaled 중앙값으로 비교한다.
- 대상 선언이 새로 생성됐는지 검사하고, 그 선언이 의존하는 공리를 조사한다. `propext`, `Classical.choice`, `Quot.sound`만 허용한다. `sorryAx`와 새 공리에 의존하면 실패한다.
- 실패·timeout·측정 누락에는 점수를 주지 않는다. timeout 시 자식 Lean을 포함한 프로세스 그룹을 종료한다.
- 이 보수적 검사는 임의의 악성 Lean/tactic 코드를 실행하기 위한 보안 sandbox가 아니다. 신뢰할 수 없는 agent를 실행하려면 evaluator/manifest와 환경을 별도 사용자나 컨테이너로 격리해야 한다.

heartbeat 단위와 비동기 elaboration 처리 근거:
[Mathlib CountHeartbeats 공식 문서](https://leanprover-community.github.io/mathlib4_docs/Mathlib/Util/CountHeartbeats.html).

토큰은 LLM의 BPE 토큰이나 컴파일된 proof term 크기가 아닌 **증명 소스의 lexical token**이다.
[공개 proof_length 구현의 고정 커밋](https://github.com/delta-lab-ai/lean-refactor/blob/05f1dad9719979d1f2d82167fb7aeedf6b85233b/lean_refactor/utils.py)의
어휘 규약을 참고하되, 명제 경계를 명시적으로 사용하고 중첩 주석·공백 처리를 보강한 `lean-source-anchored-v1`이다.
공개 워밍업 15개 원본의 기준 token 수와 15/15 일치함을 확인했다. 모든 구문에서 공식 worker와 동일하다는 보장은 아니다.

## API/agent 담당자 연결 계약

```python
from refactor_eval.session import Session, run_search

session = Session("runs/experiment-001")
session.initialize("path/to/problem.json")

def propose(feedback):
    # 다른 담당자가 구현하는 refactoring API/agent를 여기서 호출한다.
    # feedback: statement, baseline, incumbent_code, latest_code,
    # latest_evaluation(컴파일 오류 포함), scoring, 후보 수
    code = your_agent(feedback)
    if code is None:
        return None  # 정상 탐색 종료: 즉시 최종 평가로 이동
    return {"code": code, "parent_id": feedback["incumbent_id"], "note": "시도 이유"}

selection = run_search(session, propose, max_attempts=20)
print(selection["source"])  # run directory 기준 확정 결과 파일
```

CLI adapter는 매 호출마다 stdin JSON 하나를 읽고 stdout에 `{"code": "...", "parent_id": "...", "note": "..."}`
또는 `null`을 출력한다. 부가 로그는 stderr로 보낸다. adapter가 전달하는 score/선택 의견은 사용하지 않는다.
유료 호출·재시도·예산 제한은 adapter 담당 범위다. adapter 예외/비정상 종료/timeout이면 루프를 중단하며,
이전 checkpoint는 보존한다. 이때 자동으로 정상 종료나 최종 선택을 주장하지 않는다.
`run_search`에 기존 Session을 넘기거나 CLI `checkpoint`/`finalize`로 이어갈 수 있다.

## 매니페스트와 복구

```text
run/
  manifest.json                     설정, 환경 fingerprint, 후보, 평가, 현재 선택
  candidates/baseline.lean           원본 스냅샷
  candidates/candidate-0001.lean      부모 ID, SHA-256으로 연결되는 후보
  evaluations/<candidate>/<pass>/<env>/
    check.lean, check.log            계측 없이 검증한 전체 파일
    measure-1.lean, measure-1.log    실제 compiler 입력과 raw/scaled/axioms
  selections/final-001/
    selected.lean                   선택된 전체 선언
    selection.json                  선택 이유와 모든 후보의 점수/자격
```

최종 출력의 진실 공급원은 `manifest.json.selection`이다. 이 값이 null이면 현재 확정 결과가 없다.
`selection.source` 경로와 `winner.sha256`이 선택된 코드와 연결된다. 최신처럼 보이는 디렉터리 이름만 보고 제출하지 않는다.

`status`로 전체 기록, `feedback`으로 다음 시도용 입력을 확인한다.
컴파일 도중 프로세스가 종료되면 `pending`이 남아 후속 평가/선택을 차단한다.
로그를 확인하고 `recover`를 실행하면 해당 시도를 실패로 남기며 이후 후보를 기록할 수 있다.
원본 측정이 중단/실패했다면 환경을 고친 뒤 새 run으로 시작한다.
finalize가 중단됐다면 `recover` 후 `finalize`로 전체 최종 평가를 다시 수행한다.

파일 잠금으로 동시 쓰기를 차단하고 manifest는 임시 파일 + fsync + replace로 갱신한다.
후보 SHA-256, 설정, 평가기 코드, compiler version, toolchain, Lake lock/config, 프로젝트의 Git HEAD/추적 파일 diff를 검사한다.
필요한 추가 파일은 환경 설정의 `fingerprint_files`로 지정한다.
가져온 모든 `.olean`, Git 미추적 파일, 모든 의존성 checkout을 전부 해시하는 완전한 환경 봉인은 아니다.
정확한 반복 비교를 위해 준비된 의존성과 빌드 캐시를 실행 동안 변경하지 않는다.

## 테스트

```sh
python3 -m unittest discover -s tests -v
REFACTOR_EVAL_LEAN_TESTS=1 python3 -m unittest discover -s tests -v
```

두 번째 명령은 실제 Lean 4.26.0으로 오류→수정→최종 선택, module 문맥, 공리 검사,
계측 import로만 통과하는 후보의 거절까지 확인한다.
상태/점수 테스트는 최종 최고점, 동점, 원본 유지, 상충 정책, 다중 환경, 위조 스냅샷,
환경 변경, 중단 복구, 동시 접근, 유한하지 않은 측정값을 다룬다.

실행 기록과 범위는 [검증 기록](docs/validation.md)에 정리한다.
