# 검증·재현과 보관 범위

## 이 브랜치만으로 확인할 수 있는 것

- `evidence/git-audit.json`: main 기준 SHA, branch tip, 로컬 연구 파일 239개의 내용 비교와 과거 커밋 조회.
- `evidence/facts.json`: 기존 측정에서 뽑은 수치·완료 상태·제한.
- `evidence/proofs.json`, `evidence/proofs/*.lean`: 예제 14개의 정확한 소스·SHA와 검증 범위.
- `evidence/source-records.json`: 원래 arena 체크아웃에 보관된 근거 49개 파일의 주소·해시. 원시 API/Lean 실행 로그 전체를 포함하는 것은 아니다.

`tools/verify.py`는 위 JSON과 증명 해시, raw sample 중앙값, 기준 main의 파일·반영 여부, Markdown 링크를 오프라인으로 확인한다. Lean을 다시 컴파일하거나 유료 모델을 호출하지 않는다.

증명 예제는 측정 소스의 byte snapshot이다. 원본의 줄 끝 공백도 보존하며, 해당 폴더의 `.gitattributes`로 줄바꿈 정규화와 whitespace 교정을 막는다. 일반 구현 파일에 적용하는 예외는 아니며, 예제의 내용 일치는 별도의 SHA 검사로 강제한다.

```sh
source /Users/jwkweon/00_work/00_project/env/use.sh 05_pseudolab/LeanAgent-LeanRefactorArena
python3 -B docs/research/techniques-20261101/tools/verify.py
```

이번 문서의 검증을 과거 실행의 새 독립 Lean 측정으로 세지 않는다. 외부 환경이 삭제돼도 문서와 기존 수치의 일관성은 검사할 수 있지만, 원래 실험 재실행에는 아래 자원이 별도로 필요하다.

## 원래 로컬 파일에서 새 감사 snapshot 만들기

기존 파일을 덮어쓰지 않고 새 출력 경로를 사용한다. 코드나 아직 완료되지 않은 실행 상태가 바뀌었으면 새 날짜의 감사로 남긴다.

```sh
python3 -B docs/research/techniques-20261101/tools/audit_local.py \
  --source-root /path/to/arena-with-local-research \
  --ref 7f9508a85d44c5369f9461222f9904d6a9c01486 \
  --output /path/to/new-git-audit.json

python3 -B docs/research/techniques-20261101/tools/collect_evidence.py \
  --source-root /path/to/arena-with-local-research \
  --ref 7f9508a85d44c5369f9461222f9904d6a9c01486 \
  --output /path/to/new-curated-evidence
```

입력은 이번에 조사한 미커밋 구현·원래 `runs/`를 가진 체크아웃이며, 일반적인 새 clone에는 포함되지 않는다. `source-records.json`은 원본 파일을 재획득하는 아카이브 서비스가 아니다. collector는 기존 자료만 읽고, 빠진 실험 결과를 추측으로 채우지 않는다.

## 원래 실험을 실행하는 경우

다음은 원래 체크아웃의 경로이며, 이 문서 브랜치에 실험 구현 전체를 동봉했다는 뜻은 아니다.

| 대상 | 원래 진입점 | 필요한 자원과 주의점 |
| --- | --- | --- |
| P06/P11 수동 실험 | `experiments/oai-techniques-p06-p11-20261101/reproduce.py --output NEW --execute` | 새 출력 디렉터리. P06 4.32/P11 4.31 primary cache 재사용. P11 4.29/4.30은 고정 source/toolchain 복원·빌드 필요 |
| P01–P03 사후 코드 대조 | `experiments/structured-reasoning-analysis-20261031/verify.py` | 아카이브 검사는 무과금·컴파일 없음. 재측정은 새 실험 출력 경로 사용 |
| 경쟁형 12/40/fresh40 | 각 `experiments/competitive-*`의 `audit.py`/`report.py` | 감사·재집계는 새 후보 평가가 아니다. 새 탐색은 별도 input/ledger 필요 |
| v7–v11 | 각 실험 README와 전용 실행기 | 고정 compiler·source·runtime·native index 필요. `run`은 API 비용을 쓸 수 있으므로 문서 검사 용도로 실행하지 않음 |
| theorem retrieval | `experiments/theorem-retrieval-20261101/retrieval.py` | 고정 OpenAI math Git object·FTS DB·original-scope native index. 색인은 중앙 cache에서 재생성 |

현재 문서화 작업에서는 이를 새로 실행하지 않았다. 측정값·날짜·모델·reasoning·가격은 원래 실험 시점의 조건이며, 현재 API 사양을 확인한 결과가 아니다.

## 버전·header 검증 범위

| 예제 | 기존 근거에서 통과한 범위 | 주장하지 않는 것 |
| --- | --- | --- |
| 수동 P06 | 4.32.0, 원본 전체 module, 허용 공리, primary 3회 HB | 더 짧은 다른 모든 후보의 채택 |
| 수동 P11 | 같은 후보로 4.29.0/4.30.0/4.31.0, 원본 전체 module·공리. HB는 4.31에서 3회 | 368/240토큰 후보도 같은 버전 범위를 통과했다는 주장 |
| portfolio P01/P02 | supplied 4.26.0, 독립 final 3회 HB | 다른 compiler/context에 그대로 적용 가능하다는 주장 |
| portfolio P03 | supplied 4.26.0 | 4.27.0/4.29.1 |
| fresh/structural P13/P14/P15 | 축소된 supplied Mathlib 4.26.0, 독립 final 3회 HB | 전체 benchmark header, 추가 지정 버전, 공식 worker 점수 |
| retrieval P11 | 전체 primary 4.31.0, 독립 final 3회 HB | 4.29.0/4.30.0 |

## 디스크 정리 후 보존한 것

앞선 정리에서는 P11 4.29/4.30 전용의 재생성 가능한 환경·빌드를 제거하고 로그/config 803개를 archive에 보존했다. P06 4.32/P11 4.31의 primary library와 공유 download는 남겼다. 원래 증명·측정 근거 155파일의 byte hash도 확인했다.

이전 텍스트 실험 11,177파일은 APFS로 내용·경로를 바꾸지 않고 압축했고, 2파일은 원본 그대로 뒀다. 원래 정리 기록은 `runs/oai-techniques-p06-p11-20261101/storage-cleanup/report.json`이다. 이번 브랜치에 대형 라이브러리·원시 로그를 다시 추가하지 않는다.

## 통합 시 지킬 경계

1. main의 stat-cache·usage·기본 golf/API를 기반으로 한다. 오래된 로컬 파일 전체를 덮어쓰지 않는다.
2. 후보의 모든 지정 버전/header를 재검증하고 같은 정규화값으로 현재 채택 후보와 비교한다.
3. parser·query·LSP·회계·복구를 구현 단위로 옮기고 각 회귀 검증을 유지한다.
4. 검색·DAG·portfolio는 공통 입력·자원 조건에서 반복 비교가 필요하다. 유리했던 작은 단회 결과만을 채택 이유로 쓰지 않는다.

반영 상태는 snapshot이다. 이후 main이나 제출 후보가 갱신되면 같은 감사를 새 출력 경로에서 다시 수행한다.
