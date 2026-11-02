lemma ι_timeOrderF_superCommuteF_eq_time {φ ψ : 𝓕.CrAnFieldOp}
    (hφψ : crAnTimeOrderRel φ ψ) (hψφ : crAnTimeOrderRel ψ φ) (a b : 𝓕.FieldOpFreeAlgebra) :
    ι 𝓣ᶠ(a * [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * b) =
    ι ([ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * 𝓣ᶠ(a * b)) := by
  rw [map_mul]
  induction Basis.mem_span ofCrAnListFBasis a, Basis.mem_span ofCrAnListFBasis b using
    Submodule.span_induction₂
  · rename_i h g
    rcases h with ⟨x, rfl⟩
    rcases g with ⟨y, rfl⟩
    simp only [ofListBasis_eq_ofList, map_mul]
    obtain ⟨l, r, f⟩ : ∃ l r : 𝓕.WickAlgebra, ∀ z : List 𝓕.CrAnFieldOp,
        (∀ c ∈ z, crAnTimeOrderRel φ c ∧ crAnTimeOrderRel c φ) →
        ι (ofCrAnListF (crAnTimeOrderList (x ++ z ++ y))) = l * ι (ofCrAnListF z) * r := by
      refine ⟨?_, ?_, ?_⟩
      rotate_left 2
      intro z hz
      rw [crAnTimeOrderList, insertionSort_of_eq_list _ _ _ _ _ hz]
      simp only [ofCrAnListF_append, map_mul]
      exact @mul_assoc 𝓕.WickAlgebra _ _ _ _
    trans crAnTimeOrderSign (x ++ φ :: ψ :: y) •
      (l * ι [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * r)
    · rw [superCommuteF_ofCrAnOpF_ofCrAnOpF]
      simp only [mul_sub, sub_mul, Algebra.mul_smul_comm, Algebra.smul_mul_assoc,
        map_sub, map_smul, ← ofCrAnListF_singleton, ← ofCrAnListF_append,
        timeOrderF_ofCrAnListF]
      simp only [List.append_assoc, List.cons_append, List.nil_append]
      rw [crAnTimeOrderSign_swap_eq_time hφψ hψφ]
      have s := f [φ, ψ] (by simp [hφψ, hψφ])
      have v := f [ψ, φ] (by simp [hφψ, hψφ])
      simp only [List.append_assoc, List.cons_append, List.nil_append] at s v
      rw [s, v, smul_sub, smul_comm]
    rw [Subalgebra.mem_center_iff.mp (ι_superCommuteF_ofCrAnOpF_ofCrAnOpF_mem_center φ ψ),
      mul_assoc]
    have w := f [] (List.forall_mem_nil _)
    simp only [List.append_nil, ofCrAnListF_nil, map_one, mul_one] at w
    rw [← w]
    by_cases q : (𝓕 |>ₛ φ) ≠ (𝓕 |>ₛ ψ)
    · simp only [ι_superCommuteF_of_diff_statistic q, zero_mul, smul_zero]
    · rw [crAnTimeOrderSign, Wick.koszulSign_eq_rel_eq_stat _ _ hφψ hψφ (not_ne_iff.mp q).symm,
        ← crAnTimeOrderSign, ← ofCrAnListF_append, timeOrderF_ofCrAnListF]
      simp only [map_smul, Algebra.mul_smul_comm]
  all_goals simp only [*, add_mul, mul_add, map_add, map_smul, zero_mul,
    mul_zero, map_zero, Algebra.smul_mul_assoc, Algebra.mul_smul_comm]
