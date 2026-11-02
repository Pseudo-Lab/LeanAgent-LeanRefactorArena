# Final 60문제 원본 Length·HB 측정

갱신: 2026-11-02T15:14:11.115060+00:00

원본 dataset SHA256: `d53690b057f9972f44643678ee6b5eee7a66f56e1a7d2678a2e5ff47fadbd682`. 모델 API 호출 0회.

문제를 F001부터 순서대로 처리한다. 각 지정 버전의 새 Lean 프로세스에서 원문 컴파일·공리 확인과 HB 1회 계측을 수행한다. 원본 단일 컴파일 모드는 protocol에 기록하며 이전의 별도 사전 컴파일 증거도 보존한다. 이미 완료한 복수 표본은 실제 횟수와 중앙값을 그대로 보존한다. 버전별 결과를 따로 보존하고, 대표 HB는 dataset의 첫 번째 지정 버전 값을 사용한다. 공식 worker 점수는 아니다.

Length는 제공 기준값과 로컬 tokenizer 결과를 구분한다. raw HB와 환산 HB(raw // 1000)도 분리하며 미측정 값을 0으로 채우지 않는다.

완료: 60/60. 현재 상태: `complete`. 환경 종료 검사: `passed`.

실행 중인 결과는 종료 시 전체 해시 검사가 끝날 때까지 잠정값이다. 문제 사이에는 stat-cache와 원본 소스 해시 검사를 유지한다.

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
| F031 | `interleaved_affine_gaps_imply_tensor_gaps` | 1353 | 1353 | arklib-v4.34.0 | 7,774,574 | 7,774 | 1 |
| F031 | `interleaved_affine_gaps_imply_tensor_gaps` | 1353 | 1353 | arklib-v4.33.1 | 7,829,037 | 7,829 | 1 |
| F031 | `interleaved_affine_gaps_imply_tensor_gaps` | 1353 | 1353 | arklib-v4.31.0 | 10,226,033 | 10,226 | 1 |
| F031 | `interleaved_affine_gaps_imply_tensor_gaps` | 1353 | 1353 | arklib-v4.30.0 | 10,227,365 | 10,227 | 1 |
| F032 | `Binius.BinaryBasefold.fold_advances_evaluation_poly` | 1906 | 1906 | arklib-v4.31.0 | 47,701,818 | 47,701 | 1 |
| F032 | `Binius.BinaryBasefold.fold_advances_evaluation_poly` | 1906 | 1906 | arklib-v4.30.0 | 49,156,465 | 49,156 | 1 |
| F033 | `Binius.BinaryBasefold.fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius` | 1463 | 1463 | arklib-v4.31.0 | 16,839,602 | 16,839 | 1 |
| F033 | `Binius.BinaryBasefold.fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius` | 1463 | 1463 | arklib-v4.30.0 | 18,274,665 | 18,274 | 1 |
| F034 | `Combine.master_lemma` | 546 | 546 | arklib-v4.33.1 | 190,043,613 | 190,043 | 1 |
| F034 | `Combine.master_lemma` | 546 | 546 | arklib-v4.31.0 | 282,353,782 | 282,353 | 1 |
| F034 | `Combine.master_lemma` | 546 | 546 | arklib-v4.30.0 | 310,005,663 | 310,005 | 1 |
| F035 | `JohnsonBound.johnson_bound_alphabet_free` | 2440 | 2440 | arklib-v4.31.0 | 84,743,834 | 84,743 | 1 |
| F035 | `JohnsonBound.johnson_bound_alphabet_free` | 2440 | 2440 | arklib-v4.30.0 | 95,208,808 | 95,208 | 1 |
| F036 | `ProximityToRS.dir_close_of_many_close_pts` | 5128 | 5128 | arklib-v4.31.0 | 106,464,364 | 106,464 | 1 |
| F036 | `ProximityToRS.dir_close_of_many_close_pts` | 5128 | 5128 | arklib-v4.30.0 | 106,965,202 | 106,965 | 1 |
| F037 | `ProximityGap.RS_exists_nonzero_kernelVec_of_det_eq_zero_natDegree_le_one` | 2122 | 2122 | arklib-v4.31.0 | 163,948,549 | 163,948 | 1 |
| F037 | `ProximityGap.RS_exists_nonzero_kernelVec_of_det_eq_zero_natDegree_le_one` | 2122 | 2122 | arklib-v4.30.0 | 167,280,056 | 167,280 | 1 |
| F038 | `ProximityGap.RS_jointAgreement_of_goodCoeffs_card_gt` | 5538 | 5538 | arklib-v4.31.0 | 62,515,166 | 62,515 | 1 |
| F038 | `ProximityGap.RS_jointAgreement_of_goodCoeffs_card_gt` | 5538 | 5538 | arklib-v4.30.0 | 70,404,926 | 70,404 | 1 |
| F039 | `Sumcheck.Spec.SingleRound.Simple.reduction_perfectCompleteness` | 1426 | 1426 | arklib-v4.31.0 | 44,522,173 | 44,522 | 1 |
| F039 | `Sumcheck.Spec.SingleRound.Simple.reduction_perfectCompleteness` | 1426 | 1426 | arklib-v4.30.0 | 45,724,728 | 45,724 | 1 |
| F040 | `ps_coprime_case_constant` | 1105 | 1105 | arklib-v4.34.0 | 38,031,288 | 38,031 | 1 |
| F040 | `ps_coprime_case_constant` | 1105 | 1105 | arklib-v4.33.1 | 40,063,756 | 40,063 | 1 |
| F040 | `ps_coprime_case_constant` | 1105 | 1105 | arklib-v4.31.0 | 44,381,008 | 44,381 | 1 |
| F040 | `ps_coprime_case_constant` | 1105 | 1105 | arklib-v4.30.0 | 46,665,599 | 46,665 | 1 |
| F041 | `LeanPool.Erdos132ConvexK3.erlv_case12_other_d1_bone_impossible` | 2030 | 2030 | leanpool-v4.35.0-rc3 | 49,681,455 | 49,681 | 1 |
| F041 | `LeanPool.Erdos132ConvexK3.erlv_case12_other_d1_bone_impossible` | 2030 | 2030 | leanpool-v4.34.0 | 54,162,272 | 54,162 | 1 |
| F042 | `CoxeterSystem.matsumoto_reduced_aux` | 1699 | 1699 | leanpool-v4.35.0-rc3 | 3,091,286 | 3,091 | 1 |
| F042 | `CoxeterSystem.matsumoto_reduced_aux` | 1699 | 1699 | leanpool-v4.34.0 | 3,247,359 | 3,247 | 1 |
| F043 | `Vlasov.transportedIntegral_continuousOn` | 2413 | 2413 | leanpool-v4.35.0-rc3 | 9,943,703 | 9,943 | 1 |
| F043 | `Vlasov.transportedIntegral_continuousOn` | 2413 | 2413 | leanpool-v4.34.0 | 10,672,287 | 10,672 | 1 |
| F044 | `ZetaZeros.step1_double` | 2315 | 2315 | leanpool-v4.35.0-rc3 | 13,000,252 | 13,000 | 1 |
| F044 | `ZetaZeros.step1_double` | 2315 | 2315 | leanpool-v4.34.0 | 13,790,729 | 13,790 | 1 |
| F045 | `LocalComplexGeometry.holomorphic_constant_rank` | 1756 | 1756 | leanpool-v4.35.0-rc3 | 53,089,873 | 53,089 | 1 |
| F045 | `LocalComplexGeometry.holomorphic_constant_rank` | 1756 | 1756 | leanpool-v4.34.0 | 53,805,764 | 53,805 | 1 |
| F046 | `LeanEval.Topology.ClassificationOfSurfaces.Moise.PartialTriangulation.exists_chartMatchingControlOn_of_metricSpace` | 1645 | 1645 | leanpool-v4.35.0-rc3 | 11,484,649 | 11,484 | 1 |
| F046 | `LeanEval.Topology.ClassificationOfSurfaces.Moise.PartialTriangulation.exists_chartMatchingControlOn_of_metricSpace` | 1645 | 1645 | leanpool-v4.34.0 | 11,865,100 | 11,865 | 1 |
| F047 | `LeanEval.Topology.ClassificationOfSurfaces.Moise.PolygonalCircle.insertZero_nonadjacent_disjoint` | 1509 | 1509 | leanpool-v4.35.0-rc3 | 6,122,522 | 6,122 | 1 |
| F047 | `LeanEval.Topology.ClassificationOfSurfaces.Moise.PolygonalCircle.insertZero_nonadjacent_disjoint` | 1509 | 1509 | leanpool-v4.34.0 | 6,380,698 | 6,380 | 1 |
| F048 | `IsoGraph.Canon.dfsNode_dom` | 2879 | 2879 | leanpool-v4.35.0-rc3 | 4,193,446 | 4,193 | 1 |
| F048 | `IsoGraph.Canon.dfsNode_dom` | 2879 | 2879 | leanpool-v4.34.0 | 4,730,011 | 4,730 | 1 |
| F049 | `FirstOrder.Language.schemaTruthStage_imp` | 746 | 746 | leanpool-v4.35.0-rc3 | 194,028,210 | 194,028 | 1 |
| F049 | `FirstOrder.Language.schemaTruthStage_imp` | 746 | 746 | leanpool-v4.34.0 | 197,885,515 | 197,885 | 1 |
| F050 | `RS.cechCount` | 911 | 911 | leanpool-v4.35.0-rc3 | 157,420,889 | 157,420 | 1 |
| F050 | `RS.cechCount` | 911 | 911 | leanpool-v4.34.0 | 186,364,554 | 186,364 | 1 |
| F051 | `putnam_1964_a4` | 1769 | 1769 | putnambench-v4.27.0 | 111,471,011 | 111,471 | 1 |
| F051 | `putnam_1964_a4` | 1769 | 1769 | putnambench-v4.26.0 | 115,677,592 | 115,677 | 1 |
| F052 | `putnam_1995_a3` | 4085 | 4085 | putnambench-v4.27.0 | 14,127,586 | 14,127 | 1 |
| F052 | `putnam_1995_a3` | 4085 | 4085 | putnambench-v4.26.0 | 14,303,829 | 14,303 | 1 |
| F053 | `putnam_1988_a2` | 2162 | 2161 | putnambench-v4.27.0 | 58,090,725 | 58,090 | 1 |
| F053 | `putnam_1988_a2` | 2162 | 2161 | putnambench-v4.26.0 | 60,689,837 | 60,689 | 1 |
| F054 | `putnam_2001_b1` | 3178 | 3178 | putnambench-v4.27.0 | 50,251,248 | 50,251 | 1 |
| F054 | `putnam_2001_b1` | 3178 | 3178 | putnambench-v4.26.0 | 50,745,938 | 50,745 | 1 |
| F055 | `putnam_1964_b2` | 1754 | 1754 | putnambench-v4.26.0 | 134,489,542 | 134,489 | 1 |
| F056 | `putnam_2007_a1` | 5464 | 5463 | putnambench-v4.27.0 | 528,106,440 | 528,106 | 1 |
| F056 | `putnam_2007_a1` | 5464 | 5463 | putnambench-v4.26.0 | 551,645,096 | 551,645 | 1 |
| F057 | `putnam_1970_b5` | 2134 | 2134 | putnambench-v4.27.0 | 288,824,885 | 288,824 | 1 |
| F057 | `putnam_1970_b5` | 2134 | 2134 | putnambench-v4.26.0 | 299,472,901 | 299,472 | 1 |
| F058 | `putnam_1968_a1` | 1084 | 1084 | putnambench-v4.27.0 | 60,254,798 | 60,254 | 1 |
| F058 | `putnam_1968_a1` | 1084 | 1084 | putnambench-v4.26.0 | 63,206,600 | 63,206 | 1 |
| F059 | `putnam_1991_b1` | 3313 | 3313 | putnambench-v4.27.0 | 342,798,486 | 342,798 | 1 |
| F059 | `putnam_1991_b1` | 3313 | 3313 | putnambench-v4.26.0 | 351,967,827 | 351,967 | 1 |
| F060 | `putnam_2019_a1` | 2381 | 2381 | putnambench-v4.27.0 | 3,223,874,343 | 3,223,874 | 1 |
| F060 | `putnam_2019_a1` | 2381 | 2381 | putnambench-v4.26.0 | 3,448,431,931 | 3,448,431 | 1 |

원시 소스·컴파일 로그·측정 표본·결과 해시는 다음 로컬 실행 폴더에 보관한다.

`/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-final-20261102`

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

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-cslib-final-20261102/F028`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-cslib-final-20261102/F029`

- 기존 증거: `/Users/jwkweon/00_work/00_project/05_pseudolab/.worktrees/arena-final60-baselines/runs/manual/final60-baselines-cslib-final-20261102/F030`

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

## 비교 Length와 최종 검증

비교 Length는 Final 평가기의 `arena-paper-compatible-v1` 계산과 60문제 모두 일치하는 제공값이다. 표의 별도 로컬 값은 `lean-source-anchored-v1` 감사 결과다. F053은 제공 2,162·로컬 2,161, F056은 제공 5,464·로컬 5,463이며 두 값을 보존한다.

최종 추가 감사에서 60개 결과와 127개 문제·버전 조합의 원시 소스·로그·compiler setup 해시를 확인했다. 실제 HB 표본은 133개이며 F001의 기존 3회 표본을 유지한 결과다. 추가 감사는 HB를 다시 측정하지 않았다. 17개 현재 고정 환경의 전체 라이브러리 bytes·127개 입력 문맥과 8개 compiler의 Lean/Lake 바이너리 해시·버전을 확인했다. 초기 Strata setup은 앞서 보존한 원래 setup 해시와 감사 자료로 대조한다.

최종 감사 기록: `runs/manual/final60-completion-audit-20261102/receipt.json`, SHA256 `0760355f08b529d4793b7352ffc4c65fdb75f80579de7578cd149dfd19e4bc58`. 환경 구성·캐시 재개·Strata setup 경로 감사는 [환경 준비 문서](final60-environments.md)에 설명한다.
