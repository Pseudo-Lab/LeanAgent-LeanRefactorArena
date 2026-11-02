# HB 조사 이후 15문제 제출 라운드

목표는 앞선 HB 계측 연구와 증명 탐색에서 얻은 후보를 실제 15문제 업로드 파일로 만드는 것이다. 최종 제출은 사용자가 한다. 작업 브랜치는 기존 `exp/cost-hypothesis-pipeline`을 이어 썼고, 공식 제출이나 커밋은 하지 않았다.

## 구성

- `selection-baseline.json`: 이번 라운드 시작 시점의 후보 경로. 이후 최선 후보와 구분해 보존한다.
- `probe_small.py`, `small_batch.py`: P01·P02·P04·P13·P14·P15의 원본 문맥 Check, 독립 Audit, 동기식 전체 선언 HB 측정.
- `selection-current.json`: 실제 내보낼 후보의 SHA, 검증 기록, 요구 버전 성공 목록.
- `archival-evidence.json`: P01·P02·P03·P13·P14·P15의 과거 성공 기록을 현재 후보 SHA와 대조한 결과. 검증 강도의 차이와 원격 CI 로그 미보유를 명시한다.
- `evidence_gate.py`: 선택의 `verified_pins` 값을 신뢰하지 않고 성공 증거에서 버전을 유도한다. 다른 증명에 이전 성공 기록을 붙이면 실패한다.
- `export_bundle.py`: 정확한 15개 원문 선언, 이름, 공리 검사 증거, 공개 금지 패턴, proof SHA, JSON 왕복 파싱을 확인한 뒤 JSONL와 열람용 JSON을 만든다.
- `export-review.json`: 중간 묶음의 독립 검토.
- `final-export-review.json`: 최종 JSONL SHA에 대한 독립 검토. 파일이 바뀌면 이전 검토를 새 묶음의 검토라고 간주하지 않는다.

결과는 워크트리의 `submissions/warmup-hb-20261028/`에 저장한다. 최종 호환성 상태와 개별 증거는 그 폴더의 `manifest.json`을 기준으로 읽는다.

## 이번 라운드에서 드러난 점

1. **자동 탐색을 지웠다는 이유만으로 더 좋다고 볼 수 없다.** P04의 `fun_prop`를 실제 Physlib용 `Continuous.inner'`로 바꾸면 raw HB가 1,406,888에서 1,406,735로 조금 줄지만 Length가 123에서 126으로 늘었다. 원본 대비 두 지표를 함께 보아 기존 후보를 유지했다. 앞선 `Continuous.inner` 대체는 이 문맥이 Mathlib의 `InnerProductSpace` 대신 Physlib의 `InnerProductSpace'`를 쓰므로 실패했다.
2. **명시할 부분과 추론시킬 부분을 함께 선택해야 한다.** P13에서 감소 조건에 `Nat.sub_lt`를 명시하면 HB가 줄지만 인덱스까지 반복하면 259→263 tokens가 된다. 인덱스를 `_`로 추론시키면 259 tokens를 유지하고 같은 환경의 raw HB가 3,659,724(기존 1회)→3,522,969(새 후보 3회 중앙값)로 감소했다. 새 후보는 전체 3개 요구 버전의 Check/Audit를 통과해 채택했다.
3. **P05·P06·P10·P11은 이득이 큰 구조적 후보를 확정하는 데 집중했다.** 분모의 순서, 쌍선형 기저를 통한 extensionality, cardinality/coercion 명시, 계수 순서와 `rfl`이 핵심이다. 성공했던 빠른 탐색 결과를 그대로 제출 확정으로 취급하지 않고 별도 Check/Audit와 HB 3회로 재검증했다.
4. **이미 해 본 실패 실험을 재사용하면 탐색 낭비를 줄일 수 있다.** P08의 직접 `refl`, 명시 witness, `let`/`match` 후보는 이전에 길이나 HB가 악화했다. 이번 읽기 전용 재검토에서도 더 나은 국소 변경의 근거가 없어 185-token 후보를 유지했다.
5. **내보내기 자체에도 후보 혼동 방지가 필요하다.** 초기 exporter는 `verified_pins`를 그대로 믿었다. 독립 검토 후 실제 증거의 proof SHA와 성공 버전에서 상태를 유도하도록 수정했다. 다른 유효한 증명으로 바꾸고 예전 증거를 유지한 사례들을 의도적으로 넣어 모두 거부되는지 확인했다.

## 계측 연구와 제출 코드의 관계

`HB-METRIC-AUDIT.ko.md`의 counter restore/async 경계 실험은 측정 의미를 이해하기 위한 진단이다. 이번 제출에는 임의 counter 변경이나 커스텀 메타프로그램을 넣지 않았다. 함수 귀납 원리와 기존 정리의 재사용처럼 실제 증명에 적용할 수 있고 검증을 통과한 방법을 사용했다. P15에서는 `decide +kernel`, 일반 `decide`, `rfl`을 실제 닫힌 산술 목표에서 비교했다. 일반 `decide`와 불필요한 `push_cast` 제거 후 `ring1`을 결합한 후보가 283→281 tokens, 같은 4.25 환경 raw HB 2,628,784(기존 1회)→2,499,913(새 후보 3회 중앙값)으로 개선했다. 4.25·4.26·4.27의 Check/Audit를 모두 통과해 채택했다.

여러 후보를 찾는 데 쓴 시간은 제출 HB와 구분한다. 소스 코드가 짧아지는 변경과 검증 과정이 덜 드는 변경도 구분한다. 로컬 추정 점수, 역사적 공식 기록, 현재 공식 서버의 미확인 점수를 하나의 확정 수치로 섞지 않는다.

## 최종 산출물

`submissions/warmup-hb-20261028/submission.jsonl`을 `--require-complete` 옵션으로 내보냈다. 필수 36개 문제·버전 조합의 증거가 모두 연결됐으며 pending은 없다. JSONL SHA-256은 `6ac28ac0292fd20a522bffb51734c74c30a6b7163f97c3f6955fe59fd6efa212`, 크기는 21,686 bytes다. 제출 Length 합계는 2,722 tokens, 문제별 평균 Length 감소율은 79.8465%다. 공식 제출과 채점은 아직 하지 않았다.
