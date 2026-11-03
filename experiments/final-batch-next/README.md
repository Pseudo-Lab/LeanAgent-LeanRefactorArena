# 다음 실행용 검증 결과 재사용·최종 버전 검사

선택적 Bank를 새 입력에 동결하려면 `prepare`/`inputs`에 `--strategy-bank PATH`,
`--strategy-contextual`, `--strategy-top-k 3`, `--strategy-search-policy alternating-v1`을 지정한다.
설정·추천·추적과 재사용 규칙은 [공통 Bank 문서](../../docs/strategy-bank.md)를 따른다.
기존 봉인 입력에는 정책을 덧씌우지 않는다.

평가 캐시와 최종 버전 검사를 사용하는 배치 실행기다.
현재 실행 중인 배치의 코드·입력·환경·ledger는 수정하지 않는다.
이전 `final-batch` 복사본과 source snapshot은 원본 커밋 `3ee67de`에 보존하고
새 브랜치에는 현재 실행기만 남겼다.

## 변경한 실행 방식

- 탐색 중 후보는 기본 Lean 버전에서 검사하고 1회 측정한다. 이 결과는
  해당 버전에서만 통과했다는 의미이며 전체 버전 통과로 표시하지 않는다.
- 같은 후보가 다시 나오면 `evaluation-cache/`의 버전별 결과를 재사용한다.
  후보 소스뿐 아니라 문제·전체 문맥, 환경 manifest, compiler, 실행 setup,
  평가 코드, OS/아키텍처, 측정 횟수와 reference 신뢰 정책이 같아야 한다.
- 정상 완료 결과와 결정적인 컴파일·공리 거절은 보존한다. 타임아웃,
  메모리·프로세스·환경 오류는 캐시하지 않는다. 캐시가 훼손되면 중단한다.
- 탐색 예산 소진 후 유효 후보를 점수순으로 확인한다. 이 단계에서 전체
  지정 버전을 검사하며, 기본 버전의 동일 조건 결과는 재사용한다.
  다른 버전에서 증명 오류가 나면 다음 후보를 확인한다. 환경·자원 실패는
  후보의 논리적 실패로 취급하지 않고 중단한다. 원본 후보도 fallback에 포함된다.
- 최종 선택한 증명은 기본 버전의 새 프로세스에서 3회 측정한다.
  이 최종 측정은 캐시를 사용하지 않는다. 기존 환경의 시작·종료 전체 해시
  검증, 원본 사전 검사, API 비용 정책과 동시 실행 제한은 유지한다.

최종까지 호환성 검사를 미루므로 탐색 도중 다른 버전의 오류 피드백은 받지 못한다.
기본 버전 최선 후보와 실제 최종 선택 후보가 다를 수 있다.

## 기본 scout→merger와 환율 정책

새 입력을 `prepare` 또는 `inputs`로 준비하면 기본으로 공통 하네스의
격리된 scout-a/b/c→merger와 `exchange-v1` 접근 정책을 사용한다.
`--portfolio`는 명시적 활성화 옵션으로 유지하며, `--no-portfolio`를 지정하면 기존 단일 문맥으로 준비한다.
기본 평가 수는 scout 각 6회, merger 22회이며 `--scout-evaluations`·`--merger-evaluations`로 지정한다.
모든 역할의 비용은 기존 문제별 $1 정산 후 중단 한도를 공유한다. 기존의 마지막 호출 초과 가능성은 같다.
할당량을 먼저 완료하면 $1 전에도 정상 종료한다. 예산이 먼저 끝나면 검증 best를 보존하고
`stopped`로 기록하며 완료 export에 포함하지 않는다. 보고서는 저장된 요청과 평가로 할당량을 재집계한다.

```sh
PYTHONPATH=src python3 -B experiments/final-batch-next/driver.py prepare --root runs/final-batch-next/NEW-PORTFOLIO --rows 31 --workers 1
```

이는 입력 준비 명령이다. `run`에서는 봉인된 설정을 읽으므로 정책 플래그를 다시 지정하지 않는다.
기존 준비 입력/실행의 정책은 바꾸지 않으며, 다른 정책에는 새 root가 필요하다.
이미 준비된 입력은 플래그 없이 재개하면 기존 정책을 그대로 유지한다. 이는 이전 단일 문맥 입력에도 적용된다.
명시적으로 다른 정책을 요청하면 새 root를 요구한다. 역할별 입력, 환율·단계 선택과
합성 출처는 [`docs/common-harness/README.md`](../../docs/common-harness/README.md)를 따른다.

한 문제 안의 scout 호출은 현재 순차 처리한다. 여러 문제는 `run --workers 2`로 진행하면
최대 두 API 호출을 겹칠 수 있으며, 실제 Lean 컴파일은 기존 전역 lock으로 하나씩 처리한다.
이는 FIFO 검증 큐나 한 문제 내부의 병렬 scout 실행을 추가한 변경은 아니다.
범용 `lean-agent run --config`는 사용자가 제공한 명시적 설정을 따르며 과거 config에 portfolio를 자동 삽입하지 않는다.

