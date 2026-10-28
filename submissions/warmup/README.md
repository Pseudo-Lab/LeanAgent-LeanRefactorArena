# Warm-up 첫 제출 준비 후보

`best/P01.lean`부터 `best/P15.lean`까지 담당자별 최종 후보를 모은다. 대시보드의 대표 후보와 파일 내용 및 SHA-256이 같다. 원본 LeanAgent 자료는 그대로 보존한다.

`best`는 담당자 최종본을 선택했다는 뜻이다. 후보 간 점수 최적화, 모든 지정 버전 통과, Track1 API 비용·생성 요건 충족을 뜻하지 않는다. 아직 공식 제출하지 않았다.

- `best/`: 제출 준비용 선언·증명. P12의 보조 증명은 대상 정리의 귀납 분기 안에 포함한다.
- `manifest.json`: 작성자, LeanAgent 원본 경로·커밋·해시, 후보 해시, 검증 상태·지정 버전.
- 공식 명제·헤더·소스 위치: manifest의 `benchmarkSnapshot`이 가리키는 기존 벤치마크 JSONL. 전체 문맥은 지정된 라이브러리 커밋에서 복원한다.

이 파일들은 고정된 문제 문맥에 넣는 후보이므로 모두 독립 실행 파일인 것은 아니다. P14·P15의 계측용 헤더·후행 명령은 후보에서 제외했으며 원본 LeanAgent 파일에서 확인할 수 있다. API 요청 형식은 API를 연결할 때 별도로 준비한다.

## 지정 환경 재검증

P01–P15의 환경은 `.github/workflows/warmup-verification.yml`의 **Verify pinned warmup environments**를 수동 실행해 복원한다. Strata v4.26.0/v4.27.0/v4.29.1, Physlib v4.32.0, Cslib v4.30.0/v4.31.0/v4.32.0/v4.33.0-rc2, ArkLib v4.28–v4.31 및 Mathlib v4.25–v4.27을 각각 별도 Linux runner에서 준비한다. 현재 작업은 총 15개다. `verification-inputs.json`은 위 benchmarkRevision에서 가져온 공식 명제·원본 증명·헤더와 버전별 소스 커밋을 고정한다. 이전 실행 [40301978929](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/actions/runs/40301978929)의 7개 summary는 P12를 포함한 당시 등록 6문제의 원본·후보가 지정 버전을 통과한 결과다. 15개 환경의 새 결과는 검증 후 아래 게시 절차로 반영해야 한다. 새 연결만으로 기존 대시보드의 측정값·통과 상태를 바꾸지는 않는다.

현재 P07 best는 SHA-256 `a5463ce0c227809919c02f9dee135565a88d06ff5a4f0aadaf1a45f5c9e4a07e`이며 Cslib 지정 환경 결과 게시 전까지 `pending`을 유지한다. 대표 측정 버전은 v4.32.0이다.

현재 P12 best는 SHA-256 `cad3a711ad849eff00de920e3ea7622ba8636e6f97651784969e35f0fe627bd2`인 새 수정 후보다. 보조 `have`를 귀납 분기에 통합하고 `Fin.snoc`으로 확률 분할을 정리했다. 공식 statement는 보존하며 후보 파일·manifest·대시보드 proof와 해시를 동기화했다. 새 후보는 ArkLib v4.29.0/v4.30.0/v4.31.0에서 Lean 검증·측정 전이므로 `pending`이며, 후보 측정값과 지정 버전 통과 상태를 비웠다.

이전 P12 후보 `cbc9d9819e788a9c7f1bfa917c17edfd7b31907a3b7c17b765b0a3eddff1abc4`의 Linux 지정 세 버전 통과 기록은 `verification-results.json`에 그대로 보존한다. 대표 v4.31.0의 원본 1,353토큰/9,199 HB → 후보 747토큰/3,501 HB는 그 이전 후보의 결과이며 새 후보에 적용하지 않는다. `measuredAt`은 기존 결과의 측정 시각을 유지하며 이번 후보 변경을 새 측정으로 기록하지 않는다.

`scripts/verify_warmup_pins.py`는 고정 커밋을 checkout하고, 해당 Lean 컴파일러를 설치하고 지정 의존성을 복원한다. Strata는 Mathlib·cache 실행기가 없어 `lake env lean --version`으로 Lake 의존성을 준비하고, 다른 소스는 공식 Mathlib 캐시를 복원한다. 의존성 커밋과 manifest 불변 여부를 대조한 뒤 필요한 모듈을 빌드한다. 원본이 통과한 환경에서만 후보를 PR3 평가기로 측정한다. 후보는 대시보드의 파일 해시와 대조하고, 선택 후보는 `best/` 파일과도 일치해야 한다. 세 번의 독립 실행 중앙값과 허용 공리 검사는 기존 평가기와 같다.

