# 선택적 Strategy Bank와 free/guided 혼합 탐색

최신 공통 `actions-v1` 요청·응답·기록 재생 경로에 Bank를 연결한다.
설정을 생략하면 기존 요청 형식과 실행 정책을 유지한다. provider, 예산 예약,
평가기, portfolio 할당량·반복 방지·다중 라운드·최종 선택은 기존 구현을 사용한다.

## 설정과 실행

준비된 공통 CLI 설정을 새 파일로 복사하면서 Bank를 포함한다. Bank 내용은
설정에 내장되어 run input과 함께 동결된다. 상대 경로는 원래 설정 파일을 기준으로
절대 경로로 변환한다. 기존 설정·출력 파일은 덮어쓰지 않는다.

```sh
python3 scripts/configure_strategy_bank.py \
  --config /path/to/prepared-actions-config.json \
  --bank configs/strategy-bank/team-v1.json \
  --contextual --top-k 3 --search-policy alternating-v1 \
  --output /path/to/new-bank-config.json

PYTHONPATH=src python3 -B -m lean_agent run \
  --config /path/to/new-bank-config.json --output /path/to/new-run
PYTHONPATH=src python3 -B -m lean_agent replay /path/to/new-run
python3 scripts/export_strategy_trace.py \
  --run /path/to/new-run --output /path/to/new-trace.jsonl
```

설정 도구는 API·Lean을 호출하지 않는다. `run`은 원래 설정의 backend를 따른다.
`fixture`이면 저장된 응답을 사용하고, `openrouter`이면 기존 인증·비용 정책으로 호출한다.
고정 응답 파일에는 각 호출에 대응하는 JSON action 문자열이 있어야 한다.

`agent.strategy_bank.bank`에는 파일 경로 대신 JSON 내용을 넣는다.
실제 Bank에는 1~30개 유효 카드가 필요하다.
`search_policy`를 생략하거나 `guided`로 설정하면 항상 추천한다.
`contextual`은 현재 best의 코드·목표와 최근 실패를 추천에 반영하는 옵션이다.
v1 전술/태그 카드와 v2 구조 신호 카드, 최대 3개 추천을 지원한다.

Final 배치의 `prepare`/`inputs`에서는 다음 옵션으로 같은 설정을 동결한다.
배치 설정 형식은 공통 CLI 설정과 다르므로 위 설정 복사 도구를 배치에 사용하지 않는다.

```sh
PYTHONPATH=src python3 -B experiments/final-batch-next/driver.py prepare \
  --root runs/final-batch-next/NEW-BANK-RUN --rows 51 35 --workers 1 \
  --strategy-bank configs/strategy-bank/team-v1.json \
  --strategy-contextual --strategy-top-k 3 --strategy-search-policy alternating-v1
```

`run`에는 정책 옵션을 다시 넘기지 않는다. 기존 입력을 재사용할 때 옵션을 생략하면
동결된 Bank를 유지하며, 다른 Bank·검색 정책을 요청하면 새 root를 요구한다.
미설정 새 배치는 Bank를 사용하지 않는다. provider·비용 상한은 기존 배치 설정을 따른다.
배치의 추천은 문제별 `steps/*/request.json`, 선택 선언은 `event.json`에 남는다.
위 `export_strategy_trace.py`는 공통 CLI run의 스냅샷 형식용이다.

## 혼합 정책과 기록

- `alternating-v1`은 각 scout/merger의 첫 후보를 `free`로 시작한 뒤 `guided`와 교대한다.
  다중 라운드에서도 각 역할이 새로 시작할 때 free로 초기화한다. portfolio의 역할별 평가 수를
  사용하므로 다른 scout의 후보나 이전 라운드 seed가 순서를 바꾸지 않는다.
- portfolio가 없는 actions 실행에서는 baseline을 제외한 누적 후보 수로 교대한다.
  유효·무효 Lean 평가와 repair는 후보 수에 포함한다. 도구 조회, 응답 형식 오류,
  평가 전에 거절된 중복 후보는 교대 횟수에 포함하지 않는다.
