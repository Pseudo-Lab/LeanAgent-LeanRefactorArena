# 담당 20문제 라우팅 실험

`driver.py route20`은 F011–F030을 기존 팀 `FinalEvaluator`로 평가한다. 일반 실행은 동결된 원본 선언에서 시작한다. `--team-seeds`를 지정한 개발 실험은 PR #54와 #60의 팀 풀이도 대조군으로 읽는다. 각 풀이의 출처를 결과에 기록한다. 팀 풀이를 제공한 실행의 점수에는 그 풀이를 만든 사람의 성과가 포함된다.

## 실행

저장소 루트에서 실행한다. 준비된 final registry와 고정 Lean toolchain·라이브러리가 필요하다. `--prepared-repo`는 해당 환경을 가진 체크아웃을 지정한다.

```sh
PYTHONPATH=src python3 -B experiments/final-batch-next/driver.py route20 \
  --out runs/original20 --limit 2
PYTHONPATH=src python3 -B experiments/final-batch-next/driver.py route20 \
  --rows 24 27 --team-seeds solutions --out runs/compare24-27 --limit 2
```

결과 디렉터리는 실행마다 새로 지정한다. 전체 성공 시 `submission.jsonl`은 선택한 행의 `name`과 `proof`를 담는다. `report.json`은 행별 원본, 팀 대조군, 선택 후보와 가장 좋은 대조군 대비 추가 점수를 기록한다. 각 행의 `trials.json`과 Lean 로그에 실패·선별·최종 측정이 남는다.

## 선택 기준

1. 원본 선언의 단서를 20개 유형 설명과 대응시킨다. 유한 열거에는 입력 분해, 텐서 항등식에는 GaussianInt 사상, 형식 보존에는 반전과 명시적 반사성, 행렬에는 Schur 보조정리를 시도한다. 컴파일러가 대상 선언에서 불필요하다고 표시한 simp 인자도 제거 후보로 만든다.
2. 원본과 대조군은 동일 대표 버전에서 3회 측정한다. 다른 필수 버전에서도 각 1회 확인한다. 토큰 비율과 raw heartbeat 비율의 합이 작은 유효 후보부터 시작한다.
3. 새 후보는 대표 버전 1회로 선별한다. 점수가 올라가면 대표 버전 3회와 다른 필수 버전 검사를 거친다. 최종 점수가 더 높을 때만 교체하고 다음 변형의 출발점으로 사용한다. 환경 또는 자원 문제가 있으면 중단한다.
4. `--limit`는 문제당 새로운 결정적 변형의 최대 횟수다. 자료를 분석해 설계한 라우터이므로 이 20문제의 결과는 별도 홀드아웃에 대한 일반화 측정과 구분한다.

F023에서는 선택 전이의 증인을 직접 구성하거나 `And.imp_right`로 우측 함의만 증명한다. F028에서는 경계식을 `cumLen_succ`로 펼치고 자연수 뺄셈 정리로 닫는다. 대표 버전에서 컴파일된 후보를 다른 버전과 대조군 점수까지 확인한 뒤 선택한다.

`--policy portfolio --limit 4`는 현재 최고 풀이에서 파생한 편집, 목표와 선행 선언만 받은 독립 탐색, 다른 검증된 출발 풀이의 변형을 교대로 배정한다. 하나의 후보 한도와 동일한 채점기를 공유한다. 모든 버전 통과와 heartbeat 0을 가정해도 현재 최고 점수에 못 미치는 후보는 컴파일 전에 `score-pruned`로 기록한다. `route60 --rows $(seq 11 30)`으로 담당 문제만 골라 여러 라운드를 돌릴 수 있다.

`report.json`의 `assigned20_mean`은 F011–F030이 모두 검증됐을 때만 채워진다. 문제별 `selected.json`의 `metrics`에서 토큰 감소율, heartbeat 감소율, 버전 통과율을 확인할 수 있다. 셋의 평균이 해당 문제의 로컬 종합 점수다.

## 원본 재사용률에 따른 비교

