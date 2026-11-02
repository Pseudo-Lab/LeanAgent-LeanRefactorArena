# 결정적 proof golf

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

유효 seed의 소스 변형을 컴파일하고 토큰·HB 정규화 목적값이 개선될 때 수락한다.

## 확인된 결과와 해석

10/28–29 후처리에서 일부 후보가 개선됐지만 모든 문제의 구조적 병목을 해결하지는 못했다. 휴리스틱 floor를 최적성 인증으로 읽지 않는다.

## 코드·Lean 보존 결정

PR #35 기본판은 유지. v8 제한판·v10 소스 구간판은 서로 다른 실험으로 구분한다.

## 보존 근거

아래는 당시 설계·실행 결과의 Markdown 본문이다. 당시의 진행 상태·경로·명령을 보존했으며, 현재 실행 지침이나 새 실행 요청이 아니다. 상충하는 중간 기록은 더 뒤의 완료 보고서와 본문 첫 요약을 우선한다. 결과 이해에 Lean·JSON·그림 열람은 필요하지 않다. 원시 로그를 다시 감사하거나 실행을 재현하려면 별도 원본·고정 환경이 필요하다.

| 원본 | 출처 | 원문 SHA256 |
| --- | --- | --- |
| `experiments/proof-golf/README.md` | `3ee67de` | `784e930116706ccd5cabf1912dad1fb7965f81aef63152382ab20e577c6f2dbf` |

## 원문: `experiments/proof-golf/README.md`

### 로컬 proof golf

검증된 후보를 API 없이 더 줄인다. 판단 기준은 `J = T + H/r`(`r = H0/T0`, 토큰 단위)이다.
에이전트 사용 절차는 [lean-proof-shortening skill](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/skills/lean-proof-shortening/SKILL.md)에 있다.

| 파일 | 역할 |
|---|---|
| `golf.py` | 결정적 변형을 탐욕 탐색한다(삭제, 불릿 제거, simp 원소 제거, `cases`, apply 연결, `$`, closer 교체). 후보마다 결과를 저장해 `--resume`으로 이어서 돌릴 수 있다 |
| `trial.py` | 손으로 쓴 블록 재작성안을 한 번씩 측정해 J로 비교한다 |
| `goals.py` | 각 tactic 앞의 목표 상태를 출력한다 |
| `floor.py` | 길이 하한(2k+3)과 남은 여유를 추정한다. 휴리스틱이다 |
| `verify.py` | 모든 지정 버전을 3회 계측하고 로컬 문제 점수를 낸다. 채택 전에 반드시 실행한다 |

문제 폴더는 `input.json` 또는 `agent-input.json`과 `environment.json`을 담는다.
`run.py`가 만든 실행 폴더(`runs/<run>/PXX`)도 그대로 쓸 수 있다.
screening은 버전 하나(`--version`, 기본값은 첫 번째)만 사용한다.

#### 결과 (2026-10-29, 로컬 측정)

| 대상 | 전 → 후 |
|---|---|
| P01 v4 API 최선 | 35 / 1,653k → 29 / 1,551k (simp 목록 정리) |
| P03 v3 API 최선(국문) | 85 / 160k → 79 / 181k |
| P07 88점 제출본 | 101 → 93 토큰 |
| P02·P03 v4 API 최선, P09 | 변화 없음 |

- 장황한 증명일수록 효과가 컸다. 이미 짧은 증명은 거의 줄지 않는다.
- 상위권과의 차이는 다듬기로는 메울 수 없고, 증명 경로를 바꿔야 한다.