- free 요청에는 카드·추천 신호·힌트를 넣지 않는다. 과거 action과 후보 요약의 명시적
  `strategy`·`strategy_ids` 등은 복사본에서 제거한다. 응답 작성에 필요한 action schema의
  `strategy` 필드는 유지한다. 저장된 원본 기록은 바꾸지 않는다.
  도구 결과의 문자열 피드백은 명시적 전략 이름이 다시 노출되지 않도록 제거하고,
  같은 결과를 담은 정리된 `recent_actions[-1].observation`을 참조한다.
- 원본 비공개 scout-a에서는 후보 수와 무관하게 Bank 추천을 차단한다.
  이미 생성된 증명과 검증 피드백은 공유한다. free는 독립 실험군이나 편향 제거가 아니다.
- guided의 `propose`/`repair`는 선택한 카드 ID를 선택적 `strategy_ids` 배열(중복 없는 0~3개)에
  남길 수 있다. 미설정·알 수 없는 ID는 평가 전에 거절한다. 추천되지 않은 등록 카드를
  선택한 경우도 추적에 구분한다. ID는 선택 선언이며 실제 적용·인과 효과의 증거가 아니다.
- trace는 요청별 mode, 추천 ID, 선택 ID, 후보 작성, 실제 평가 환경, 검증 결과와 비용을
  분리한다. 대표 버전의 attempt를 전체 필수 버전 통과로 표시하지 않는다.
- 두 Bank 모듈·설정·요청·응답은 기존 run snapshot과 manifest에 포함된다.
  replay는 동결된 코드로 mode·추천·후보 계보·비용·선택을 재구성한다.

## Bank 출처와 해석

`configs/strategy-bank/team-v1.json`은 [PR #69의 Bank](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/c1c639c31eb33bf211dbbe600863dbca826760d0/experiments/putnambench-mixed-bank/bank/bank.json)를
byte-exact로 보존한 20-card Bank다. 같은 Bank는 [PR #71](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/pull/71)에서도 사용했다.
Bank/신호 구현과 혼합 정책은 #69, 공통 연결부·추적 설계는 #71의 동결 코드를 참고해
필요한 부분만 이식했다. rule scoring은 박채원님의 [PR #50](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/pull/50)에서
유래한 all/any 조건·전술 최소치·안정적 동률 순서를 따른다.

카드는 같은 Final 문제의 기존 개선 관찰에서 도출됐으며 모두 `review_required`다.
현재 문제 자신의 evidence는 추천 근거에서 제외하고, 다른 문제 근거가 없는 카드는 제외한다.
여러 문제로 만든 카드의 문구까지 재작성하는 완전한 leave-one-out은 아니다.
독립 holdout·미지 문제 일반화·Bank 단독 성능·공식 제출 적합성을 주장하지 않는다.
원본 diff·관찰·생성 비용 등 상세 근거는 #69·#71에 보존한다. 이 기능의 통합은 해당
연구 실행을 OpenRouter 공식 제출이나 대회 비용 준수 인증으로 바꾸지 않는다.

## 검사

```sh
python3 -B scripts/check_common_harness.py
```

합성 응답·평가기 회귀는 Bank 제외 시 요청, hidden/free/guided, 실패 제외,
후보와 도구 호출의 구분, 라운드 seed, 반복 방지, 잘못된 ID, 동결 replay와
trace의 해석 범위를 검사한다. 실제 두 문제 검증은
[`strategy-bank-validation.json`](strategy-bank-validation.json)에 별도로 기록한다.
실제 유료 호출로 수행한 Putnam·ArkLib 검증과 free 피드백 수정 근거는
[`strategy-bank-paid-validation.json`](strategy-bank-paid-validation.json)에 기록한다.

실제 ArkLib 문맥 확인 중 발견한 계측 경계도 보완했다. preflight는 대상 자리에
익명 `True` 예제를 넣어 대상의 docstring·지역 지시문을 소비하되 원본/후보 정리는
검사하지 않는다. 실제 정리 검증은 이후 baseline/candidate/final 단계에서 수행한다.
계측 renderer는 대상 직전 docstring과 한 줄 `omit/include/open/set_option … in`을
계측 command 안으로 옮겨 원래 선언에 붙인다. 다른 선언·전역 문맥은 그대로다.
