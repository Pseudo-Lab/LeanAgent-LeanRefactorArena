lemma ι_timeOrderF_superCommuteF_eq_time {φ ψ : 𝓕.CrAnFieldOp}
    (hφψ : crAnTimeOrderRel φ ψ) (hψφ : crAnTimeOrderRel ψ φ) (a b : 𝓕.FieldOpFreeAlgebra) :
    ι 𝓣ᶠ(a * [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * b) =
    ι ([ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * 𝓣ᶠ(a * b)) := by
  have h φs' φs :
      ι 𝓣ᶠ(ofCrAnListF φs' * [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * ofCrAnListF φs) =
      ι [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * ι (𝓣ᶠ(ofCrAnListF φs' * ofCrAnListF φs)) := by
    let l1 :=
      List.takeWhile (fun c => ¬crAnTimeOrderRel φ c)
        ((φs' ++ φs).insertionSort crAnTimeOrderRel) ++
      List.filter (fun c => crAnTimeOrderRel φ c ∧ crAnTimeOrderRel c φ) φs'
    let l2 :=
      List.filter (fun c => crAnTimeOrderRel φ c ∧ crAnTimeOrderRel c φ) φs ++
      List.filter (fun c => crAnTimeOrderRel φ c ∧ ¬crAnTimeOrderRel c φ)
        ((φs' ++ φs).insertionSort crAnTimeOrderRel)
    have hs χ ξ
        (hχ : crAnTimeOrderRel φ χ ∧ crAnTimeOrderRel χ φ)
        (hξ : crAnTimeOrderRel φ ξ ∧ crAnTimeOrderRel ξ φ) :
        ι 𝓣ᶠ(ofCrAnListF (φs' ++ χ :: ξ :: φs)) =
        crAnTimeOrderSign (φs' ++ χ :: ξ :: φs) •
          (ι (ofCrAnListF l1) * ι (ofCrAnListF [χ, ξ]) * ι (ofCrAnListF l2)) := by
      rw [timeOrderF_ofCrAnListF,
        show φs' ++ χ :: ξ :: φs = φs' ++ [χ, ξ] ++ φs by simp,
        crAnTimeOrderList,
        insertionSort_of_eq_list 𝓕.crAnTimeOrderRel φ φs' [χ, ξ] φs (by simp_all)]
      simp only [List.append_assoc, decide_not, Bool.decide_and,
        ofCrAnListF_append, map_smul, map_mul, l1, l2, mul_assoc]
    trans crAnTimeOrderSign (φs' ++ φ :: ψ :: φs) •
      (ι (ofCrAnListF l1) * ι [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF *
        ι (ofCrAnListF l2))
    · conv_lhs =>
        rw [← ofCrAnListF_singleton, ← ofCrAnListF_singleton,
          superCommuteF_ofCrAnListF_ofCrAnListF]
        simp only [ofList_singleton, mul_sub, sub_mul,
          Algebra.mul_smul_comm, Algebra.smul_mul_assoc,
          ← ofCrAnListF_append, List.append_assoc,
          List.cons_append, List.nil_append, map_sub, map_smul]
        rw [hs φ ψ (by simp) ⟨hφψ, hψφ⟩,
          hs ψ φ ⟨hφψ, hψφ⟩ (by simp)]
      rw [crAnTimeOrderSign_swap_eq_time hφψ hψφ,
        superCommuteF_ofCrAnOpF_ofCrAnOpF, ← ofCrAnListF_singleton,
        ← ofCrAnListF_singleton]
      simp only [← ofCrAnListF_append, List.singleton_append,
        map_sub, map_smul, mul_sub, sub_mul,
        Algebra.mul_smul_comm, Algebra.smul_mul_assoc, smul_sub]
      module
    rw [Subalgebra.mem_center_iff.mp (ι_superCommuteF_ofCrAnOpF_ofCrAnOpF_mem_center φ ψ),
      mul_assoc, ← map_mul, ← ofCrAnListF_append]
    have h1 := insertionSort_of_takeWhile_filter 𝓕.crAnTimeOrderRel φ φs' φs
    simp only [l1, l2, decide_not, Bool.decide_and, List.append_assoc] at h1 ⊢
    rw [← h1, ← crAnTimeOrderList]
    by_cases hq : (𝓕 |>ₛ φ) ≠ (𝓕 |>ₛ ψ)
    · simp only [ι_superCommuteF_of_diff_statistic hq, zero_mul, smul_zero]
    · rw [crAnTimeOrderSign, Wick.koszulSign_eq_rel_eq_stat _ _ hφψ hψφ
        (by symm; simpa using hq), ← crAnTimeOrderSign, ← ofCrAnListF_append,
        timeOrderF_ofCrAnListF]
      simp only [map_smul, Algebra.mul_smul_comm]
  conv_rhs => rw [map_mul]
  rw [← ofCrAnListFBasis.linearCombination_repr a,
    ← ofCrAnListFBasis.linearCombination_repr b]
  simp only [Finsupp.linearCombination_apply, Finsupp.sum,
    Finset.sum_mul, Finset.mul_sum, Finset.smul_sum,
    Algebra.smul_mul_assoc, Algebra.mul_smul_comm, map_sum, map_smul,
    ofListBasis_eq_ofList, h]
