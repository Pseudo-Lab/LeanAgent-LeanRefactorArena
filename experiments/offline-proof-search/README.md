# 제출 증명을 위한 지속형 로컬 탐색

`exp/cost-hypothesis-pipeline` 브랜치의 별도 실험이다. 기존 48후보 A/B 코호트의 코드·규칙·결과는 변경하지 않는다. 탐색 시간과 후보 수는 점수 벌점이 아니다. 최종 목적은 필수 버전 호환을 유지하면서 `L/L₀ + H/H₀`를 줄이는 것이다.

첫 P12 실험은 34개 후보를 탐색해 **362→178토큰, primary raw HB 4,111,012→3,017,981**을 얻었다. 동일 후보의 필수 세 버전 검증과 기록 감사를 완료했다. [성과와 인사이트](INSIGHTS.ko.md), [선택한 선언](validated/P12.lean), [검증 manifest](validated/manifest.json).

2026-10-28 후속 탐색은 **178→156토큰, primary raw HB 3,017,981→2,805,356**으로 추가 개선했고 필수 세 버전 검증을 마쳤다. [두 번째 라운드 결과](ROUND2.ko.md), [새 검증본](validated/20261028/P12.lean). 첫 라운드 파일은 보존했다.

## 구현 범위

- `lookup.py`: 원래 target 앞부분과 import 관계에서 소스 검색. 원래 target 본문·suffix를 검색 대상에서 제외한다. 발견한 3,000개 이상 소스의 해시와 없는 소스 목록을 저장한다. Lean의 export 검사나 타입 기반 검색 엔진은 아니므로 실제 사용 가능성은 후보 컴파일로 확인한다.
- `search.py`: 별도 실행 디렉터리, 고정 코드/환경 지문, 순차 Lean 실행, 선언 검증, 전체 원문 plain compile, 별도 공리 검사, 동기 fresh HB 측정, 후보 계보·Pareto 보존, 중복 소스 평가 방지, 재개 가능한 탐색.
- `mutations.py`: 규칙 목록의 전체·부분 삭제, `only` 유무, 단순 named argument 삭제, 일부 독립 tactic 삭제. 이 생성기는 정확성을 주장하지 않으며 실패도 기록한다.
- `submit`: 사람이거나 모델이 검색 결과로 만든 새로운 구조 후보를 같은 기록에 넣는다. 자동 변형만으로 구조 발굴을 대체하지 않는다.
- `certify`: 원본·시작 후보·선택 후보를 각각 새 프로세스 세 번 재측정한다. 확인 측정에서 시작 후보가 더 좋으면 시작 후보로 돌아간다.
- `polish.py`: 현재 최선의 named argument 삭제를 따로 탐색한다. 단순 규칙 삭제가 정체돼도 다른 종류의 편집을 이어갈 수 있다.
- `diagnose_p12.py`: 전체 원문에서 구간별 HB를 관측한다. 계측 tactic을 먼저 컴파일해 marker 자체의 부담을 줄인다. 계측된 증명과 값은 제출 후보·점수에서 제외한다.
- `audit.py`, `summarize.py`: 원문 문맥·코드/로그 해시·fresh nonce·공리·raw 표본을 재생 확인하고 같은 코드의 세 pin 결과를 연결한다.
- `verify_all_p12.py`: primary 확인 측정과 4.30·4.29 검증을 순차 실행하고 완료 단계는 확인 후 재사용한다. 불완전한 단계는 보존하고 중단하며 덮어쓰지 않는다.

현재 전체 소스 adapter는 기존 P12 `full_probe.py`이며 계측 marker도 P12 전용이다. 임의 문제에 즉시 적용되는 범용 Lean 서비스라고 주장하지 않는다. 초기 탐색은 4.31 primary-only이고 다른 pin 검증은 별도 수행해야 한다.

## 실행

