# 탐색·하네스·검증 기법

구현 경로는 원래 arena 체크아웃 기준이다. 이 문서 브랜치가 아래 모든 구현을 기본 패키지에 편입하는 것은 아니다. 경로별 존재·내용 비교는 [Git 감사](evidence/git-audit.json), 실제 시행 수치는 [실험 비교](experiments.md)에 있다.

## 1. 이미 main에 있는 기반을 중복 구현하지 않기

| 기반 | 현재 상태 | 후속 실험과의 차이 |
| --- | --- | --- |
| preflight·오류 피드백·status/replay | PR #3 반영 | 장기 실패 기억과 SQLite 복구는 아님 |
| prepared 환경의 SHA 검증·stat cache | PR #33 반영 | 같은 파일 stat을 이용해 **내용 검증 작업**을 재사용. Lean 성공 판정을 재사용하는 기능이 아님 |
| usage/cost 통합 | PR #31·#34 반영 | 기록·비용 보고 기능과 발송 전 금융 예약·불확실 응답 처리 정책을 분리 |
| 예산 API runner·direct adapter·기본 golf·프로파일러 | PR #35 반영 | local v5 이후의 컨트롤러·검색·작업 큐까지 기본 탑재된 것은 아님 |

prepared cache는 opt-in이고 기본값은 full 검사다. 수정된 라이브러리·다른 compiler/pin을 검증 생략하는 허가가 아니다. 실험 보고 시간에 시작/종료의 전체 해시 비용을 포함했는지도 구분해야 한다.

## 2. 공통 전략·구조화 계획: v5와 v6

v5 연구는 문제별 정답 힌트 없이 공통 지침과 원래 문제/허용 문맥을 주는 실험이다. 하지만 준비된 API 대조군 연구는 `deferred_after_user_scope_correction`, 비용 0으로 남아 있다. 실제 완료한 local-agent 40회 연구와 유료 API 연구를 같은 것으로 부르면 안 된다.

v6는 route 가설, 인용 근거, 2–8개 claim DAG, bridge, falsifier와 explore/refine/repair를 기록한다. exact/comment-only 반복을 거절하고 평가 예약·소스 해시·best/Pareto·최종 독립 검증을 장부로 연결한다.

**검증된 것은 최종 Lean 증명과 컨트롤러 계약이다.** 인용문 일치가 가설의 의미를 증명하지 않고, 완성 증명 검증이 각 claim DAG 노드를 독립적으로 증명하지 않는다. 경로 설명의 개수가 수학적 경로 다양성도 보장하지 않는다.

초기 v6의 두 번 실패 시 route quarantine, 여섯 번 정체 시 재고 힌트는 나중 v9에서 제거됐다. 모든 버전의 정책을 한꺼번에 쓰는 단일 완성 설계처럼 정리하지 않는다.

원래 구현: `experiments/common-v5-study-20261030/`, `structured-reasoning-20261030/`, `structured-openai-20261031/`. 모두 main 미반영이다.

## 3. 상태와 외부 비용을 안전하게 이어가기: v7

`src/lean_agent/workflow.py`와 v7 실행기는 case/API call/Lean 관찰/실패 기억/해시 연결 이벤트를 SQLite 트랜잭션에 기록한다. FULL sync, Decimal 금액 문자열, case lock을 사용한다.

API 발송 의도와 응답 receipt를 외부 HTTP 실행 전후에 저장한다. 응답이 불확실한 요청은 예약 비용을 유지하고 차단하며, **자동 재발송하지 않는다**. 로컬 Lean 중단은 같은 immutable 후보·같은 평가 slot을 복구한다. 알려진 response receipt가 있으면 이를 조정하되 새 유료 호출로 바꾸지 않는다.

영구 진단은 metavariable 주소만 정규화하고 상수·타입·실패 표현을 유지한다. route를 바꿨다고 같은 실패를 잊지 않는다. 다만 v7의 top-eight 표시와 정체 임계값은 후속 연구에서 바뀐 정책이다.

오프라인 recovery/replay 근거가 있으며 main에는 해당 파일이 없다. 이후 실험에서 상태 머신을 계승했다는 것과 v7 단독 새 유료 실험의 효과가 검증됐다는 것은 별개다.

## 4. workload를 줄인 빠른 모드: v8

중간 측정 1회, case별 golf 40 screen/180초, API 탐색과 golf 큐 분리로 컴파일 작업량을 줄였다. baseline/final은 3회 측정을 유지했다.