팀 이슈 [#61](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/issues/61)의 진단을 시험하려면 같은 행·시작점·`--limit`에서 `--policy local`과 `--policy issue61`을 서로 다른 run root로 실행한다. 이슈의 단순 토크나이저로 길이 3 이상 일치 블록이 후보 본문에서 차지하는 비율을 기록한다. CSLib의 최선 대조군에서 이 비율이 0.95 이상이면 첫 후보 슬롯을 원본 본문을 보지 않는 scout에 배정한다. 입력은 statement와 그 앞의 Lean 선언 헤더뿐이다. 유료 모드를 명시했을 때 이 조건의 단일 모델 요청도 같은 입력을 사용한다. 양쪽 정책은 같은 횟수 상한과 점수 채택 기준을 사용한다. 재사용률을 점수로 쓰지 않으며 이슈의 상관관계는 실험 가설이다.

## 전체 60문제의 반복 실험

```sh
PYTHONPATH=src python3 -B experiments/final-batch-next/driver.py route60 --plan-only --out runs/inventory
PYTHONPATH=src python3 -B experiments/final-batch-next/driver.py route60 --team-seeds solutions \
  --rounds 2 --limit 4 --policy issue61 --out runs/team60
```

`coverage.json`에 문제별 필수 버전과 준비 누락 사유를 남긴다. 준비된 문제에서는 이전 라운드의 승자도 다시 검증하고 이미 시험한 후보의 해시는 제외한다. 한 라운드가 새 후보 한도를 채우지 못하면 그 문제의 탐색을 끝낸다. 검증 중 오류가 난 행은 `incomplete.json`에 남기며, 그 행의 예전 결과를 다시 내보내지 않는다. `route60`은 모델 호출이 없는 로컬 탐색이다. 60문제를 전부 통과한 경우에만 전체 평균과 `submission.jsonl`을 기록한다. 일부만 통과하면 `partial.jsonl`을 쓴다.

이미 검증한 20문제 선택 파일을 `--carry-jsonl PATH`로 전달하면 첫 라운드에 함께 재검증한다. 결과 보고서에는 팀 seed나 이전 풀이를 사용한 개발 실험임을 표시한다.

공통 Final 배치의 로컬 `report.py --export` 결과와 이 PR의 후보를 함께 비교하려면 `--carry-jsonl`을 두 번 지정한다. 동일한 문제의 두 증명은 각각 원본 선언과 모든 지정 버전에서 재검증한 뒤 같은 점수 기준으로 선택한다. 파일별 SHA256과 `previous-round`·`carry-02` 출처가 기록된다. 동일 파일 안의 중복 문제나 다른 선언은 거절한다. 이는 검증된 결과를 결합하는 별도 로컬 단계이며, 공통 scout의 입력을 자동으로 바꾸거나 공식 사이트에 제출하지 않는다. 기존 모델 사용액은 해당 원본 장부에서 별도로 확인해야 한다.

```sh
PYTHONPATH=src python3 -B experiments/final-batch-next/driver.py route60 \
  --rows 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 \
  --carry-jsonl runs/common-batch/submission.jsonl \
  --carry-jsonl experiments/assigned-route-results/verified-candidates.jsonl \
  --rounds 1 --limit 0 --out runs/compare-common-assigned
```

`experiments/assigned-route-results/verified-candidates.jsonl`은 F014–F015, F020, F023–F030의 팀 풀이 기반 개선 후보 11개를 담는다. 아래처럼 전달하면 해당 문제를 탐색할 때 기존 평가기로 먼저 다시 검증하고 대조군으로 사용한다. 나머지 문제는 원본과 선택한 팀 seed에서 시작한다. 이 파일은 개발용이며 공식 제출물이나 전체 20문제 결과가 아니다.

```sh
PYTHONPATH=src python3 -B experiments/final-batch-next/driver.py route60 \
  --rows 14 15 20 23 24 25 26 27 28 29 30 --team-seeds solutions \
  --carry-jsonl experiments/assigned-route-results/verified-candidates.jsonl \
  --policy portfolio --limit 4 --out runs/verified-seeds
```

## 유료 후보


기본 실행은 모델 호출이 없다. 유료 모드에서는 문제당 최대 1개의 OpenRouter 후보를 동일 평가기에 넣는다. `--ledger`에 모든 실행에서 공유하는 SQLite 경로, `--prior-spend`에 정확한 정리 이름별 선행 USD 지출 JSON을 함께 지정한다. `--key-file` 또는 `OPENROUTER_API_KEY` 환경 변수로 인증한다. 문제당 선행 비용과 다음 요청의 최악 비용 합이 $2.99를 넘으면 호출을 생략한다. 결제 정보를 확인하지 못한 문제는 장부 대조 전 추가 호출을 막는다. 같은 문제에 새 장부를 만들어 기존 지출을 제외하면 안 된다. 팀 풀이를 재사용한 출처의 비용은 별도로 입증해야 한다. [공식 대회 규칙](https://huggingface.co/spaces/delta-lab-ai/lean-refactor-arena/blob/main/app.py)

## 참고한 방법

- 같은 문제의 팀 후보는 [PR #60](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/pull/60)에서 가져왔다. [PR #62](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/pull/62)의 기존 최선 재검증과 [PR #49](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/pull/49)의 전체 문맥 재검증을 참고했다.
- 대회 참가용 저장소라고 명시한 aurasoph의 웜업 하네스에서는 원본과 후보를 같은 환경에서 짝지어 재는 방법을 참고했다. 그 팀의 해답이나 모델 가중치를 가져오지 않는다. [aurasoph의 실행 설명](https://github.com/aurasoph/lean-refactor/blob/7f3a401470d04f70013d293db4253b088ec8a0ae/competition/README.md)
- 길이와 비용을 함께 보고 버전을 확인하는 기준은 [Lean Refactor](https://arxiv.org/abs/2605.20244), 통과한 증명에서 다음 변형을 만드는 구조는 [ProofOptimizer](https://proceedings.iclr.cc/paper_files/paper/2026/hash/60917970c4257e50aff60d1d7bde2edf-Abstract-Conference.html), 컴파일러 피드백은 [ImProver](https://arxiv.org/abs/2410.04753)를 참고했다.
- Paperthin의 [modelchk](https://github.com/LilMGenius/paperthin/tree/main/skills/depth/modelchk)와 [mandela](https://github.com/LilMGenius/paperthin/tree/main/skills/depth/mandela)로 유료 실행 필요성과 평가의 독립성을 검토했다. 실행 전략 선택은 이 저장소의 코드가 한다.
