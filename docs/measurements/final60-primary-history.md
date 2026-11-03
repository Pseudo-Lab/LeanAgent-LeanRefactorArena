# 기존 Final 60문제 대표 버전 기록

출처: main commit `f3d6f359820a2e4e6f7d3001dc7f620440accce3`의 [공개 원본 JSON](https://github.com/Pseudo-Lab/LeanAgent-LeanRefactorArena/blob/f3d6f359820a2e4e6f7d3001dc7f620440accce3/dashboard/public/data/final-baselines.json). JSON SHA256: `c8dbb29fc7f5699f8b605e38c2a67632f1bbc16cfc8cb65ec16b4ce7a8e8776c`.

기존 대표 버전의 3회 중앙값 48문제·1회 표본 12문제를 보존한다. 원시 증거 경로·해시는 위 불변 JSON에 있다. 이번 전체 지정 버전 측정은 [새 60문제·127개 조합 결과](final60-baselines.md)에 따로 기록한다. 서로 다른 실행의 표본을 합산하거나 기존 표본을 새 계측으로 집계하지 않았다.

| 문제 | 정리 | 대표 버전 | Length | raw HB | 환산 HB | 표본 수 | 실행 |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| F001 | `Core.InitsUpdatesComm` | v4.31.0 | 224 | 4,182,543 | 4,182 | 3 | `20261101-final60-usd1-r1` |
| F002 | `Lambda.denote_suffix_irrel` | v4.31.0 | 904 | 4,367,942 | 4,367 | 3 | `20261101-final60-usd1-r1` |
| F003 | `Lambda.denote_Denotes` | v4.31.0 | 931 | 10,924,741 | 10,924 | 3 | `20261101-final60-usd1-r1` |
| F004 | `Lambda.callOfLFunc_eraseMetadata_congr` | v4.31.0 | 291 | 21,349,352 | 21,349 | 3 | `20261101-final60-usd1-r1` |
| F005 | `Lambda.liftBVars_typeCheck` | v4.31.0 | 209 | 17,630,418 | 17,630 | 3 | `20261101-final60-usd1-r1` |
| F006 | `Lambda.liftBVars_denote` | v4.31.0 | 972 | 8,898,103 | 8,898 | 3 | `20261101-final60-usd1-r1` |
| F007 | `Lambda.LExpr.typeCheck_to_HasTypeA` | v4.31.0 | 429 | 7,093,908 | 7,093 | 3 | `20261101-final60-usd1-r1` |
| F008 | `Lambda.callOfLFunc_constr_disjoint_denote` | v4.31.0 | 968 | 7,351,678 | 7,351 | 3 | `20261101-final60-usd1-r1` |
| F009 | `Lambda.denote_replaceMetadata` | v4.31.0 | 938 | 7,275,281 | 7,275 | 3 | `20261101-final60-usd1-r1` |
| F010 | `Lambda.denote_ext` | v4.31.0 | 1200 | 4,667,076 | 4,667 | 3 | `20261101-final60-usd1-r1` |
| F011 | `FTheory.SU5.ChargeSpectrum.containsPhenoCompletionsOfMinimallyAllows_viableCompletions` | v4.34.1 | 4 | 64,051,730 | 64,051 | 3 | `20261101-final60-usd1-r1` |
| F012 | `FTheory.SU5.ChargeSpectrum.isPhenoClosedQ5_viableCharges` | v4.34.1 | 12 | 74,041,515 | 74,041 | 3 | `20261101-final60-usd1-r1` |
| F013 | `FTheory.SU5.ChargeSpectrum.isPhenoClosedQ10_viableCharges` | v4.34.1 | 12 | 79,108,905 | 79,108 | 3 | `20261101-final60-usd1-r1` |
| F014 | `PauliMatrix.pauliContrDown_mul_pauliContr_mul_pauliContrDown` | v4.34.1 | 181 | 212,379,390 | 212,379 | 3 | `20261101-final60-usd1-r1` |
| F015 | `PauliMatrix.pauliContr_mul_pauliContrDown_mul_pauliContr` | v4.34.1 | 183 | 136,539,444 | 136,539 | 3 | `20261101-final60-usd1-r1` |
| F016 | `Electromagnetism.ElectromagneticPotential.time_deriv_time_deriv_electricField_of_isExtrema` | v4.34.1 | 1372 | 23,941,357 | 23,941 | 3 | `20261101-final60-usd1-r1` |
| F017 | `FieldSpecification.WickAlgebra.ι_timeOrderF_superCommuteF_eq_time` | v4.34.1 | 1217 | 35,774,564 | 35,774 | 3 | `20261101-final60-usd1-r1` |
| F018 | `fundamental_theorem_of_variational_calculus'` | v4.34.1 | 851 | 10,202,612 | 10,202 | 3 | `20261102-remaining22` |
| F019 | `HermitianMat.inv_convex` | v4.34.1 | 1025 | 211,678,398 | 211,678 | 3 | `20261102-remaining22` |
| F020 | `cauchyBinet` | v4.34.1 | 1200 | 143,389,348 | 143,389 | 3 | `20261102-remaining22` |
| F021 | `Cslib.LambdaCalculus.LocallyNameless.Fsub.Typing.progress` | v4.34.1 | 408 | 59,934,118 | 59,934 | 3 | `20261101-final60-usd1-r1` |
| F022 | `Cslib.SKI.parallelReduction_diamond` | v4.34.1 | 407 | 1,500,504 | 1,500 | 3 | `20261102-speed-pilot` |
| F023 | `Cslib.CCS.bisimilarity_congr_choice` | v4.34.1 | 251 | 3,940,866 | 3,940 | 1 | `20261102-provisional12` |
| F024 | `Cslib.LambdaCalculus.LocallyNameless.Fsub.Typing.preservation` | v4.34.1 | 391 | 38,109,474 | 38,109 | 3 | `20261102-remaining22` |
| F025 | `Cslib.FLP.PseudoConsensus.of_consensus` | v4.34.1 | 433 | 11,623,316 | 11,623 | 3 | `20261102-remaining22` |
| F026 | `Cslib.Automata.NA.Buchi.buchiFamily_saturation` | v4.33.1 | 623 | 56,937,148 | 56,937 | 3 | `20261102-remaining22` |
| F027 | `Cslib.FLP.OnePseudoConsensus.nonUniform_step` | v4.34.1 | 368 | 39,338,816 | 39,338 | 3 | `20261102-remaining22` |
| F028 | `Cslib.LTS.OmegaExecution.flatten_execution` | v4.33.1 | 312 | 27,606,221 | 27,606 | 3 | `20261102-remaining22` |
| F029 | `Cslib.FLP.CanReachVia.subset_inp` | v4.34.1 | 364 | 33,198,680 | 33,198 | 3 | `20261102-remaining22` |
| F030 | `Cslib.LambdaCalculus.LocallyNameless.Untyped.Term.parallel_diamond` | v4.34.1 | 519 | 8,589,146 | 8,589 | 3 | `20261102-remaining22` |
| F031 | `interleaved_affine_gaps_imply_tensor_gaps` | v4.34.0 | 1353 | 7,774,574 | 7,774 | 3 | `20261101-final60-usd1-r1` |
| F032 | `Binius.BinaryBasefold.fold_advances_evaluation_poly` | v4.31.0 | 1906 | 47,701,818 | 47,701 | 3 | `20261101-final60-usd1-r1` |
| F033 | `Binius.BinaryBasefold.fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius` | v4.31.0 | 1463 | 16,839,601 | 16,839 | 3 | `20261101-final60-usd1-r1` |
| F034 | `Combine.master_lemma` | v4.33.1 | 546 | 190,043,621 | 190,043 | 3 | `20261101-final60-usd1-r1` |
| F035 | `JohnsonBound.johnson_bound_alphabet_free` | v4.31.0 | 2440 | 84,743,551 | 84,743 | 3 | `20261101-final60-usd1-r1` |
| F036 | `ProximityToRS.dir_close_of_many_close_pts` | v4.31.0 | 5128 | 106,464,364 | 106,464 | 3 | `20261101-final60-usd1-r1` |
| F037 | `ProximityGap.RS_exists_nonzero_kernelVec_of_det_eq_zero_natDegree_le_one` | v4.31.0 | 2122 | 163,948,549 | 163,948 | 3 | `20261101-final60-usd1-r1` |
| F038 | `ProximityGap.RS_jointAgreement_of_goodCoeffs_card_gt` | v4.31.0 | 5538 | 62,515,167 | 62,515 | 3 | `20261101-final60-usd1-r1` |
| F039 | `Sumcheck.Spec.SingleRound.Simple.reduction_perfectCompleteness` | v4.31.0 | 1426 | 44,522,173 | 44,522 | 3 | `20261101-final60-usd1-r1` |
| F040 | `ps_coprime_case_constant` | v4.34.0 | 1105 | 38,031,288 | 38,031 | 3 | `20261101-final60-usd1-r1` |
| F041 | `LeanPool.Erdos132ConvexK3.erlv_case12_other_d1_bone_impossible` | v4.35.0-rc3 | 2030 | 49,681,455 | 49,681 | 3 | `20261101-final60-usd1-r1` |
| F042 | `CoxeterSystem.matsumoto_reduced_aux` | v4.35.0-rc3 | 1699 | 3,091,286 | 3,091 | 3 | `20261101-final60-usd1-r1` |
| F043 | `Vlasov.transportedIntegral_continuousOn` | v4.35.0-rc3 | 2413 | 9,943,703 | 9,943 | 3 | `20261101-final60-usd1-r1` |
| F044 | `ZetaZeros.step1_double` | v4.35.0-rc3 | 2315 | 13,000,252 | 13,000 | 3 | `20261101-final60-usd1-r1` |
| F045 | `LocalComplexGeometry.holomorphic_constant_rank` | v4.35.0-rc3 | 1756 | 53,089,872 | 53,089 | 3 | `20261101-final60-usd1-r1` |
| F046 | `LeanEval.Topology.ClassificationOfSurfaces.Moise.PartialTriangulation.exists_chartMatchingControlOn_of_metricSpace` | v4.35.0-rc3 | 1645 | 11,484,649 | 11,484 | 3 | `20261101-final60-usd1-r1` |
| F047 | `LeanEval.Topology.ClassificationOfSurfaces.Moise.PolygonalCircle.insertZero_nonadjacent_disjoint` | v4.35.0-rc3 | 1509 | 6,122,522 | 6,122 | 3 | `20261101-final60-usd1-r1` |
| F048 | `IsoGraph.Canon.dfsNode_dom` | v4.35.0-rc3 | 2879 | 4,193,446 | 4,193 | 3 | `20261101-final60-usd1-r1` |
| F049 | `FirstOrder.Language.schemaTruthStage_imp` | v4.35.0-rc3 | 746 | 194,028,210 | 194,028 | 1 | `20261102-provisional12` |
| F050 | `RS.cechCount` | v4.35.0-rc3 | 911 | 157,420,890 | 157,420 | 1 | `20261102-provisional12` |
| F051 | `putnam_1964_a4` | v4.27.0 | 1769 | 111,470,986 | 111,470 | 3 | `20261101-final60-usd1-r1` |
| F052 | `putnam_1995_a3` | v4.27.0 | 4085 | 14,127,586 | 14,127 | 1 | `20261102-provisional12` |
| F053 | `putnam_1988_a2` | v4.27.0 | 2162 | 58,090,725 | 58,090 | 1 | `20261102-provisional12` |
| F054 | `putnam_2001_b1` | v4.27.0 | 3178 | 50,251,248 | 50,251 | 1 | `20261102-provisional12` |
| F055 | `putnam_1964_b2` | v4.26.0 | 1754 | 134,489,542 | 134,489 | 1 | `20261102-provisional12` |
| F056 | `putnam_2007_a1` | v4.27.0 | 5464 | 528,106,378 | 528,106 | 1 | `20261102-provisional12` |
| F057 | `putnam_1970_b5` | v4.27.0 | 2134 | 288,824,887 | 288,824 | 1 | `20261102-provisional12` |
| F058 | `putnam_1968_a1` | v4.27.0 | 1084 | 60,254,800 | 60,254 | 1 | `20261102-provisional12` |
| F059 | `putnam_1991_b1` | v4.27.0 | 3313 | 342,798,487 | 342,798 | 1 | `20261102-provisional12` |
| F060 | `putnam_2019_a1` | v4.27.0 | 2381 | 3,223,874,343 | 3,223,874 | 1 | `20261102-provisional12` |
