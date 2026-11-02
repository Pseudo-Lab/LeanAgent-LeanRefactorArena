lemma ι_timeOrderF_superCommuteF_eq_time {φ ψ : 𝓕.CrAnFieldOp}
    (hφψ : crAnTimeOrderRel φ ψ) (hψφ : crAnTimeOrderRel ψ φ) (a b : 𝓕.FieldOpFreeAlgebra) :
    ι 𝓣ᶠ(a * [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * b) =
    ι ([ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * 𝓣ᶠ(a * b)) := by
  let m := LinearMap.mul ℂ 𝓕.FieldOpFreeAlgebra
  let c := [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF
  let i := (ι (𝓕 := 𝓕)).toLinearMap
  let t := timeOrderF (𝓕 := 𝓕)
  suffices h : (m.comp (m.flip c)).compr₂ (R := ℂ) (A := ℂ) (i.comp t) =
      m.compr₂ (R := ℂ) (A := ℂ) (i.comp ((m c).comp t)) by
    exact LinearMap.congr_fun₂ h a b
  apply Basis.ext ofCrAnListFBasis
  intro x
  apply Basis.ext ofCrAnListFBasis
  intro y
  change ι 𝓣ᶠ(ofCrAnListFBasis x * [ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * ofCrAnListFBasis y) =
    ι ([ofCrAnOpF φ, ofCrAnOpF ψ]ₛF * 𝓣ᶠ(ofCrAnListFBasis x * ofCrAnListFBasis y))
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