## 선택적 여러 라운드와 예산 기준 merger 종료

scout→merger(기본)와 함께 쓰는 opt-in 옵션이다. 옵션이 없으면 기존 scout 6×3 → merger 22와 같다. `--no-portfolio`와는 함께 쓸 수 없다.

- `--rounds N`: scout-a/b/c → merger를 N번 반복한다. 2라운드부터 scout는 직전까지의 최선 후보(seed)에서 시작하고,
  다른 scout의 후보는 여전히 볼 수 없다. 라운드별 평가 수는 `portfolio.completed_rounds`에 남는다.
- `--merger-until-budget`: 마지막 라운드의 merger가 평가 횟수 대신 문제별 비용 한도에 닿을 때까지 돈다.
  이때 merger 요청의 `remaining_evaluations`는 `null`, `stops_at`은 공유 예산이다. 모든 scout 할당을 채운 뒤
  예산으로 끝난 문제는 `stop_reason: portfolio_budget_complete`, `status: completed`로 기록하고 report 감사도 통과한다.
  이 단계에서는 다음 요청의 최악 비용(`request_cost`의 예약액)을 더했을 때 문제별 한도를 넘으면 그 요청을 보내지 않고 멈춘다.
  한도에 닿는 것이 일상이 되는 모드라, 마지막 호출이 한도를 넘는 일을 막기 위해서다(대회 규칙: 문제당 $3, 재시도 포함).
- 라운드 전환 규칙은 `portfolio.transition()` 하나로 실행기와 `report.py` 감사가 같이 쓴다.

배경: 평가 40회를 다 써도 문제당 약 $1.5만 쓰고 끝나는 문제가 있었다(ArkLib F039·F040). 같은 예산을 더 쓰는 방식과
scout·merger 배분을 바꾸는 방식을 비교하기 위한 옵션이다.

### 비교 조건(예시)

| 조건 | 옵션 | 평가 수 |
| --- | --- | --- |
| C0 기본 | (옵션 없음) | 6×3 + 22 = 40 |
| C1 넓은 scout | `--scout-evaluations 10 --merger-evaluations 10` | 10×3 + 10 = 40 |
| C2 두 라운드 | `--scout-evaluations 5 --merger-evaluations 5 --rounds 2` | (5×3 + 5)×2 = 40 |
| C3 예산까지 merger | `--merger-until-budget` | 18 + 예산까지 |
| C4 두 라운드 + 예산 | `--scout-evaluations 5 --merger-evaluations 5 --rounds 2 --merger-until-budget` | 35 + 예산까지 |

같은 문제 묶음에서 조건마다 새 root를 쓴다. 예: Strata F002·F006·F008(빠름), LeanPool F045·F048, ArkLib F039.

```sh
ROWS="2 6 8 45 48 39"
PYTHONPATH=src python3 -B experiments/final-batch-next/driver.py prepare --root runs/final-batch-next/AB-C2 --rows $ROWS --workers 1 \
  --scout-evaluations 5 --merger-evaluations 5 --rounds 2
PYTHONPATH=src python3 -B experiments/final-batch-next/driver.py run --root runs/final-batch-next/AB-C2 --rows $ROWS --workers 1 --ensure-preflight --key-file /ABSOLUTE/PATH/TO/.env
python3 experiments/final-batch-next/compare_conditions.py runs/final-batch-next/AB-C0 runs/final-batch-next/AB-C1 runs/final-batch-next/AB-C2 runs/final-batch-next/AB-C3 runs/final-batch-next/AB-C4
```

`compare_conditions.py`는 각 root의 summary로 문제별 점수·비용·평가 수와 공통 문제 평균을 보여 준다(Lean·API 없음).
조건당 한 번 실행은 실행 간 변동을 구분하지 못하므로, 가능하면 C0을 한 번 더 돌려 변동 폭과 함께 본다.
비용 한도는 실행기의 문제별 한도를 따른다.

## 증거와 재시작

캐시는 run root 내부에만 생성한다. 기존 실험의 결과를 가져오지 않는다.
항목은 완료 후 원자적으로 공개하고, 원본 소스·로그·결과의 SHA-256을 함께
보관한다. 재사용할 때는 증거를 새 평가 폴더로 복사하므로 기존 보고서 구조를
유지한다. `report.py`는 재사용 결과를 캐시 원본과 대조하고, 최종 측정이
캐시 결과인 경우 export를 거절한다.