P10 파일럿에서 실행은 약 37분 29초였지만 과거보다 조건부 점수가 79.84→78.09로 낮아졌다. 과거 실행은 queueing/resumption을 포함하므로 wall ratio도 순수한 동일 품질 가속 실험이 아니다. **검증이 된 tradeoff 모드이며, 동일 품질의 가속으로 증명된 것은 아니다.**

후속 v9/v10은 중간 3회와 전체 golf를 복원했다. v8 cap을 v10의 상시 규칙으로 소급하지 않는다.

## 5. 원래 범위의 완전한 타입·실행 경험: v9

소스의 첫 `:=`를 정리 본문 경계로 삼으면 P11처럼 결과 타입 안의 `let :=`에서 타입이 잘린다. compiler syntax의 실제 declaration-body span으로 본문만 제거해 타입과 타입 안의 proof term을 유지하는 파서가 필요했다.

v9는 원래 import 범위에서 canonical type/axiom을 조회하고, 이번 실행에서 검증된 변경을 소스 span·증명 해시와 연결해 기록·조합한다. helper import로만 보이는 이름을 솔버에게 노출하지 않는다. 관찰된 patch는 일반적 의미 보존 rewrite 정리가 아니므로 조합 후보도 Lean으로 검사한다.

shared source transformation은 `src/lean_agent/proof_experience.py`에 있다. 준비 입력·원래 prefix·compiler/project/index/helper 해시를 맞춰 다른 scope의 조회 결과가 섞이지 않게 한다.

하지만 완료된 유료 세 문제 연구는 작업 문맥 누락으로 같은 정보를 반복 조회했고, 비용의 76.74%가 inspection에 쓰였다. 40회 목표를 채우지 못했다. “타입 조회를 제공하면 점수가 개선된다”는 결론은 나오지 않았다.

## 6. 바이트 보존 golf와 검증 선별·병렬화: v10

| 요소 | 구현한 보장 | 하지 않는 것 |
| --- | --- | --- |
| 소스 구간 편집 golf | 편집하지 않은 바이트·줄·문자열·주석 유지 | 재구성 과정에서 본문을 버린 옛 parser 사용 |
| LSP snapshot negative prefilter | 같은 immutable prefix에서 후보+suffix만 교체, version·diagnostic completion·nonce 확인 | 이전 후보 정리를 다음 후보가 사용하는 것 |
| fresh CLI admission | 완료된 실패만 선별에서 거절; pass/unknown은 새 CLI 검증 | LSP 성공만으로 후보 채택 |
| fresh final 측정 | plain check 후 독립 프로세스 3개 측정 | warm/LSP heartbeat로 순위 계산 |
| shared FIFO | 전역 compiler slot·owner lock으로 큐 관리; 죽은 ticket 복구 | 살아 있는 느린 compiler를 TTL만으로 만료 |
| 관찰 기억 | 검증된 원래-scope fact·현재 증명·최근 실패와 provenance 유지 | 마지막 몇 개 메시지 밖의 모든 사실 삭제 |

유료 P01/P10/P14 시행과 serial/parallel 동일 최종 소스의 후속 검증을 구분한다. 후속 병렬 검증은 validity·토큰이 같고 raw HB 차이가 −60/0/+13이었다. 단회 짝 관찰이므로 모든 환경에서 그 비율의 가속을 보장하지 않는다.

보수적인 UTF-8 byte 기반 입력 예약 때문에 실제 지출 한도가 남아도 다음 호출이 막히는 문제는 해결되지 않았다. v10도 세 문제 모두 40회 전에 중단됐다.

## 7. 실제 검색 도구와 외부 예제: v11

`experiments/theorem-retrieval-20261101/`는 기존 이름 AND 검색의 빈 결과 문제를 다룬다. preceding declaration의 완전한 signature와 외부 소스에 FTS5/BM25를 적용하고 name/signature/source 순위를 RRF로 합친다.

`experiments/retrieval-harness-20261101/`는 이를 v10에 연결한다.

- `retrieve`: 이름·선행 선언 signature 검색.
- `type_search`: 원래-scope compiler 타입의 상수·결론 head·선언 종류·binder 수 필터. **타입 unification 검색은 아니다.**
- `external`, `external_source`, `external_refs`: OpenAI math의 참고 증명·소스 줄·사용 가능 이름 힌트.