아래 명령은 저장소 worktree 루트 기준이다. `init`에는 새 디렉터리를 사용한다. `search`의 `--steps`는 이번 호출의 작업 묶음 크기이며 전체 후보 예산이 아니다. 다시 실행하면 기존 평가를 보존하고 다음 후보로 이어간다.

```sh
python3 -B experiments/offline-proof-search/search.py init runs/offline-proof-search/NEW \
  --adapter /absolute/path/to/p12/full_probe.py \
  --environment /absolute/path/to/environment_P12.json \
  --seed /absolute/path/to/P12.lean

python3 -B experiments/offline-proof-search/lookup.py runs/offline-proof-search/NEW \
  'lemma_pattern' --output runs/offline-proof-search/NEW/lookup-01.json

python3 -B experiments/offline-proof-search/search.py submit runs/offline-proof-search/NEW \
  /absolute/path/to/new_candidate.lean --note '정리 검색에서 발견한 구조 변경'

python3 -B experiments/offline-proof-search/search.py search runs/offline-proof-search/NEW --steps 20
python3 -B experiments/offline-proof-search/search.py certify runs/offline-proof-search/NEW

# P12의 나머지 필수 pin runtime이 복구된 뒤 수행한다.
python3 -B experiments/offline-proof-search/verify_all_p12.py runs/offline-proof-search/NEW \
  --research-root /absolute/path/to/insights-20261024-round7
```

초기 원본·seed는 각 세 번, 탐색은 한 번, 최종 확인은 다시 세 번 측정한다. 모든 평가에는 plain compile와 별도 axiom audit가 포함된다. 실패/timeout은 HB 0으로 취급하지 않는다. 한 번 측정한 작은 차이는 확정 성과가 아니다. 표본 분산과 필수 pin 결과를 함께 보고한다.

탐색 중에는 `state.json`의 `best`가 잠정 최선이며, `confirmed.lean`은 확인 측정이 선택한 코드다. `confirmation-*.json`의 정확한 코드 SHA와 측정값을 함께 사용한다. 기존 `confirmed.lean`이 있다는 사실만으로 이후 추가 탐색 후보까지 검증됐다고 해석하지 않는다.

코드가 바뀌면 기존 실행의 지문 검사가 실패한다. 이전 실행 파일을 덮어쓰지 말고 새로운 실행 디렉터리에서 시작한다. 입력 원문과 참조하는 기존 runner 및 tokenizer는 수정하지 않는다. 실행당 프로세스 timeout은 고장 난 후보를 멈추기 위한 장치이며 전체 탐색 시간을 제한하지 않는다.

최종 세 pin 검증 이후에도 `search`/`submit`으로 후보 탐색을 이어갈 수 있다. 더 좋은 코드가 생겼을 때 기존 `RESULTS.json`과 pin 검증 디렉터리를 덮어쓰지는 않는다. 새 검증 묶음에는 새로운 실행 디렉터리를 만들고 해당 후보를 seed로 전달한다. 현재 `verify_all_p12.py`는 이전 후보와 새 후보가 섞이면 중단하도록 되어 있다.

## 검증과 제한

```sh
python3 -B -m unittest discover -s experiments/offline-proof-search -p 'test_*.py' -v
```

중첩 규칙 구문, 원문 statement 보존, 목적함수의 길이/HB 교환, Pareto 판정, import header의 주석 처리 등을 검사한다. 새 전략의 실증 결과는 별도 결과 문서에 기록한다. 모델·유료 API 호출, 공식 제출, 커밋은 자동 수행하지 않는다.

소스 검색은 설치된 일부 Lean core 소스가 없으면 부분적이다. 검색 실패를 정리 부재의 증거로 쓰지 않는다. 비교 환경은 기존의 정확 pin 복원 환경이며 공식 worker와 bit-identical하다는 뜻은 아니다. compiler·runtime·원문/manifest 지문을 확인하지만, 이를 매 평가마다 모든 의존성 파일을 다시 해시한 것과 동일시하지 않는다.
