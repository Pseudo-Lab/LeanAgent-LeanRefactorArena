# 문제별 원본 입력 준비

[실험 목록](../README.md) · 정리 기준: 2026-11-02

## 목적과 방법

원본 증명·고정 문맥·tactic 사용 가능 범위를 에이전트 입력으로 준비한다.

## 확인된 결과와 해석

입력 준비는 최종 검증 성공과 별개다. agentkit의 P01–P05 입력 수정과 tactic probe는 미커밋으로 남아 있다.

## 코드·Lean 보존 결정

현재 사용 입력과 도구는 유지. 미반영 worktree를 제거하지 않는다.

## 보존 근거

아래는 당시 설계·실행 결과의 Markdown 본문이다. 당시의 진행 상태·경로·명령을 보존했으며, 현재 실행 지침이나 새 실행 요청이 아니다. 상충하는 중간 기록은 더 뒤의 완료 보고서와 본문 첫 요약을 우선한다. 결과 이해에 Lean·JSON·그림 열람은 필요하지 않다. 원시 로그를 다시 감사하거나 실행을 재현하려면 별도 원본·고정 환경이 필요하다.

| 원본 | 출처 | 원문 SHA256 |
| --- | --- | --- |
| `experiments/problem-inputs/README.md` | `3ee67de` | `a5a57df6ed10333b3fb9e3da3f5476fad51a92dc64b58284d12f1827c5a36f60` |

## 원문: `experiments/problem-inputs/README.md`

### 문제 입력 묶음

`PXX/agent-input.json`(문제, 문맥, 문제별 전략 문장)과 `PXX/original.lean`(원본 선언)은 기계와 무관하다.
문맥은 정리 직전까지의 관련 정의와 API 시그니처를 손으로 고른 것이다. 88점 제출본이나 이전 후보는 넣지 않았다.
P01–P03 묶음은 v4 실행에 쓴 입력이고, P04·P05 묶음은 프롬프트 실험에 쓴 입력이다.

`environment.json`은 Lean 경로가 들어가므로 커밋하지 않는다. `make_environment.py`로 각 기계에서 만든다.
만드는 방법은 [lean-proof-shortening skill](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/3ee67de1707d712321e403da5cf1d064dc4240f9/skills/lean-proof-shortening/SKILL.md)의 2절에 있다.