외부 index는 `openai/math` commit `4eaee87548250b2682affda7d05d947c05554bae`의 **162,417개 OAI 모듈**을 대상으로 한다. target stub은 제외한다. 실제 대상 환경의 이름·타입·적용 가능성 검증을 대체하지 않는다. lexical reference는 검증된 의존 그래프가 아니다.

외부 working tree를 줄였어도 Git object와 index SHA가 남으면 고정 commit의 `git show`로 필요한 파일만 복원한다. lazy fetch를 금지하고 원래 SHA가 맞아야 materialize한다. byte가 바뀐 기존 파일을 덮어쓰지 않는다.

P11 실제 유료 시행에서 `retrieve`·`type_search`는 각각 1회 사용됐지만 external source 호출은 없었다. 외부 예제 검색의 점수 효과는 이 실행으로 입증되지 않았다. 검색 도구 구현과 성능 입증을 분리한다.

## 8. 현재 후보군 경쟁과 구조 탐색

공통 피드백은 현재 champion 전체 소스, Length/HB frontier, 최근 유효 통계·실패 소스/진단, 고정 길이의 하한을 보여 준다. 상대 anchor는 표시값만 갱신하고 채택은 고정 목적식으로 한다.

독립 portfolio는 서로 격리된 scout 3개와 새 merger를 둔다. 40회 버전은 **6/6/6/22**이며, 18개 scout 평가 완료 전에 merger가 pool을 읽거나 평가할 수 없다. scout-a는 원본 proof를 숨기고 명제/타입에서 출발한다. 실패·수정도 credit을 쓴다.

이는 host와 지침에 의한 연구 입력 격리다. OS 수준 접근 차단으로 증명된 것은 아니다. 세 scout가 같은 큰 수학적 경로로 수렴한 P03처럼 독립 문맥이 구조적 다양성을 보장하지 않는다. backward·replace-block·distill·reencode는 모델 탐색 정책으로 시험했으며, AST 합성기나 전역 unification 엔진을 새로 구현한 것이 아니다.

후속 `competitive-structure-20261101`은 기존 best를 제공한 **incumbent-seeded continuation**이다. 독립 원본 출발 연구로 합산하거나, 새 구조를 전부 독립 재발견한 것으로 세지 않는다.

이 후속 연구는160회·유효120개·독립 final4개와 전체 오프라인 감사를 완료했다. [7가지 설계 인사이트](structural-insights.md)에 공개 분모와 경쟁 anchor의 분리, 문제별 교환비·손익분기점, API에 맞춘 중간 표현, 문맥 가정 비용, 비승리 구조 보존, 기존 구조 진단, 정체 시 재검색을 정리했다. 현재 packet에 이미 있는 Pareto·전체 이력·최근8개 통계·교환비와, 아직 일반 정책으로 구현하지 않은 구조 아카이브·자동 재검색은 구분한다.

## 9. 작은 머신의 빌드 재사용과 저장 정책

`experiments/cached-verification/worker.py`는 기존 고정 compiler/library를 등록하고, 매 후보를 원본 파일 한 곳에 교체한 전체 모듈로 새 프로세스에서 검사한다. 새 Mathlib 복사본 대신 이미 있는 빌드를 연결한다. `#print axioms`로 허용 공리도 확인하지만 이 worker 경로 자체는 HB/공식 점수를 계산하지 않는다.

P01/P02/P04/P05/P06 로컬 batch 검증 근거가 있다. 이것은 REPL 성공 결과 재사용이나 공식 비공개 평가 worker의 복제품이 아니다. 새 pin에 native plugin·module 옵션이 있으면 별도 준비·검사가 필요하다. P11 구버전 준비에서 Loom plugin과 메모리 한도 문제가 실제로 확인됐다.

완료한 P11 4.29/4.30 전용 환경·빌드는 정리했고, 고정 소스와 빌드 로그/config archive·재현 코드는 남겼다. 기본 P06 4.32/P11 4.31 캐시는 유지했다. 재현 가능성은 모든 build 산출물을 영구 보관한다는 뜻이 아니다.

## 10. 별도 커밋된 repair 연구

`origin/codex/verification-repair-*`의 설계·과거 실패 corpus 평가·bounded native recursive repair는 관련 있지만 다른 브랜치의 구현이다. main 미병합이며 이 문서가 합치지 않는다. v7의 장기 실패 기억이나 v9의 조회 기능 전체가 이미 그 브랜치에 편입됐다는 주장도 하지 않는다.