### Strata·Physlib 검증 연결

[이슈 #26](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/issues/26)에 따라 P01–P06도 같은 평가·artifact·게시 경로에 등록했다. 공식 입력은 기존 benchmark revision의 행을 그대로 복사했으며 후보 증명과 해시는 바꾸지 않았다.

| 소스 | 문제 | 지정 Lean 버전 | 대표 측정 버전 |
|---|---|---|---|
| Strata | P01·P02 | v4.26.0 | v4.26.0 |
| Strata | P03 | v4.26.0·v4.27.0·v4.29.1 | v4.26.0 |
| Physlib | P04·P05·P06 | v4.32.0 | v4.32.0 |

Strata v4.26.0은 `Strata.Transform.CallElimCorrect`와 `Strata.Languages.Core.StatementSemanticsProps`를 빌드한다. v4.27.0/v4.29.1에서는 P03만 평가하므로 후자만 빌드한다. Physlib는 `Physlib.Mathematics.VariationalCalculus.Basic`, `Physlib.Electromagnetism.Dynamics.IsExtrema`, `Physlib.QFT.PerturbationTheory.WickAlgebra.TimeOrder`를 빌드한다. 각 환경은 공식 입력에 기록된 정확한 소스 커밋과 그 manifest의 의존성을 사용한다.

워크플로는 계속 `workflow_dispatch` 수동 실행이다. PR 브랜치를 선택해 실행한 뒤 전체 15개 summary로 게시 스크립트를 실행한다. 실제 Linux 검증과 결과 게시·main 병합·운영 배포는 이번 연결 변경에 포함하지 않는다.

### Cslib P07–P09 검증 연결

P08·P09의 공식 입력도 고정 benchmark의 행을 그대로 등록했다. 후보 증명·해시·기존 게시 점수는 변경하지 않는다. Cslib 대표 측정 버전은 세 문제 모두 기존과 같은 v4.32.0이다.

| 문제 | 지정 Lean 버전 | 빌드 모듈 |
|---|---|---|
| P07 | v4.31.0·v4.32.0·v4.33.0-rc2 | `Cslib.Languages.LambdaCalculus.LocallyNameless.Fsub.Safety` |
| P08 | v4.30.0·v4.31.0·v4.32.0·v4.33.0-rc2 | `Cslib.Languages.CombinatoryLogic.Confluence` |
| P09 | v4.31.0·v4.32.0·v4.33.0-rc2 | `Cslib.Languages.CCS.BehaviouralTheory` |

v4.30.0에서는 P08 모듈만 빌드·평가하고, v4.31.0/v4.32.0/v4.33.0-rc2에서는 세 모듈을 빌드하여 P07–P09를 평가한다.

공식 입력은 이제 전체 15문제를 포함하며 워크플로 환경 수도 15개다. 새 결과 게시에는 모든 지정 문제의 결과가 들어 있는 15개 summary가 필요하다. P08·P09 등록 전의 Cslib summary에는 해당 결과가 없으므로 Cslib 네 환경을 다시 실행해야 한다. 게시기는 소스·버전뿐 아니라 문제 결과의 누락·중복도 검사한 뒤 갱신한다. P09의 기존 보충 실험 링크는 새 검증 근거와 함께 유지한다.

### Cardinality 표기 사전검사 수정

워크플로는 회귀 검사 전에 고정 평가기 커밋 `c18ec56682462847e2f4d8b6d60aa79ec071a10b`를 별도 checkout하고 Git 객체를 로컬 fetch로 가져온다. squash 병합 후에는 해당 커밋이 현재 브랜치의 조상이 아닐 수 있어 `fetch-depth: 0`만으로 복원되지 않는다. 비공개 저장소의 인증은 checkout 단계에서만 사용하며 의존성 빌드·증명 평가에 자격 증명을 남기지 않는다.

실행 `40278829841`에서 P12의 공식 원본에 있는 `#(filter …)`가 PR3 사전검사의 `#` 전체 금지에 걸렸다. 세 지정 버전 모두 원본 사전검사에서 중단되어 수정 후보는 평가하지 못했다. Actions 성공은 검증 시도와 artifact 저장의 완료이며 증명 통과를 뜻하지 않는다.

`scripts/warmup_evaluator.py`는 평가기 커밋 `c18ec56682462847e2f4d8b6d60aa79ec071a10b`를 복원하고 `tokens.py`의 `|#|` 한 곳만 `|#(?![({])|`로 바꾼다. 버전은 `lean-declaration-cardinality-v1`이며, 복원 전후 파일의 고정 SHA-256을 확인한다. 공백 없이 붙은 `#(`·`#{`만 허용하고, 내부·후행 코드의 금지 명령과 기존 금지 항목은 계속 검사한다. 공식 원본, 후보, 토큰 계산, Lean 실행·heartbeat 계측·공리 검사는 변경하지 않는다. 이 사전검사는 샌드박스가 아니며 문법·증명 유효성은 Lean 검증으로 확인한다.

summary에는 기준 커밋 `evaluatorRevision`, 패치 버전 `validatorVersion`, 실제 `tokens.py` 해시 `validatorSha256`을 기록한다. 게시기는 세 값이 현재 설정과 일치하는 summary만 받으며, 게시한 `verification-results.json`은 schemaVersion 2로 이 정보를 전체 및 실행별로 보존한다. 패치 정보가 없는 과거 summary는 새 결과와 섞어 게시할 수 없다. 현재 설정에서는 전체 15문제의 지정 결과를 포함한 15개 환경의 summary가 필요하다. 이전 7개·10개·14개 환경 실행은 새로 등록한 문제·버전의 결과가 없어 그대로 게시할 수 없다. 회귀 검사는 다음 명령으로 실행하며 warmup 워크플로에서도 의존성 설치 전에 수행한다. Lean 설치나 네트워크는 사용하지 않는다.

```sh
python3 -m unittest discover -s tests -p test_warmup_validator.py
```

### 검증 결과 반영

메모리 기본 한도는 6 GiB이며, 원본 실행에서 Lean 메모리 예외가 확인되면 준비된 환경에서 8 GiB로 한 번 재시도한다. 이 경우 후보도 같은 8 GiB 설정으로 측정하고 실제 명령을 fingerprint에 남긴다. 메모리 한도·시간 초과는 증명 오류와 구분한다.

완료된 작업의 `warmup-<source>-<version>` artifact에는 준비 로그, 실제 컴파일 명령·오류, 측정 결과와 환경 fingerprint가 들어 있다. 전체 15개 summary(Strata 3개·Physlib 1개·Cslib 4개·ArkLib 4개·PutnamBench 3개)를 내려받은 뒤 `python3 scripts/publish_warmup_verification.py <summary.json ...>`으로 반영한다. 이 스크립트는 모든 지정 버전과 후보 해시가 맞는지 확인한 뒤 대시보드와 manifest를 갱신한다. 등록된 문제의 지정 결과가 누락되면 해당 문제·소스·버전을 표시하고 게시 파일을 변경하지 않는다. 환경 구축 실패나 미완료 artifact로는 게시할 수 없다. 원본 실패와 후보 실패는 검증 결과에 구분해 남긴다.

`verification-results.json`에는 게시한 결과와 GitHub Actions 실행 ID를 보존한다. 상세 실험 로그는 작업 브랜치에 기록 후 삭제하며, main에는 후보·재현 스크립트·검증 요약만 유지한다. Actions artifact 보관 기간은 30일이며, 이후에도 작업 브랜치의 실험 기록 커밋 `8baf521`에서 `experiments/warmup-environment-repair/`의 상세 로그를 복구할 수 있다.

기존 웜업 수집 사본·보조 스크립트·원시 로그는 정리 요청에 따라 최종 트리에서 제거했다. 새 검증 결과를 게시하기 전에는 기존 대시보드 데이터를 유지하며, 게시 시에도 기존 근거 링크를 보존한다. 과거 로그는 삭제 전 커밋에서 확인한다. 후보를 변경하면 새로 검증한 뒤 best 파일·manifest 해시·대시보드 후보를 함께 갱신한다.


## 첫 업로드 파일과 남은 수정 범위 (2026-10-23)

업로드할 파일은 `submission.jsonl`이다. UTF-8 JSONL이며 각 줄에는 공식 benchmark의 `name`과 명제를 포함한 전체 Lean 선언인 `proof`만 들어 있다. `manifest.json`, `submission.audit.json`, 대시보드 JSON은 업로드 파일이 아니다.

저장된 `submission.jsonl` 묶음은 **14개 팀 best + P12 공식 원본**이다. 생성 당시 P12 팀 후보는 최상위 `private lemma` 세 개와 `omit` 문맥 변경을 포함하므로 그대로 넣지 않았다. 대신 고정 benchmark의 `src`를 그대로 사용했다. P12 원본의 공식 평가 통과나 점수는 아직 확인하지 않았으며, 해당 행을 팀 리팩터 성과로 취급하지 않는다. 이후 수정된 P12 후보는 이 파일에 아직 반영하지 않았다.

재생성:

```bash
python3 scripts/export_warmup_submission.py --p12-reference
```

로컬에 manifest의 `benchmarkSnapshot` 파일이 있어야 한다. 배포 저장소에는 benchmark 원본이 포함되지 않을 수 있으므로 `benchmarks/README.md`의 출처를 확인한다. `--p12-reference`는 대체 사용을 명시적으로 선택하는 옵션이다. 수정된 P12 후보는 이 옵션 없이 패키징할 수 있는 단일 선언 형태이며, 지정 환경 검증이 완료되면 이 옵션 없이 생성한다. 패키징 검사를 통과한 것만으로 Lean 검증 통과를 뜻하지 않는다.

검사 기록 `submission.audit.json`에는 제출 파일·각 proof의 SHA-256, 공식 규칙 revision, 선택 출처, 원본 대체 여부와 로컬 검증 상태가 있다. 생성기는 정확한 15개 이름·중복·manifest 해시·명제 보존·공식 업로드 금지 패턴·추가 선언을 검사한다. 이 검사는 Lean 컴파일이나 공식 평가를 대체하지 않는다.

| 우선순위 | 수정 범위 | 완료 조건 |
|---|---|---|
| P12 새 후보 검증 | 귀납 분기에 통합한 새 후보 `cad3a711`의 공식 statement·manifest·대시보드 해시 동기화 완료 | ArkLib v4.29/v4.30/v4.31에서 새 후보의 Lean 검증·측정 및 결과 게시 대기. 이전 `cbc9d981` 점수는 이월하지 않음 |
| P12 검증 연결 | 공식 P12 입력 및 `ArkLib.Data.CodingTheory.ProximityGap.DG25.MainResults` 빌드 타깃 연결 완료. 게시기는 등록 입력을 따라 P12도 처리함 | 이전 후보 `cbc9d981`의 실행 40301978929 기록 보존. 새 후보의 결과 게시와 `submission.jsonl` 재생성은 별도 진행 |
| P07 검증 연결 | 공식 P07 입력, Cslib 저장소와 `Cslib.Languages.LambdaCalculus.LocallyNameless.Fsub.Safety` 모듈 빌드, 지정 버전 3개 CI 및 게시 대표 버전 v4.32.0 연결 완료 | Linux 원격 검증 후 전체 15개 summary로 결과 게시 대기. 현재 측정값과 통과 상태는 변경하지 않음 |
| P01–P06 검증 연결 | 공식 입력·지정 커밋, Strata의 Mathlib 없는 준비 경로와 문제별 모듈 빌드, Physlib 세 모듈 및 4개 CI 작업 연결 완료 | Linux 원격 검증 후 전체 15개 summary로 결과 게시 대기. 기존 측정값·통과 상태 유지 |
| P08·P09 검증 연결 | 공식 입력, 문제별 Cslib 모듈 빌드와 P08 전용 v4.30.0 작업 연결 완료 | Cslib 네 환경을 다시 실행한 뒤 전체 15개 summary로 게시 대기. 기존 측정값·후보 해시·P09 보충 근거 유지 |
| 공식 점수 표시 | `dashboard/src/lib/model.ts`와 결과 데이터에 공식 결과 표시 경로 추가 | 로컬 실험 평균과 분리해 미제출·실패 0점 포함 15문제 평균, 공식 heartbeat 기준 및 worker 결과 사용 |
| 최종 참가 요건 | `docs/architecture.md`의 OpenRouter 실행·비용 장부·재현 하네스·보고서 계획 구현 | 문제당 $3에 재시도/폐기 후보 포함, 모델 공개, 재현 코드와 OpenReview 보고서 준비. 지금 업로드 가능하다는 사실을 비용 요건 면제로 해석하지 않음 |

공식 홈페이지는 증명 업로드와 코드 제출을 분리한다. 코드는 2026-11-01부터 접수하며 코드·보고서 마감은 2026-11-08이다. 첫 업로드 시 발급되는 submission key를 보관하고, 재제출은 기존 리더보드 결과를 교체하므로 전체 묶음을 사용한다. 이 작업에서는 실제 업로드를 수행하지 않았다.

규칙 확인 기준: [공식 app.py, 8fdaaaa](https://huggingface.co/spaces/delta-lab-ai/lean-refactor-arena/blob/8fdaaaa25b993ae8d894e9bb756c3ae222b58507/app.py), [공식 홈페이지](https://huggingface.co/spaces/delta-lab-ai/lean-refactor-arena).