환경별 `result.json`의 `cache.hit: true`는 이번에 compiler를 실행하지 않았다는
뜻이다. `runs[].seconds`와 command는 원래 실행의 역사적 증거이므로 새 실행
시간으로 합산하면 안 된다. 이번 hit의 실행 횟수·시간은 `cache`에 0으로 기록한다.
다른 단계나 재시작 후에도 동일 조건의 완료 결과는 재사용한다.
측정 횟수가 다르면 별도 항목이며, 최종 측정은 `fresh=True`로 우회한다.

## 다음 실행에서 사용

반드시 **새 run root**를 사용한다. 아래 `prepare`는 입력 준비만 수행한다.
`run`은 유료 API 호출을 시작한다. 이번 구현 작업에서는 어떤 배치도 시작하지 않았다.

```sh
PYTHONPATH=src .venv/bin/python -B experiments/final-batch-next/driver.py prepare --root runs/final-batch-next/NEW-RUN --rows 31 --workers 1
PYTHONPATH=src .venv/bin/python -B experiments/final-batch-next/driver.py run --root runs/final-batch-next/NEW-RUN --rows 31 --workers 1 --ensure-preflight --key-file /ABSOLUTE/PATH/TO/.env
PYTHONPATH=src .venv/bin/python -B experiments/final-batch-next/report.py --root runs/final-batch-next/NEW-RUN --require-complete --export
```

새 배치 authorization에는
`verification_policy: candidate-cache-final-compatibility-fast-inventory-v2`을 기록한다.
이 값이 없는 기존 배치에 새 runner를 적용하려 하면 파일 변경 전에 거절한다.
기존 배치를 이 정책으로 reseal하거나 자동 이관하지 않는다.

## 검증

```sh
PYTHONPATH=src .venv/bin/python -B -m unittest discover -s experiments/final-batch-next -p 'test_*.py'
```

회귀 테스트는 실제 API나 Lean compiler를 실행하지 않는다. 동일 후보 재사용,
다른 버전만 실행, 재시작, 실패 분류, 환경·후보·문맥·측정 조건 변경,
캐시 훼손, 증거 감사, 호환성 실패 시 차순위 선택, 최종 강제 재측정과
기존 배치 거절을 확인한다. 실제 Lean 환경 검사는 별도로 수행해야 한다.


## v2: 환경 확인 비용 절감

`stat-cache` 환경은 시작과 종료에 전체 바이트 해시를 검사하고, 중간에는
검증된 파일 목록의 stat과 디렉터리 변경 여부를 확인한다. 파일·구조 변경은
전체 검사 또는 오류로 이어진다. 디렉터리 symlink와 비정규 파일은 거절한다.
검증된 캐시 hit은 compiler lock을 기다리지 않는다. 실제 컴파일의 전역 직렬화,
최종 새 프로세스 3회 측정, scout→merger의 문맥 격리는 유지한다.
`full` 설정에는 중간 inventory 최적화를 적용하지 않는다.

캐시 schema와 verification policy가 v2로 바뀌므로 새 run root가 필요하다.
기존 실행을 reseal하거나 기존 v1 캐시를 옮기지 않는다.
이번 변경의 적용 범위는 이 배치 러너이며, 공통 `lean-agent` CLI의 기본 검증기는 아니다.
현재 실행 시간은 결과의 `timing`을 사용한다. 캐시의 `runs[].seconds`는 원래 실행 기록이다.

Mac에서 F018을 $1 한도로 단독 실행했을 때 준비·최종 검증 포함 11분 51초,
43회 호출에 $1.0018848이었다. 정산 후 중단 정책상 마지막 호출로 한도를 넘을 수 있다.
같은 후보 9개의 탐색 검증을 오프라인 재생한 비교는 271.10초에서 81.35초로
약 70% 단축되었다. 이는 탐색 검증 구간 비교이며 전체 실행 시간의 단축률은 아니다.
대회 60문제 전체나 다른 OS의 성능을 보장하는 수치는 아니다.

## 검색 반복 방지 핫픽스

새 입력의 기본 실행과 명시적인 `--portfolio`는 모두 `progress_guard: bounded-v1`를 저장한다.
4회 연속 미평가 호출 또는 반복 조회 후에는 후보 제출만 허용하며, 8회 연속 미평가 호출이나
역할당 `3 × 평가 할당량 + 8` 호출이면 그 역할을 미완료로 닫고 다음 역할로 진행한다.
평가 수는 실제 검증만으로 증가한다. 일부 역할이 할당량을 못 채웠다면 최종 상태는
`portfolio_stalled`/`stopped`이며, 감사는 기록된 호출과 평가 증거로 전환을 다시 계산한다.

이 변경은 기존 frozen 실행을 수정하거나 자동 재시도하지 않는다. 새 정책은 새 입력에서만 활성화한다.
오프라인 회귀는 검색 반복 차단·단계 진행·재현·감사 정합성을 검증하며, 실제 API에서의 점수 개선을 보장하지 않는다.
