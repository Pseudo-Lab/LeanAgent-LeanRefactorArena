lemma ι_timeOrderF_superCommuteF_eq_time {φ ψ : 𝓕.CrAnFieldOp}
    (hφψ : crAnTimeOrderRel φ ψ) (hψφ : crAnTimeOrderRel ψ φ) (a b : 𝓕.FieldOpFreeAlgebra) :
    ι 𝓣ᶠ(a * [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * b) =
    ι ([ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * 𝓣ᶠ(a * b)) := by
  induction (Basis.mem_span ofCrAnListFBasis b) using Submodule.span_induction
  · rename_i x hx
    rcases hx with ⟨φs, rfl⟩
    simp only [ofListBasis_eq_ofList, map_mul]
    induction (Basis.mem_span ofCrAnListFBasis a) using Submodule.span_induction
    · rename_i x hx
      rcases hx with ⟨φs', rfl⟩
      simp only [ofListBasis_eq_ofList, map_mul]
      calc _
        _ = crAnTimeOrderSign (φs' ++ [φ, ψ] ++ φs) •
            (_ * _ * ι [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * _ * _) := by
          conv_lhs =>
            rw [superCommuteF_ofCrAnOpF_ofCrAnOpF, ← ofCrAnListF_singleton,
              ← ofCrAnListF_singleton]
            simp [mul_sub, sub_mul, ← ofCrAnListF_append]
            rw [timeOrderF_ofCrAnListF, timeOrderF_ofCrAnListF]
          rw [← crAnTimeOrderSign_swap_eq_time hφψ hψφ]
          simp only [map_smul]
          rw [smul_comm, ← smul_sub]
          have hs := insertionSort_of_eq_list 𝓕.crAnTimeOrderRel φ φs'
          rw [crAnTimeOrderList, show φs' ++ φ :: ψ :: φs = φs' ++ [φ, ψ] ++ φs by simp,
            hs [φ, ψ] φs (by simp [hφψ, hψφ])]
          rw [crAnTimeOrderList, show φs' ++ ψ :: φ :: φs = φs' ++ [ψ, φ] ++ φs by simp,
            hs [ψ, φ] φs (by simp [hφψ, hψφ])]
          repeat rw [ofCrAnListF_append]
          conv_rhs =>
            rw [superCommuteF_ofCrAnOpF_ofCrAnOpF, ← ofCrAnListF_singleton,
              ← ofCrAnListF_singleton]
            simp [← ofCrAnListF_append]
          simp [mul_sub, sub_mul]
          rfl

      rw [Subalgebra.mem_center_iff.mp (ι_superCommuteF_ofCrAnOpF_ofCrAnOpF_mem_center φ ψ)]
      simp only [mul_assoc, ← map_mul, ← ofCrAnListF_append]
      have h1 := insertionSort_of_takeWhile_filter 𝓕.crAnTimeOrderRel φ φs' φs
      simp only [decide_not, Bool.decide_and, List.append_assoc, List.cons_append, List.nil_append] at h1 ⊢
      rw [← h1, ← crAnTimeOrderList]
      by_cases hq : (𝓕 |>ₛ ψ) = (𝓕 |>ₛ φ)
      · rw [crAnTimeOrderSign, Wick.koszulSign_eq_rel_eq_stat _ _ hφψ hψφ hq,
          ← crAnTimeOrderSign, timeOrderF_ofCrAnListF]
        simp only [map_smul, Algebra.mul_smul_comm]
      · simp [ι_superCommuteF_of_diff_statistic (Ne.symm hq)]
    all_goals simp_all only [map_mul, zero_mul, map_zero, mul_zero, map_add,
      mul_add, add_mul, map_smul, smul_mul_assoc, Algebra.mul_smul_comm]
  all_goals simp_all only [map_mul, zero_mul, map_zero, mul_zero, map_add,
    mul_add, add_mul, map_smul, smul_mul_assoc, Algebra.mul_smul_comm]
