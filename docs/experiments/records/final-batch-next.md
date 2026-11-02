# 공통 Final 배치 adapter

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

공통 actions·portfolio·예산 계약으로 배치 재시작·평가 캐시·최종 fresh 측정·export를 연결한다.

## 확인된 결과와 해석

PR #46 합성 회귀 검사에 포함된다. 이번 정리는 실제 모델 호출·새 Lean 컴파일·Final 성능 측정을 수행하지 않았다.

## 코드·Lean 보존 결정

현재 runtime 의존성이 있으므로 PR #46에 유지한다.

## 보존 근거

아래는 당시 설계·실행 결과의 Markdown 본문이다. 당시의 진행 상태·경로·명령을 보존했으며, 현재 실행 지침이나 새 실행 요청이 아니다. 상충하는 중간 기록은 더 뒤의 완료 보고서와 본문 첫 요약을 우선한다. 결과 이해에 Lean·JSON·그림 열람은 필요하지 않다. 원시 로그를 다시 감사하거나 실행을 재현하려면 별도 원본·고정 환경이 필요하다.

| 원본 | 출처 | 원문 SHA256 |
| --- | --- | --- |
| `experiments/final-batch-next/README.md` | `3ee67de` | `530d56290d0d13ce6c4c2e8d5d61da0c11a8250e212d277c598151ae06294655` |

## 원문: `experiments/final-batch-next/README.md`

### 다음 실행용 검증 결과 재사용·최종 버전 검사

기존 `experiments/final-batch/`를 복사해 별도 실행 경로로 만든 변경본이다.
현재 실행 중인 배치의 코드·입력·환경·ledger는 수정하지 않는다.
복사한 원본의 해시는 `source-snapshot.json`에 기록했다.

#### 변경한 실행 방식

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

#### 증거와 재시작

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

#### 다음 실행에서 사용

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

#### 검증

```sh
PYTHONPATH=src .venv/bin/python -B -m unittest discover -s experiments/final-batch-next -p 'test_*.py'
```

회귀 테스트는 실제 API나 Lean compiler를 실행하지 않는다. 동일 후보 재사용,
다른 버전만 실행, 재시작, 실패 분류, 환경·후보·문맥·측정 조건 변경,
캐시 훼손, 증거 감사, 호환성 실패 시 차순위 선택, 최종 강제 재측정과
기존 배치 거절을 확인한다. 실제 성능 향상 수치는 새 실험에서 측정해야 한다.
