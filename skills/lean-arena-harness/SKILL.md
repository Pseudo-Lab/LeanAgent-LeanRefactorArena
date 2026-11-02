---
name: lean-arena-harness
description: Prepare multi-source Lean Refactor Arena work from official JSONL, select bounded refactoring passes, and connect candidates to this repository's Lean verification tools. Use for dataset or source-group workflows; use lean-proof-shortening for an already prepared individual warm-up problem.
---

# Arena 데이터에서 증명 탐색·검증까지

저장소 루트에서 실행한다. 이 스킬은 실행 계획 생성기와 기존 `trial.py`·`golf.py`·`verify.py`를 연결하는 에이전트 절차다. 외부 플러그인 설치나 새 60문제 모델 실행기를 전제하지 않는다.

## 입력과 첫 실행

공식 JSONL 경로, 대상 출처, 출력 폴더를 확인한다. 출처를 생략하면 전체를 준비한다.

```sh
python3 skills/lean-arena-harness/scripts/plan.py \
  --benchmark /path/to/benchmark_data_final.jsonl \
  --output runs/manual/arena-plan/plan.json
```

담당 묶음만 준비하려면 `--source physlib --source cslib`처럼 반복한다. `--development /path/to/development.jsonl`을 추가하면 개발 자료와 전체 benchmark의 이름·정규화된 선언 중복을 검사한다. 개발 자료는 `name`, `source`, `statement`를 담는 JSONL이다.

생성기는 다운로드·Lean·모델 호출 없이 다음을 저장한다.

- 공식 정리 이름, 원본·명제 SHA, 원본 토큰 수, 문제별 비용 장부 키
- 출처·Lean 버전·전체 commit SHA로 구분한 환경 목록
- 문제별 지정 환경 조합: 최초 상태는 모두 `not_run`
- 입력 파일 SHA와 개발 자료 중복 검사 범위

문제·환경·검사 수는 입력에서 계산한다. 60·17·127을 코드에 고정하지 않는다. 기존 출력 파일은 덮어쓰지 않는다. 계획을 생성한 것과 검증에 통과한 것을 구분한다.

## 실행 절차

1. **환경과 시작 후보를 준비한다.** 공식 `version_info`를 실행 계획으로 고정한다. 실제 실행 환경과 원본 문맥 준비는 [기존 도구 연결](references/tools.md)을 따른다. 선택한 각 문제에 대해 등록된 환경이 그 문제의 공식 지정 목록을 전부 포함하는지 버전과 commit으로 비교한다. 출처를 필터링했다면 선택하지 않은 문제의 환경까지 준비할 필요는 없다. 과거 warm-up 패킷을 Final 환경으로 간주하지 않는다. 원본과 기존 후보를 같은 조건에서 확인하고 검증된 시작 후보를 고른다.
2. **현재 목표에서 편집을 고른다.** [수정 전략](references/passes.md)의 표에서 증명 구조와 현재 오류에 맞는 작은 시도를 선택한다. 먼저 고정 소스에서 관련 선언을 검색한다. 출처는 검색 문맥에 사용하고, 정리 이름·문제 번호로 저장된 답을 고르지 않는다. 한 후보에는 변경 의도와 수정 구간을 남긴다.
3. **편집하고 피드백을 읽는다.** 로컬 규칙은 기존 golf를, 직접 작성한 블록 변경은 trial을 사용한다. 실패하면 목표·가정·오류 위치·짧은 진단을 다음 시도에 전달한다. 환경 오류는 환경 준비로 돌리고, 같은 증명 오류를 그대로 반복하지 않는다. 지원되는 경우 MCP 또는 LeanInteract로 목표를 확인하되 파일 검사 경로도 유지한다.
4. **선택한 후보를 새로 검증한다.** 같은 증명을 공식 지정 버전마다 검사한다. 명제 바이트와 허용 문맥을 보존하고, 공통 평가기의 금지 구문·공리 검사를 사용한다. 한 버전 screening이나 외부 도구의 checkpoint를 최종 검증으로 승격하지 않는다.
5. **근거와 함께 선택한다.** 동일한 기준값·환경·호환성에서만 J로 비교한다. 호환성이 달라지면 토큰·HB·버전별 결과를 함께 보고 판단한다. 실패·미실행·환경 오류를 구분하고 호환성 100%는 모든 필수 버전이 통과한 경우에 표시한다. 개선이 없으면 검증된 시작 후보를 유지한다.

## 편집·비용 범위

- `:=` 뒤 허용된 증명 본문 안에서 수정한다. 외부 도구의 import 추가·새 전역 helper·선언 일반화·옵션 변경 절차는 가져오지 않는다. 생성자가 요구하는 가정과 문맥을 유지한다.
- 후보 채택은 대회 방식의 소스 토큰과 실제 HB·버전 결과로 결정한다. 줄 수·전술 이름·실행 대기시간만으로 성능을 판정하지 않는다.
- 모델 실행은 사용자가 요청한 범위와 예산을 따른다. Track 1의 모든 모델 호출 경로와 보조 호출 비용을 문제별 OpenRouter 장부에 모은다. 이전 실행 비용도 합산한다. 비용이 미확정이면 0으로 바꿔 추가 호출하지 않는다.
- main의 `cost_stop_usd`는 응답 후 종료 조건이다. 엄격한 US$3 사전 상한이나 중단 후 자동 재개를 제공한다고 간주하지 않는다. 유료 실행 연결 시 [기존 구현의 지원 범위](references/tools.md)를 확인한다.
- 버전 불일치 시 공식 toolchain을 외부 도구에 맞춰 올리지 않는다. 맞는 연결 방식이나 기존 파일 검사를 선택한다.

## 종료와 보고

실행 범위·남은 시간·비용 제한 또는 반복 실패를 근거로 종료한다. 원본/시작 후보/선택 후보의 SHA, 사용 전략, 버전별 결과, T·HB·기준값 출처, 비용 확정 여부와 채택 사유를 남긴다. 검증한 증명과 내보낸 증명의 SHA가 같아야 한다. 실행 계획만 만든 경우 측정과 모델 비용은 `미실행`으로 보고한다.

정책 비교나 성능 보고를 할 때는 [평가 구분](references/evaluation.md)을 읽는다. 참고한 상류 구현과 이번 스킬에 반영한 범위는 [도구·출처](references/tools.md)에 있다. 이 스킬을 읽는 것만으로 공식 제출·외부 게시·다른 PR 변경을 시작하지 않는다.

모델 비교가 필요한 경우 [비교 모델 목록](references/models.md)의 공식 링크·ID를 참고한다. 후보 목록으로 기본 모델을 자동 변경하지 않는다.
