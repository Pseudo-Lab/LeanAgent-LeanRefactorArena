# PR C: 고정 실패 후보 평가

[보고서](report.md), [실행 전 계획](PLAN.md), [입력 출처 조사](source-audit.json), [고정 후보](corpus.json)를 함께 읽는다.
이 평가는 API를 호출하지 않는다. 실제 Recursive Repair 모델 성능과 #37 생성 루프 성능은 미측정이다.

## 재현

Python 3.10 이상, 미리 설치된 Lean 4.26.0, 지정 revision의 Strata와 빌드된 import 모듈이 필요하다.
평가 명령은 의존성이나 toolchain을 자동 다운로드하지 않는다. 원본 source와 컴파일된 라이브러리의 해시를 확인한다.

원시 이력에서 입력을 다시 만들 때만 GitHub 읽기 권한이 있는 `gh`를 사용한다.
내려받은 파일은 실행 코드로 import하지 않고 JSON 데이터로 읽는다.

```sh
python3 experiments/verification-repair-policy/corpus_import.py fetch \
  --source-root runs/manual/week4-source
python3 experiments/verification-repair-policy/corpus_import.py freeze \
  --source-root runs/manual/week4-source \
  --output runs/manual/week4-corpus.json
```

Strata는 `451e5f047bafa010d178856db76c00029bfa4d7f`, plausible은 upstream `lake-manifest.json`에 지정된
`b949552f6ca8e223f424b3e3b33f74185bbf1179`를 사용한다. `lake update`로 핀을 갱신하지 않는다.
Strata checkout에서 다음 import 모듈을 빌드한다.

```sh
lake build Strata.DL.Imperative.CmdSemantics Strata.DL.Imperative.HasVars \
  Strata.DL.Imperative.StmtSemantics Strata.DL.Lambda.Lambda \
  Strata.DL.Util.ListUtils Strata.DL.Util.Nodup \
  Strata.Languages.Core.Env Strata.Languages.Core.Identifiers \
  Strata.Languages.Core.OldExpressions Strata.Languages.Core.Procedure \
  Strata.Languages.Core.Program Strata.Languages.Core.ProgramType \
  Strata.Languages.Core.Statement Strata.Languages.Core.StatementSemantics \
  Strata.Languages.Core.StatementSemanticsProps Strata.Languages.Core.WF \
  Strata.Transform.CallElim Strata.Transform.CoreTransform
```

저장소 루트에서 새 폴더로 평가를 준비하고 실행한다.

```sh
python3 experiments/verification-repair-policy/corpus.py prepare \
  --project /absolute/path/to/pinned/Strata \
  --lean /absolute/path/to/lean-4.26.0/bin/lean \
  --output runs/manual/repair-c-new
python3 experiments/verification-repair-policy/corpus.py run \
  --output runs/manual/repair-c-new
python3 experiments/verification-repair-policy/corpus.py replay \
  --output runs/manual/repair-c-new
```

기존 결과를 덮어쓰거나 중단된 실행을 재개하지 않는다. 입력과 코드가 바뀌면 새 실행 폴더를 사용한다.
replay는 저장된 관측으로 전이와 결과를 재계산한다. compiler나 모델을 호출하지 않고, 설치된 Strata도 필요하지 않는다.
현재 코드가 실행 당시 코드와 다르면 보존한 코드로 재생한다.

```sh
python3 runs/manual/repair-c-new/code/repo/experiments/verification-repair-policy/corpus.py \
  replay --output runs/manual/repair-c-new
```

완료된 실행에서 파생 표와 압축파일을 만들 때는 원시 실행 폴더 밖의 출력 경로를 사용한다.

```sh
python3 experiments/verification-repair-policy/corpus_report.py \
  --run runs/manual/repair-c-new \
  --output runs/manual/repair-c-new-export
```

## 결과 읽기

- `summary.json`: 중복 포함/제외 분모, 문제별 재현·복구·미확정 수. null은 0이 아니다.
- `rows.json`: 49개 사례의 간결한 파생 결과. 원본 유지의 선택 Q는 2로 표시하며 새 계측의 미세한 변동은 `final_measured_q`로 별도 보존한다.
- `protocol.json`, `validation.json`: 실행 revision, 입력·코드·환경 한도와 검증 근거.
- `evidence.tar.gz`: 보존 코드, 고정 입력, reference/case 결과, 결정 tape, 원시 compiler 입력·로그와 파일 해시. 압축파일 자체의 해시는 `validation.json`에 기록한다.

전체 49개 목록은 포함 범위를 뜻한다. 전부에 Auto Solver가 실행됐다는 뜻이 아니다.
원본 검증 실패, 현재 실패 미재현, 정책 거절, native 추출 불가, 수리 실패를 구분한다.
정상 원본의 full-file 검증 비용은 문제별 공유 준비 비용이고 후보별 검사·수리 비용과 따로 기록한다.
`no-repair`는 같은 후보를 수정하지 않고 당시 검증된 best를 유지하는 정적 기준이며, 독립 생성 루프 실행이 아니다.

고정 실패 이력의 재사용 평가다. 미관측 문제로의 일반화, 과거 프롬프트 조건의 인과 효과, API 비용 절감으로 해석하지 않는다.
