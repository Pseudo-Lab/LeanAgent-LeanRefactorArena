# Final 60문제 원본 Length·HB 측정

갱신: 2026-11-02T07:58:25.794011+00:00

원본 dataset SHA256: `d53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682`. 모델 API 호출 0회.

문제를 F001부터 순서대로 처리한다. 각 지정 버전에서 원문 컴파일·공리 확인 후 새 Lean 프로세스 1회로 HB를 측정한다. 이미 완료한 복수 표본은 실제 횟수와 중앙값을 그대로 보존한다. 버전별 결과를 따로 보존하고, 대표 HB는 dataset의 첫 번째 지정 버전 값을 사용한다. 공식 worker 점수는 아니다.

Length는 제공 기준값과 로컬 tokenizer 결과를 구분한다. raw HB와 환산 HB(raw // 1000)도 분리하며 미측정 값을 0으로 채우지 않는다.

완료: 10/60. 현재 상태: `blocked_environment`.

현재 사유: F011의 고정 문맥 준비 필요: physlib-v4.34.1, physlib-v4.34.0

| 문제 | 정리 | 제공 Length | 로컬 Length | 버전 | raw HB | 환산 HB | 실제 표본 수 |
| --- | --- | ---: | ---: | --- | ---: | ---: | ---: |
| F001 | `Core.InitsUpdatesComm` | 224 | 224 | strata-v4.31.0 | 4,182,543 | 4,182 | 3 |
| F001 | `Core.InitsUpdatesComm` | 224 | 224 | strata-v4.27.0 | 4,699,579 | 4,699 | 3 |
| F001 | `Core.InitsUpdatesComm` | 224 | 224 | strata-v4.26.0 | 4,683,842 | 4,683 | 3 |
| F002 | `Lambda.denote_suffix_irrel` | 904 | 904 | strata-v4.31.0 | 4,367,942 | 4,367 | 1 |
| F002 | `Lambda.denote_suffix_irrel` | 904 | 904 | strata-v4.27.0 | 4,816,051 | 4,816 | 1 |
| F003 | `Lambda.denote_Denotes` | 931 | 931 | strata-v4.31.0 | 10,925,062 | 10,925 | 1 |
| F003 | `Lambda.denote_Denotes` | 931 | 931 | strata-v4.27.0 | 12,476,761 | 12,476 | 1 |
| F004 | `Lambda.callOfLFunc_eraseMetadata_congr` | 291 | 291 | strata-v4.31.0 | 21,349,356 | 21,349 | 1 |
| F004 | `Lambda.callOfLFunc_eraseMetadata_congr` | 291 | 291 | strata-v4.27.0 | 63,449,865 | 63,449 | 1 |
| F005 | `Lambda.liftBVars_typeCheck` | 209 | 209 | strata-v4.31.0 | 17,630,192 | 17,630 | 1 |
| F005 | `Lambda.liftBVars_typeCheck` | 209 | 209 | strata-v4.27.0 | 23,917,585 | 23,917 | 1 |
| F006 | `Lambda.liftBVars_denote` | 972 | 972 | strata-v4.31.0 | 8,898,513 | 8,898 | 1 |
| F006 | `Lambda.liftBVars_denote` | 972 | 972 | strata-v4.27.0 | 11,988,265 | 11,988 | 1 |
| F007 | `Lambda.LExpr.typeCheck_to_HasTypeA` | 429 | 429 | strata-v4.31.0 | 7,093,908 | 7,093 | 1 |
| F007 | `Lambda.LExpr.typeCheck_to_HasTypeA` | 429 | 429 | strata-v4.27.0 | 9,080,928 | 9,080 | 1 |
| F008 | `Lambda.callOfLFunc_constr_disjoint_denote` | 968 | 968 | strata-v4.31.0 | 7,351,450 | 7,351 | 1 |
| F008 | `Lambda.callOfLFunc_constr_disjoint_denote` | 968 | 968 | strata-v4.27.0 | 7,718,944 | 7,718 | 1 |
| F009 | `Lambda.denote_replaceMetadata` | 938 | 938 | strata-v4.31.0 | 7,275,281 | 7,275 | 1 |
| F009 | `Lambda.denote_replaceMetadata` | 938 | 938 | strata-v4.27.0 | 8,309,077 | 8,309 | 1 |
| F010 | `Lambda.denote_ext` | 1200 | 1200 | strata-v4.31.0 | 4,667,076 | 4,667 | 1 |
| F010 | `Lambda.denote_ext` | 1200 | 1200 | strata-v4.27.0 | 5,257,943 | 5,257 | 1 |

원시 소스·컴파일 로그·측정 표본·결과 해시는 다음 로컬 실행 폴더에 보관한다.

`/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-expanded-20261102`

새 문제의 HB는 fresh 측정한다. 이전 완료 결과는 아래 원본 증거를 검증해 유지한다.

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-20261102/F001`
