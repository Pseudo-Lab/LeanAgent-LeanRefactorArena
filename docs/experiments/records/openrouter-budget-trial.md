# 예산 제한 API 실행기

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

원본에서 API 탐색을 수행하고 응답 영수증·미확정 비용·다중 버전 검증을 분리한다.

## 확인된 결과와 해석

10/28–29 종합 문서에 문제별 호출·실패·비용·후처리 결과를 기록했다. timeout은 무료 실패로 세지 않고 미확정 비용을 유지한다.

## 코드·Lean 보존 결정

기본판은 PR #35 반영. agentkit 워크트리의 api-runner 전환·진단 변경은 미커밋이므로 보존한다.

## 보존 근거

아래는 당시 설계·실행 결과의 Markdown 본문이다. 당시의 진행 상태·경로·명령을 보존했으며, 현재 실행 지침이나 새 실행 요청이 아니다. 상충하는 중간 기록은 더 뒤의 완료 보고서와 본문 첫 요약을 우선한다. 결과 이해에 Lean·JSON·그림 열람은 필요하지 않다. 원시 로그를 다시 감사하거나 실행을 재현하려면 별도 원본·고정 환경이 필요하다.

| 원본 | 출처 | 원문 SHA256 |
| --- | --- | --- |
| `experiments/openrouter-budget-trial/README.md` | `3ee67de` | `f1bd7cc223d6377cf6ce97a41c088de8985607efe086ccb88977310e0e570e54` |

## 원문: `experiments/openrouter-budget-trial/README.md`

### 예산 제한 API 실행기

원본 증명에서 출발해 모델 후보를 받고, Lean 검증 → 피드백 → 후보 선택을 반복한다.
에이전트 사용 절차는 [lean-proof-shortening skill](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/skills/lean-proof-shortening/SKILL.md)에 있다.

#### 동작

- 백엔드: `--backend openai`(Responses API, `src/lean_agent/openai_direct.py`) 또는 `openrouter`.
  모델 gpt-6.1-sol, reasoning high, 도구·플러그인 없음. proof 하나를 담은 JSON만 받는다.
- 단계:
  - `prepare`: 입력을 고정하고 `protocol.json`에 한도·프롬프트 해시를 기록한다.
  - `check`: 입력과 경로를 확인한다. API는 호출하지 않는다.
  - `run`: 유료 호출이 발생한다.
  - `stop`: 진행 중인 실행을 멈춘다.
- 예산:
  - `--budget-usd`는 문제당 한도, `--total-budget-usd`는 실행 전체 한도다.
  - 호출 전에 입력 크기와 최대 출력 단가로 비용을 미리 예약한다. provider 쪽 금액 잠금은 아니다.
  - 자동 재시도는 없다. 응답이 불확실하면(시간 초과 등) 그 뒤의 유료 호출을 모두 멈춘다.
- 모델 입력: 고정 문제·문맥, 현재 최선 후보, 직전 후보와 그 검증 피드백, 최근 후보 3개, HB 프로파일.
  history에는 각 시도의 수치만 남고 실패 이유는 남지 않는다. 개선이 필요한 부분이다.
- 키: `OPENAI_API_KEY` 환경 변수나 `--dotenv <file>`로 넘긴다. 키는 실행 기록이나 Git에 남기지 않는다.

#### 결과 (2026-10-29, 로컬 측정)

| 실행 | P01 | P02 | P03 |
|---|---|---|---|
| v3 프롬프트 (OpenRouter, 약 $0.87/문제) | 52 / 1,438k | 45 / 344k | — |
| v3 프롬프트 (OpenAI, P03, 국문/영문) | — | — | 85 / 160k, 85 / 210k |
| v4 프롬프트 (OpenAI, $1.5/문제) | 35 / 1,653k | 44 / 307k | 74 / 229k |

- 실패한 시도에 쓴 비용은 실행별로 26–45%였다. 원인은 skill 문서의 "알려진 실패 원인"에 정리했다.

#### 테스트

```bash
cd experiments/openrouter-budget-trial && python -m unittest test_budget test_openai_direct
```
네트워크와 Lean 없이 돈다. `fixtures/openrouter-endpoints.json`은 2026-10-29에 받은 공개 endpoint 가격 응답이다.
