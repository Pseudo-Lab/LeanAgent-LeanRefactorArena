theorem interleaved_affine_gaps_imply_tensor_gaps
    (hC_proximityGapAffineLines : e_ε_correlatedAgreementAffineLinesNat
      (F := F) (A := A) (ι := ι) (C := MC) (e := e) (ε := ε))
    (h_interleaved_gaps : ∀ m : ℕ, m ≥ 1 →
      e_ε_correlatedAgreementAffineLinesNat (F := F)
        (A := InterleavedSymbol A (Fin m)) (ι := ι) (C := MC ^⋈ (Fin m)) e ε) :
    ∀ (ϑ : ℕ), (hϑ_gt_0 : ϑ > 0) → δ_ε_multilinearCorrelatedAgreement_Nat (F := F) (A := A)
      (ι := ι) (C := MC) (ϑ := ϑ) (e := e) (ε := ε) := by
  classical
  intro ϑ hϑ
  induction ϑ, hϑ using Nat.le_induction with
  | base =>
    intro u hp
    simp_rw [multilinearCombine₁_eq_affineLineEvaluation] at hp
    simp_rw [prob_uniform_singleton_finFun_eq (F := F)
      (P := fun r => Δ₀(affineLineEvaluation (u 0) (u 1) r, MC) ≤ e),
      Nat.cast_one, ENNReal.coe_one, one_mul] at hp
    have hc := hC_proximityGapAffineLines (u 0) (u 1) hp
    have hu : finMapTwoWords (u 0) (u 1) = u := (piFinTwoEquiv _).injective rfl
    exact hu ▸ hc
  | succ n hn ih =>
    intro u hp
    simp only [multilinearCombine_recursive_form] at hp
    erw [prob_split_last_uniform_sampling_of_finFun
      (P := multilinearCombine_affineComb_split_last_close MC u e)] at hp
    apply CA_split_rowwise_implies_CA
    apply h_interleaved_gaps (2 ^ n) Nat.one_le_two_pow
    apply lt_of_lt_of_le (prob_R_star_gt_threshold MC u e hp)
    exact Pr_le_Pr_of_implies (D := $ᵖ F) (h_imp := fun r hr =>
      correlatedAgreement_of_mem_R_star_tensor MC ih u ⟨r, hr⟩)
