# 다음 실행용 검증 결과 재사용·최종 버전 검사

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

## 선택적 scout→merger와 환율 정책

새 입력을 준비할 때 `prepare` 또는 `inputs`에 `--portfolio`를 붙이면 공통 하네스의
격리된 scout-a/b/c→merger와 `exchange-v1` 접근 정책을 사용한다.
기본 평가 수는 scout 각 6회, merger 22회이며 `--scout-evaluations`·`--merger-evaluations`로 지정한다.
모든 역할의 비용은 기존 문제별 $1 정산 후 중단 한도를 공유한다. 기존의 마지막 호출 초과 가능성은 같다.
할당량을 먼저 완료하면 $1 전에도 정상 종료한다. 예산이 먼저 끝나면 검증 best를 보존하고
`stopped`로 기록하며 완료 export에 포함하지 않는다. 보고서는 저장된 요청과 평가로 할당량을 재집계한다.

```sh
PYTHONPATH=src python3 -B experiments/final-batch-next/driver.py prepare --root runs/final-batch-next/NEW-PORTFOLIO --rows 31 --workers 1 --portfolio
```

이는 입력 준비 명령이다. `run`에서는 봉인된 설정을 읽으므로 정책 플래그를 다시 지정하지 않는다.
기존 준비 입력/실행의 정책은 바꾸지 않으며, 다른 정책에는 새 root가 필요하다.
플래그가 없으면 기존 단일 문맥의 예산 기반 실행을 유지한다. 역할별 입력, 환율·단계 선택과
합성 출처는 [`docs/common-harness/README.md`](../../docs/common-harness/README.md)를 따른다.

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
`verification_policy: candidate-cache-final-compatibility-v1`을 기록한다.
이 값이 없는 기존 배치에 새 runner를 적용하려 하면 파일 변경 전에 거절한다.
기존 배치를 이 정책으로 reseal하거나 자동 이관하지 않는다.

## 검증

```sh
PYTHONPATH=src .venv/bin/python -B -m unittest discover -s experiments/final-batch-next -p 'test_*.py'
```

회귀 테스트는 실제 API나 Lean compiler를 실행하지 않는다. 동일 후보 재사용,
다른 버전만 실행, 재시작, 실패 분류, 환경·후보·문맥·측정 조건 변경,
캐시 훼손, 증거 감사, 호환성 실패 시 차순위 선택, 최종 강제 재측정과
기존 배치 거절을 확인한다. 실제 성능 향상 수치는 새 실험에서 측정해야 한다.
