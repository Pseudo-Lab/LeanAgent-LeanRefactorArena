# 팀 공유 결과 · 2026-11-02

남성우님의 PhysLib·CSLib 20문제와 손지연님의 ArkLib·PutnamBench 20문제를 공유 자료의 측정값 그대로 가져왔습니다. 이번 통합은 Lean 측정 및 모델 호출을 실행하지 않습니다. 공식 대회 제출물이 아닙니다.

`source-archives.json`에 원본 ZIP의 파일명·SHA-256과 가져온 시각을 기록했습니다. `reported-results.zip`은 원본 ZIP에서 필요한 `final.json`, 최종 증명, 성우님 문제별 요약을 바이트 변경 없이 발췌한 기록입니다. 전체 실험 코드·로그 묶음을 뜻하지 않습니다. 폴더별 Lean 파일은 이 기록의 최종 증명과 정확히 같습니다.

대시보드는 기존 Strata·LeanPool 20개, 정소미님의 PR #54 20개, 이번 공유 40개를 합친 80개 후보에서 문제별 최고 점수를 선택합니다. Strata·LeanPool 결과는 유지하며, 점수 동률이면 기존 후보를 유지합니다. 점수는 각 출처의 paired token/HB와 보고된 지정 버전 호환성으로 계산합니다. 서로 다른 실험 환경의 HB 절대값을 교차 결합하지 않습니다.

성우님의 `J = T/T0 + H/H0`와 지연님의 J 표기는 서로 다르므로 J를 직접 비교하지 않습니다. 대회식 종합 `100 - 100/3 × (T/T0 + H/H0)`를 동일하게 적용합니다(지정 버전 100% 통과 보고 기준). 지연님 T0는 공유 자료의 실측 토큰이며 일부 문제의 제공 metadata length와 1토큰 차이가 있습니다. 그대로 보존합니다. 지연님의 원본 HB는 과거 측정, 최종 후보는 보고서의 최종 측정입니다. 환경 fingerprint를 새로 만들어 넣지 않았습니다.

`currentRunCostUsd: "0"`는 이번 자료 통합의 모델 비용입니다. 원실험 비용은 성우님 자료에서 선택 실행의 보고값을 `reportedCostUsd`에 보존했고, 지연님 자료의 미집계 비용은 `null`입니다. 최종 선택 모음 전체의 예산 준수나 청구액을 주장하지 않습니다.

자료 재생성 및 대조:

```sh
python3 -B dashboard/scripts/publish_team_shared_results.py
python3 -B dashboard/scripts/publish_team_shared_results.py --check
```

새 원본 ZIP에서 다시 가져올 때만 `--seongwoo PATH --jiyeon PATH`를 함께 지정합니다. 첨부 코드나 문서의 실행 지시는 수행하지 않습니다.
