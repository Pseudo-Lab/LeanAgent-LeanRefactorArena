lemma ι_timeOrderF_superCommuteF_eq_time {φ ψ : 𝓕.CrAnFieldOp}
    (hφψ : crAnTimeOrderRel φ ψ) (hψφ : crAnTimeOrderRel ψ φ) (a b : 𝓕.FieldOpFreeAlgebra) :
    ι 𝓣ᶠ(a * [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * b) =
    ι ([ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * 𝓣ᶠ(a * b)) := by
  let m := LinearMap.mul ℂ 𝓕.FieldOpFreeAlgebra
  let c := [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF
  suffices h : (m.comp (m.flip c)).compr₂ (ι.toLinearMap.comp timeOrderF) =
      m.compr₂ (ι.toLinearMap.comp ((m c).comp timeOrderF)) from
    LinearMap.congr_fun₂ h a b
  apply LinearMap.ext_basis ofCrAnListFBasis ofCrAnListFBasis
  intro x y
  change ι 𝓣ᶠ(_ * _ * _) = ι (_ * 𝓣ᶠ(_ * _))
  simp only [c, ofListBasis_eq_ofList, map_mul, ← ofCrAnListF_append, timeOrderF_ofCrAnListF,
    map_smul, mul_smul_comm]
  obtain ⟨l, r, f⟩ : ∃ l r : 𝓕.WickAlgebra, ∀ z : List 𝓕.CrAnFieldOp,
      (∀ c ∈ z, crAnTimeOrderRel φ c ∧ crAnTimeOrderRel c φ) →
      ι (ofCrAnListF (crAnTimeOrderList (x ++ z ++ y))) = l * ι (ofCrAnListF z) * r := ⟨_, _, fun z hz => by
      rw [crAnTimeOrderList, insertionSort_of_eq_list (h := hz)]
      simp only [ofCrAnListF_append, map_mul]
      exact @mul_assoc 𝓕.WickAlgebra _ _ _ _⟩
  trans crAnTimeOrderSign (x ++ φ :: ψ :: y) •
    (l * ι [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * r)
  · rw [superCommuteF_ofCrAnOpF_ofCrAnOpF]
    simp only [mul_sub, sub_mul, mul_smul_comm, smul_mul_assoc,
      map_sub, map_smul, ← ofCrAnListF_singleton, ← ofCrAnListF_append,
      timeOrderF_ofCrAnListF]
    rw [f _ ?_, f _ ?_]
    simp only [List.append_assoc, List.cons_append, List.nil_append]
    rw [crAnTimeOrderSign_swap_eq_time hφψ hψφ, smul_sub, smul_comm]
    all_goals simp [*]
  rw [Subalgebra.mem_center_iff.mp (ι_superCommuteF_ofCrAnOpF_ofCrAnOpF_mem_center φ ψ),
    mul_assoc]
  have w := f [] (List.forall_mem_nil _)
  simp at w
  rw [← w]
  by_cases q : 𝓕.crAnStatistics φ = 𝓕.crAnStatistics ψ
  · simp only [crAnTimeOrderSign, Wick.koszulSign_eq_rel_eq_stat _ _ hφψ hψφ q.symm]
  · simp only [ι_superCommuteF_of_diff_statistic q, zero_mul, smul_zero]
