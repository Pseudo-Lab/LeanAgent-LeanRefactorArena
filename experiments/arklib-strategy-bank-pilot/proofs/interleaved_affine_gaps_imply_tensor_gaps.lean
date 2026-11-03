theorem interleaved_affine_gaps_imply_tensor_gaps
    (hC_proximityGapAffineLines : e_ε_correlatedAgreementAffineLinesNat
      (F := F) (A := A) (ι := ι) (C := MC) (e := e) (ε := ε))
    (h_interleaved_gaps : ∀ m : ℕ, m ≥ 1 →
      e_ε_correlatedAgreementAffineLinesNat (F := F)
        (A := InterleavedSymbol A (Fin m)) (ι := ι) (C := MC ^⋈ (Fin m)) e ε) :
    ∀ (ϑ : ℕ), (hϑ_gt_0 : ϑ > 0) → δ_ε_multilinearCorrelatedAgreement_Nat (F := F) (A := A)
      (ι := ι) (C := MC) (ϑ := ϑ) (e := e) (ε := ε) := by
  classical
  intro n hn
  cases n with
  | zero => contradiction
  | succ n =>
    clear hn
    induction n with
    | zero =>
      simp only [zero_add, ModuleCode]
      intro u hp
      simp only [multilinearCombine₁_eq_affineLineEvaluation (F := F) (u := u),
        prob_uniform_singleton_finFun_eq (F := F)
          (P := fun r => Δ₀(affineLineEvaluation (u 0) (u 1) r, MC) ≤ e),
        Nat.cast_one, ENNReal.coe_one, one_mul] at hp
      have hc := hC_proximityGapAffineLines (u 0) (u 1) hp
      simp only [jointProximityNat₂, Fin.isValue] at hc
      have hu : u = finMapTwoWords (u 0) (u 1) := by
        funext i
        match i with
        | 0 => rfl
        | 1 => rfl
      rw [hu.symm] at hc
      exact hc
    | succ k ih =>
      intro u hp
      let U₀ : WordStack A (Fin (2 ^ (k + 1))) ι :=
        (splitHalfRowWiseInterleavedWords (ϑ := k + 1) u).1
      let U₁ : WordStack A (Fin (2 ^ (k + 1))) ι :=
        (splitHalfRowWiseInterleavedWords (ϑ := k + 1) u).2
      have heq (r : Fin (k + 1 + 1) → F) :
          multilinearCombine u r =
            multilinearCombine (affineLineEvaluation U₀ U₁ (r (Fin.last (k + 1))))
              (fun i => r i.castSucc) := by
        rw [multilinearCombine_recursive_form]
        rfl
      simp only [heq] at hp
      rw [prob_split_last_uniform_sampling_of_finFun
        (ϑ := k + 1) (F := F)
        (P := fun rl ri =>
          Δ₀(multilinearCombine (affineLineEvaluation U₀ U₁ rl) ri, MC) ≤ e)] at hp
      have hR := prob_R_star_gt_threshold (MC := MC) (ε := ε)
        (ϑ := k + 1) (u := u) (e := e) hp
      apply CA_split_rowwise_implies_CA (u := u) (e := e)
      apply h_interleaved_gaps (2 ^ (k + 1)) Nat.one_le_two_pow
        (u₀ := ⋈|U₀) (u₁ := ⋈|U₁)
      apply lt_of_lt_of_le hR
      apply Pr_le_Pr_of_implies
      intro r hr
      exact correlatedAgreement_of_mem_R_star_tensor (MC := MC) (e := e) (ε := ε)
        (ih := ih) (u := u) ⟨r, hr⟩
