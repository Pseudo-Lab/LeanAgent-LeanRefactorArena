# Final 60문제 원본 Length·HB 측정

갱신: 2026-11-02T10:47:26.564873+00:00

원본 dataset SHA256: `d53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682`. 모델 API 호출 0회.

문제를 F001부터 순서대로 처리한다. 각 지정 버전의 새 Lean 프로세스에서 원문 컴파일·공리 확인과 HB 1회 계측을 수행한다. 원본 단일 컴파일 모드는 protocol에 기록하며 이전의 별도 사전 컴파일 증거도 보존한다. 이미 완료한 복수 표본은 실제 횟수와 중앙값을 그대로 보존한다. 버전별 결과를 따로 보존하고, 대표 HB는 dataset의 첫 번째 지정 버전 값을 사용한다. 공식 worker 점수는 아니다.

Length는 제공 기준값과 로컬 tokenizer 결과를 구분한다. raw HB와 환산 HB(raw // 1000)도 분리하며 미측정 값을 0으로 채우지 않는다.

완료: 30/60. 현재 상태: `blocked_environment`. 환경 종료 검사: `passed`.

실행 중인 결과는 종료 시 전체 해시 검사가 끝날 때까지 잠정값이다. 문제 사이에는 stat-cache와 원본 소스 해시 검사를 유지한다.

현재 사유: F031의 고정 문맥 준비 필요: arklib-v4.34.0, arklib-v4.33.1, arklib-v4.31.0, arklib-v4.30.0

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
| F011 | `FTheory.SU5.ChargeSpectrum.containsPhenoCompletionsOfMinimallyAllows_viableCompletions` | 4 | 4 | physlib-v4.34.1 | 64,051,730 | 64,051 | 1 |
| F011 | `FTheory.SU5.ChargeSpectrum.containsPhenoCompletionsOfMinimallyAllows_viableCompletions` | 4 | 4 | physlib-v4.34.0 | 64,051,730 | 64,051 | 1 |
| F012 | `FTheory.SU5.ChargeSpectrum.isPhenoClosedQ5_viableCharges` | 12 | 12 | physlib-v4.34.1 | 74,041,515 | 74,041 | 1 |
| F012 | `FTheory.SU5.ChargeSpectrum.isPhenoClosedQ5_viableCharges` | 12 | 12 | physlib-v4.34.0 | 74,041,515 | 74,041 | 1 |
| F013 | `FTheory.SU5.ChargeSpectrum.isPhenoClosedQ10_viableCharges` | 12 | 12 | physlib-v4.34.1 | 79,108,905 | 79,108 | 1 |
| F013 | `FTheory.SU5.ChargeSpectrum.isPhenoClosedQ10_viableCharges` | 12 | 12 | physlib-v4.34.0 | 79,108,905 | 79,108 | 1 |
| F014 | `PauliMatrix.pauliContrDown_mul_pauliContr_mul_pauliContrDown` | 181 | 181 | physlib-v4.34.1 | 212,379,390 | 212,379 | 1 |
| F014 | `PauliMatrix.pauliContrDown_mul_pauliContr_mul_pauliContrDown` | 181 | 181 | physlib-v4.34.0 | 212,379,390 | 212,379 | 1 |
| F015 | `PauliMatrix.pauliContr_mul_pauliContrDown_mul_pauliContr` | 183 | 183 | physlib-v4.34.1 | 136,539,444 | 136,539 | 1 |
| F015 | `PauliMatrix.pauliContr_mul_pauliContrDown_mul_pauliContr` | 183 | 183 | physlib-v4.34.0 | 136,539,444 | 136,539 | 1 |
| F016 | `Electromagnetism.ElectromagneticPotential.time_deriv_time_deriv_electricField_of_isExtrema` | 1372 | 1372 | physlib-v4.34.1 | 23,941,357 | 23,941 | 1 |
| F016 | `Electromagnetism.ElectromagneticPotential.time_deriv_time_deriv_electricField_of_isExtrema` | 1372 | 1372 | physlib-v4.34.0 | 23,941,357 | 23,941 | 1 |
| F017 | `FieldSpecification.WickAlgebra.ι_timeOrderF_superCommuteF_eq_time` | 1217 | 1217 | physlib-v4.34.1 | 35,774,573 | 35,774 | 1 |
| F017 | `FieldSpecification.WickAlgebra.ι_timeOrderF_superCommuteF_eq_time` | 1217 | 1217 | physlib-v4.34.0 | 35,774,569 | 35,774 | 1 |
| F018 | `fundamental_theorem_of_variational_calculus'` | 851 | 851 | physlib-v4.34.1 | 10,202,611 | 10,202 | 1 |
| F018 | `fundamental_theorem_of_variational_calculus'` | 851 | 851 | physlib-v4.34.0 | 10,202,612 | 10,202 | 1 |
| F019 | `HermitianMat.inv_convex` | 1025 | 1025 | physlib-v4.34.1 | 211,678,390 | 211,678 | 1 |
| F019 | `HermitianMat.inv_convex` | 1025 | 1025 | physlib-v4.34.0 | 211,678,433 | 211,678 | 1 |
| F020 | `cauchyBinet` | 1200 | 1200 | physlib-v4.34.1 | 143,389,537 | 143,389 | 1 |
| F020 | `cauchyBinet` | 1200 | 1200 | physlib-v4.34.0 | 143,389,673 | 143,389 | 1 |
| F021 | `Cslib.LambdaCalculus.LocallyNameless.Fsub.Typing.progress` | 408 | 408 | cslib-v4.34.1 | 59,936,725 | 59,936 | 1 |
| F021 | `Cslib.LambdaCalculus.LocallyNameless.Fsub.Typing.progress` | 408 | 408 | cslib-v4.33.1 | 60,093,800 | 60,093 | 1 |
| F022 | `Cslib.SKI.parallelReduction_diamond` | 407 | 407 | cslib-v4.34.1 | 1,500,541 | 1,500 | 1 |
| F022 | `Cslib.SKI.parallelReduction_diamond` | 407 | 407 | cslib-v4.33.1 | 1,499,947 | 1,499 | 1 |
| F023 | `Cslib.CCS.bisimilarity_congr_choice` | 251 | 251 | cslib-v4.34.1 | 3,940,867 | 3,940 | 1 |
| F023 | `Cslib.CCS.bisimilarity_congr_choice` | 251 | 251 | cslib-v4.33.1 | 3,923,913 | 3,923 | 1 |
| F023 | `Cslib.CCS.bisimilarity_congr_choice` | 251 | 251 | cslib-v4.31.0 | 3,927,323 | 3,927 | 1 |
| F024 | `Cslib.LambdaCalculus.LocallyNameless.Fsub.Typing.preservation` | 391 | 391 | cslib-v4.34.1 | 38,100,120 | 38,100 | 1 |
| F024 | `Cslib.LambdaCalculus.LocallyNameless.Fsub.Typing.preservation` | 391 | 391 | cslib-v4.33.1 | 38,313,227 | 38,313 | 1 |
| F025 | `Cslib.FLP.PseudoConsensus.of_consensus` | 433 | 433 | cslib-v4.34.1 | 11,623,232 | 11,623 | 1 |
| F025 | `Cslib.FLP.PseudoConsensus.of_consensus` | 433 | 433 | cslib-v4.33.1 | 12,051,112 | 12,051 | 1 |
| F026 | `Cslib.Automata.NA.Buchi.buchiFamily_saturation` | 623 | 623 | cslib-v4.33.1 | 56,935,331 | 56,935 | 1 |
| F026 | `Cslib.Automata.NA.Buchi.buchiFamily_saturation` | 623 | 623 | cslib-v4.31.0 | 77,902,172 | 77,902 | 1 |
| F027 | `Cslib.FLP.OnePseudoConsensus.nonUniform_step` | 368 | 368 | cslib-v4.34.1 | 39,339,312 | 39,339 | 1 |
| F027 | `Cslib.FLP.OnePseudoConsensus.nonUniform_step` | 368 | 368 | cslib-v4.33.1 | 37,257,043 | 37,257 | 1 |
| F028 | `Cslib.LTS.OmegaExecution.flatten_execution` | 312 | 312 | cslib-v4.33.1 | 27,607,488 | 27,607 | 1 |
| F028 | `Cslib.LTS.OmegaExecution.flatten_execution` | 312 | 312 | cslib-v4.31.0 | 32,182,165 | 32,182 | 1 |
| F028 | `Cslib.LTS.OmegaExecution.flatten_execution` | 312 | 312 | cslib-v4.30.0 | 35,212,723 | 35,212 | 1 |
| F029 | `Cslib.FLP.CanReachVia.subset_inp` | 364 | 364 | cslib-v4.34.1 | 33,199,270 | 33,199 | 1 |
| F029 | `Cslib.FLP.CanReachVia.subset_inp` | 364 | 364 | cslib-v4.33.1 | 29,186,712 | 29,186 | 1 |
| F030 | `Cslib.LambdaCalculus.LocallyNameless.Untyped.Term.parallel_diamond` | 519 | 519 | cslib-v4.34.1 | 8,589,142 | 8,589 | 1 |
| F030 | `Cslib.LambdaCalculus.LocallyNameless.Untyped.Term.parallel_diamond` | 519 | 519 | cslib-v4.33.1 | 8,709,469 | 8,709 | 1 |

원시 소스·컴파일 로그·측정 표본·결과 해시는 다음 로컬 실행 폴더에 보관한다.

`/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-cslib-final-20261102`

동일 입력·환경·평가기의 검증된 캐시가 있으면 원래 표본을 재사용한다. 그 밖의 HB는 새로 측정한다. 재사용한 결과의 cache 필드는 원래 증거 경로와 새 compiler 실행 0회를 기록한다.

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-20261102/F001`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-cached-20261102/F011`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-cached-20261102/F012`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-cached-20261102/F013`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-cached-20261102/F014`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-cached-20261102/F015`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-cached-20261102/F016`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-cached-20261102/F017`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-cached-20261102/F018`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-cached-20261102/F019`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-cached-20261102/F020`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-cslib-20261102/F021`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-cslib-20261102/F022`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-cslib-hygiene-20261102/F023`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-cslib-hygiene-20261102/F024`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-cslib-hygiene-20261102/F025`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-cslib-hygiene-20261102/F026`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-cslib-hygiene-20261102/F027`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-expanded-20261102/F002`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-expanded-20261102/F003`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-expanded-20261102/F004`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-expanded-20261102/F005`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-expanded-20261102/F006`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-expanded-20261102/F007`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-expanded-20261102/F008`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-expanded-20261102/F009`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-expanded-20261102/F010`
