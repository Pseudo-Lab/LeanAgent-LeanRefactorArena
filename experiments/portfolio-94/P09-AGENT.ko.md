# P09 제출 증거 복원 및 검증

2026-10-28. 15문제 제출 JSON 준비의 누락 검증을 채우기 위해 맡았다. 제출 후보는 기존 `submissions/warmup/best/P09.lean` 79토큰이며 파일은 변경하지 않는다. 커밋과 공식 제출은 하지 않는다.

## 독립 런타임

요구 pin은4.33.0-rc2,4.32.0,4.31.0이다. `runs/portfolio-94/p09-runtime-{433,432,431}/lib`를 새로 만들고, 기존 P07/P08 산출물과 같은 pin의 Mathlib 캐시를 파일 symlink로 합쳤다. 기존 frozen 라이브러리는 수정하지 않았다. 필요한 CSLib import closure15개 중 기존3개를 재사용하고 누락12개만 컴파일했다. 원본 파일 및 모든 CSLib source input을 각 pin의 원본 tar archive와 byte 단위로 대조했다.

433 첫 빌드는 Mathlib.Data.Set.Finite.Basic 누락으로 실패했고 `attempt1-missing-mathlib`에 보존했다. 이후433/432의 기존 `dependency-*` 캐시,431의 `restore431/cache_union`을 추가해 모두 성공했다. 431의 Arklib cache와 해당 CSLib의 Mathlib revision은 동일한fabf563a7c95a166b8d7b6efca11c8b4dc9d911f였다.

실제 초기 빌드는 pin별로 독점 lease를 획득하고 내부 Lean을 순차 실행했다.433 추가 빌드의 합계 실행시간은20.33초였다. 완료 후 다른 인증 작업의 대기를 줄이도록 builder를 모듈별 lease로 변경했고, 최초 실행 버전을 `build_runtime_pin_lease_snapshot.py`에 보존했다. 두 버전 모두-j1 -M4096을 사용한다.

## 평가 경계

새 `p09_agent_adapter.py`는 target 앞뒤의 실제 전체 소스를 보존하며, target이 측정 진입 전에 존재하지 않는지 검사한다. 원본 문서 주석을 포함한 동일 theorem command를 동기 계측하고, instrumentation을 제거하면 plain source와 byte 단위로 일치해야 한다. 새 frozen run은 adapter/builder/평가기/원본 metadata/환경 입력 해시를 고정한다.

433은 original과79-token seed 각각 Check+독립Audit+3Measure를 실행한다.432/431은 동일 후보의 Check+독립Audit+Measure1을 실행하여 호환성을 확인한다. 호환성 run에는 다른 pin의 baseline을 복사하거나 점수를 계산하지 않는다. `candidates/p09_agent/certification.json`은 각 완료 receipt의 위치와 측정값을 연결한다.

아직 실행 중인 검증은 통과로 계산하지 않는다.

## 새 HB 분석을 적용한 구조 검토

기존79-token 증명은 `Bisimilarity.isBisimulation`이라는 import된 일반 정리를 직접 적용한다. 원본처럼 각 bisimilarity 가정에서 관계 witness를 다시 꺼내 follow_fst/follow_snd와 le_bisimilarity를 조립하는 작업을 반복하지 않는다. 따라서 '이미 생성·검증된 일반 원리 재사용' 전략은 이 후보에 이미 반영돼 있다.

이어 `Exists.imp`/`And.imp`로 transition witness를 직접 옮기고, 실제 CCS transition constructor만 제공한다. 이는 전역자동화에 새 탐색을 맡기는 것보다 최종 증명에서 고정된 성공 경로를 남기는 구조다. 일반 정리 head를 불필요한 polymorphic local alias로 감싸면 constant 정보의 안정성이 오히려 낮아질 가능성도 있어, 근거 없이 별칭을 추가하지 않는다.

이 목표는 재귀 함수의 실행 결과가 아니라 관계에 대한 coinduction이다. 따라서 `fun_induction`을 기계적으로 적용할 대상은 아니다. realization cache 비용이 낮다는 사실만으로 이 증명의HB가 추가 감소한다고 주장하지 않는다. 새로운 counter조작/async설정은 추가하지 않았으며 현재 단계는 기존79의 정확한pin 재검증이다.

## 완료 결과

| pin | tokens | raw HB | 검증 |
|---|---:|---:|---|
| v4.33.0-rc2 |79|507,786|Check+독립Audit+3회Measure|
| v4.32.0 |79|512,854|Check+독립Audit+1회Measure|
| v4.31.0 |79|512,973|Check+독립Audit+1회Measure|

433 후보 samples는 [507786,507805,507772]이고, 같은 환경의 원본은251 tokens /3,855,541 raw 중앙값이다. local score는85.1185348729점이다. 다른 pin에는 원본 baseline을 새로 측정하지 않았으므로 별도 점수를 계산하지 않는다.

최종 파일은 `validated/P09-12c49a5118cd/P09.lean`, manifest는 같은 폴더의 `manifest.json`이다. candidate SHA256은12c49a5118cd4a455ecbc9c793284fe24bb4123803196cf73139ba254aad7f7a이며 기존 제출79-token 파일과 같다. `required_pin_evidence`에 각 완료receipt와receipt hash를 연결했다. `submission-round/evidence_gate.py`의 `_receipt`와 `_receipt_pin`으로 Check/Audit 성공, 소스·로그hash, 실제 증명 포함, 허용공리, 환경identity/pin을 모두 재검증했다.

공식 제출과 커밋은 하지 않았다. 새 증명을 더 낮은HB로 바꿨다는 결과가 아니라 기존 선택본의3개 필수pin 인증을 복원한 결과다. 제출 완성을 우선하여 P06의추측후보 추가 실행은 보류했다.
