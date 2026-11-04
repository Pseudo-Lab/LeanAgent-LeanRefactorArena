theorem interleaved_affine_gaps_imply_tensor_gaps
    (hC_proximityGapAffineLines : e_ε_correlatedAgreementAffineLinesNat
      (F := F) (A := A) (ι := ι) (C := MC) (e := e) (ε := ε))
    (h_interleaved_gaps : ∀ m : ℕ, m ≥ 1 →
      e_ε_correlatedAgreementAffineLinesNat (F := F)
        (A := InterleavedSymbol A (Fin m)) (ι := ι) (C := MC ^⋈ (Fin m)) e ε) :
    ∀ (ϑ : ℕ), (hϑ_gt_0 : ϑ > 0) → δ_ε_multilinearCorrelatedAgreement_Nat (F := F) (A := A)
      (ι := ι) (C := MC) (ϑ := ϑ) (e := e) (ε := ε) := by
  classical
  letI : Nonempty F := ⟨0⟩
  intro ϑ
  induction ϑ with
  | zero => intro h; contradiction
  | succ n ih =>
    cases n with
    | zero =>
      simp only [zero_add, gt_iff_lt, zero_lt_one, ModuleCode, forall_const]
      intro u hp
      simp_rw [multilinearCombine₁_eq_affineLineEvaluation] at hp
      simp_rw [prob_uniform_singleton_finFun_eq (F := F)
        (P := fun r => Code.distFromCode (affineLineEvaluation (u 0) (u 1) r) (MC : Set (Word A ι)) ≤ e),
        Nat.cast_one, ENNReal.coe_one, one_mul] at hp
      have hu : u = finMapTwoWords (u 0) (u 1) := by
        funext i
        fin_cases i <;> rfl
      simpa only [jointProximityNat₂, ← hu] using hC_proximityGapAffineLines (u 0) (u 1) hp
    | succ n =>
      intro _ u hp
      let U₀ := (splitHalfRowWiseInterleavedWords (ϑ := n + 1) u).1
      let U₁ := (splitHalfRowWiseInterleavedWords (ϑ := n + 1) u).2
      let P : F → (Fin (n + 1) → F) → Prop := fun a r =>
        Code.distFromCode (multilinearCombine u (Fin.snoc r a)) (MC : Set (Word A ι)) ≤ e
      have hs := prob_split_last_uniform_sampling_of_finFun (P := P)
      dsimp only [P] at hs
      have hsnoc (r : Fin (n + 1 + 1) → F) :
          Fin.snoc (fun i => r i.castSucc) (r (Fin.last (n + 1))) = r :=
        Fin.snoc_init_self r
      simp_rw [hsnoc] at hs
      rw [hs] at hp
      have hcomb (r : Fin (n + 1) → F) (a : F) :
          multilinearCombine u (Fin.snoc r a) =
            multilinearCombine (affineLineEvaluation U₀ U₁ a) r := by
        rw [multilinearCombine_recursive_form]
        simp only [Fin.snoc_last, Fin.init_snoc]
        rfl
      simp_rw [hcomb] at hp
      have hR := prob_R_star_gt_threshold (ϑ := n + 1) (MC := MC) (ε := ε) (u := u) (e := e) hp
      apply CA_split_rowwise_implies_CA (u := u) (e := e)
      apply h_interleaved_gaps (2 ^ (n + 1)) Nat.one_le_two_pow
      apply lt_of_lt_of_le hR
      apply Pr_le_Pr_of_implies
      intro r hr
      exact correlatedAgreement_of_mem_R_star_tensor (MC := MC) (ϑ_pred := n + 1)
        (ih := ih (Nat.succ_pos n)) (u := u) ⟨r, hr⟩
