# 기존 도구 연결과 참고 출처

## 이 저장소에서 실행하기

계획 JSON은 준비할 문제/환경 목록이다. 실행기 설정 파일이나 검증 결과는 아니다. `name`이 공식 문제 ID이고 `input_line`은 원본 JSONL의 물리적 줄 번호다. 환경은 출처·Lean 버전·commit 전체가 같을 때만 공유한다. `budget_key`는 같은 문제의 여러 실행 비용을 합칠 키다.

환경 준비에는 [공통 하네스 사용법](../../../docs/first-harness.md)과 [외부 라이브러리 연결](../../../docs/api-integration.md)을 따른다. 공식 JSONL에서 실제 문제 설정의 `name`, `statement`, `reference`를 만들 때 `reference`에는 `src` 전체 선언을 사용한다. 원본 파일·imports·namespace와 대상 선언 위치를 보존한다. prepared 환경과 문맥 template을 만들고 모델 호출 전에 원본을 검사한다.

현재 main 공통 루프는 실행 하나에 환경 하나를 넘긴다. batch 계획을 `lean-agent run --config`에 직접 전달하거나 다중 환경 실행이 연결됐다고 간주하지 않는다. 버전별 실행 또는 아래 다중 환경 검증 도구로 연결한다. [#41](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/pull/41)의 목표 수집·재귀 수리와 예산 연결은 별도 PR이므로 main에 설치된 기능으로 가정하지 않는다.

공통 CLI는 Python 환경과 `PYTHONPATH=src`를 설정한 뒤 사용한다.

```sh
python3 -m lean_agent check --config configs/problem.local.json --output runs/manual/problem-check
```

`check`는 모델을 호출하지 않지만 Lean과 로컬 환경은 필요하다. 설정 예시는 `configs/smoke.json`이다. `check`와 실제 `run`은 각각 새 출력 폴더를 쓴다. 상태 조회·replay는 기록 확인이며 중단된 유료 실행의 자동 재개가 아니다. 현재 `cost_stop_usd`는 응답 뒤 한도 도달 시 종료하므로 엄격한 사전 예산 제한을 별도로 연결해야 한다.

### 이미 준비된 문제에서 로컬 편집·검증

다음 변수에는 실제 문제 폴더, 검증한 시작 후보, 공식 기준값과 출처를 확인한 값을 지정한다. `ARENA_PACKET`은 `input.json` 또는 `agent-input.json`과 `environment.json`을 담는다. 후자의 `environments`가 계획에서 **해당 문제**에 지정한 모든 버전·commit과 일치하는지 확인한다. `make_environment.py`는 이미 준비된 패킷용이며 Final JSONL을 직접 받는 도구가 아니다. 파일 없는 standalone header 문제도 해당 문맥 형식으로 별도 준비한다.

```sh
python3 experiments/proof-golf/trial.py \
  --problem-dir "$ARENA_PACKET" --base "$ARENA_SEED" \
  --trials "$ARENA_TRIALS" --output "$ARENA_TRIAL_OUTPUT" \
  --t0 "$ARENA_T0" --h0 "$ARENA_H0" --workers 1

python3 experiments/proof-golf/golf.py \
  --problem-dir "$ARENA_PACKET" --seed "$ARENA_SEED" \
  --output "$ARENA_GOLF_OUTPUT" --t0 "$ARENA_T0" --h0 "$ARENA_H0" --workers 1

python3 experiments/proof-golf/verify.py \
  --problem-dir "$ARENA_PACKET" --candidate "$ARENA_CANDIDATE" \
  --output "$ARENA_VERIFY_OUTPUT" --t0 "$ARENA_T0" --h0 "$ARENA_H0"
```

trial/golf는 대표 버전 screening이다. verify는 등록된 모든 환경에서 check와 3회 HB 계측을 한다. 등록 환경이 공식 전체인지 확인하는 책임이 남는다. HB의 raw/천 단위를 구분하고, 공식 기준값과 로컬 실측 기준값을 섞지 않는다. 로컬 점수는 공식 worker 결과가 아니다. 원본과 후보가 같은 조건에서 측정됐는지 먼저 확인한다.

## 상류에서 반영한 부분

아래 문서·구현의 절차와 아이디어를 이 저장소용 지침으로 정리했다. 상류 코드나 플러그인을 vendoring하지 않으며, 자동 설치·연결을 하지 않는다. 링크는 검토한 commit에 고정했다.

| 출처 | 이번 스킬에 반영한 부분 | 그대로 적용하지 않은 부분 |
|---|---|---|
| [lean4-skills: golf](https://github.com/cameronfreer/lean4-skills/blob/83582df9d9172456993929f32ac4dd9d99c6211c/plugins/lean4/commands/golf.md), [review](https://github.com/cameronfreer/lean4-skills/blob/83582df9d9172456993929f32ac4dd9d99c6211c/plugins/lean4/commands/review.md), [checkpoint](https://github.com/cameronfreer/lean4-skills/blob/83582df9d9172456993929f32ac4dd9d99c6211c/plugins/lean4/commands/checkpoint.md) | 검색·작은 편집·피드백·검토·체크포인트 | 스타일·전술 복잡도에 따른 채택 순위를 실제 토큰/HB/호환성 비교로 조정. 자동 Git 작업과 추가 모델 위임은 요구하지 않음 |
| [Lean Refactor](https://github.com/delta-lab-ai/lean-refactor/blob/a2372caad69ab61a42a0e997106b87e00d9d7d65/README.md) | 전략 선택 → 후보 편집 → 오류 교정·재평가 | bundled Mathlib·직접 provider 연결·호출 횟수 예산을 Arena의 고정 환경·OpenRouter·달러 장부로 대체 |
| [LeanPolish](https://github.com/paulinebourigault/leanpolish/blob/70cda81a15cca1f805885df197361102f0123cbb/README.md) | 작은 삭제·전술 대체 후보, 구조 변경 후 재축소, 새 프로세스 확인 | Lean/Mathlib 4.21.0 구현을 그대로 실행하거나 전술 메뉴 전체의 이식을 전제하지 않음 |
| [LeanRefiner](https://github.com/Tristan-sdu/LeanRefiner/blob/2f8ea4d95484cefe1684e1b569cb2a2000474107/README.md) | 큰 구조 변경과 국소 축소를 분리 | Lean 4.26.0·Claude CLI 기본 경로·길이만의 판단을 공통 조건으로 쓰지 않음 |
| [lean-lsp-mcp](https://github.com/oOo0oOo/lean-lsp-mcp/blob/ee7d833e1244bcc48e818efd58b402477175ad91/README.md) | 목표·가정·진단을 편집 피드백으로 사용 | MCP 성공이나 검색 결과를 최종 파일 검증으로 대체하지 않음 |
| [LeanInteract](https://github.com/augustepoiroux/LeanInteract/blob/768e18ebcb5c7ec34d308768a785389eeac37798/README.md) | Python/REPL 피드백의 선택적 연결 방식 | README 지원 범위만으로 Arena 모든 프로젝트·버전 통합을 가정하지 않음 |
| [Loogle](https://github.com/nomeata/loogle/blob/9f11169aaebf1ed1e7dcc4077f2aafe0fcf66fd0/README.md) | 대상 프로젝트와 같은 toolchain의 로컬 선언·타입 검색 | hosted 검색 인덱스를 고정 버전 API의 존재 근거로 쓰지 않음 |
| [lean-beam](https://github.com/leanprover/lean-beam/blob/6417176a373ee1184feebca62a4cfcc464349458/docs/COMPATIBILITY.md) | 지원 버전에서 상태를 유지한 후보 시험 | 4.34–4.36 지원창을 모든 Final 버전 지원으로 확대하지 않음 |
| [mathlib-quality](https://github.com/CBirkbeck/mathlib-quality/blob/32f54b733200f16169d3279c1b07cd67b6df53ed/README.md) | baseline 확인·느린 부분 확인·수정 후 재측정 | 파일 전체 스타일 수정·선언 일반화·새 helper·무제한 실행 절차는 가져오지 않음 |
| [ImProver](https://github.com/riyazahuja/ImProver/blob/259aa19a06183d5ccd87a32fb3a396d1de03b930/README.md) | 명시한 지표를 기준으로 후보를 생성·수정·평가하는 흐름 | 단계 수/가독성 지표나 기본 API 경로를 대회 지표·호출 경로로 간주하지 않음 |

기존 공통 검증과 로컬 단축 도구는 [#35](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/pull/35)를 재사용한다. 이 스킬의 테스트는 계획 생성과 입력 경계 검증이며 상류 도구의 성능 재현 실험이 아니다.
