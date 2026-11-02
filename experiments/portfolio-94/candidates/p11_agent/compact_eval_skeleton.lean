theorem fold_advances_evaluation_poly
  (i : Fin (ℓ)) (h_i_succ_lt : i + 1 < ℓ + 𝓡)
  (coeffs : Fin (2 ^ (ℓ - ↑i)) → L) (r_chal : L) :
  let P_i : L[X] := intermediateEvaluationPoly 𝔽q β h_ℓ_add_R_rate (i := ⟨i, by
    exact Nat.lt_trans (n := i) (k := ℓ+1) (m := ℓ) (h₁ := i.isLt) (by exact Nat.lt_add_one ℓ)
  ⟩) coeffs
  let f_i := fun (x : (sDomain 𝔽q β h_ℓ_add_R_rate)
      ⟨i, by exact Nat.lt_trans (n := i) (k := r) (m := ℓ) (h₁ := by omega) (by omega)⟩) =>
    P_i.eval (x.val : L)
  let f_i_plus_1 := fold (i := ⟨i, by omega⟩) (h_i := by omega) (f := f_i) (r_chal := r_chal)
  let new_coeffs := fun j : Fin (2^(ℓ - (i + 1))) =>
    (1 - r_chal) * (coeffs ⟨j.val * 2, by
      rw [←Nat.add_zero (j.val * 2)]
      apply mul_two_add_bit_lt_two_pow (c := ℓ - i) (a := j) (b := ℓ - (↑i + 1))
        (i := 0) (by omega) (by omega)
    ⟩) +
    r_chal * (coeffs ⟨j.val * 2 + 1, by
      apply mul_two_add_bit_lt_two_pow (c := ℓ - i) (a := j) (b := ℓ - (↑i + 1))
        (i := 1) (by omega) (by omega)
    ⟩)
  let P_i_plus_1 :=
    intermediateEvaluationPoly 𝔽q β h_ℓ_add_R_rate (i := ⟨i+1, by omega⟩) new_coeffs
  ∀ (y : (sDomain 𝔽q β h_ℓ_add_R_rate)
    ⟨i+1, by omega⟩), f_i_plus_1 y = P_i_plus_1.eval y.val := by
  intro P_i f_i f_i_plus_1 new_coeffs P_i_plus_1 y
  let fiberMap := qMap_total_fiber 𝔽q β ⟨i, by omega⟩ 1 h_i_succ_lt y
  let x₀ := fiberMap 0
  let x₁ := fiberMap 1
  have h_eval_qMap (b : Fin 2) :
      (AdditiveNTT.qMap 𝔽q β ⟨i, by omega⟩).eval (fiberMap b).val = y := by
    apply Eq.symm
    have h := generates_quotient_point_if_is_fiber_of_y 𝔽q β i 1
      (Nat.succ_le_of_lt i.isLt) (fiberMap b) y ⟨b, rfl⟩
    rw [iteratedQuotientMap_k_eq_1_is_qMap] at h
    exact congrArg Subtype.val h
  have h_fiber_diff : x₁.val = 1 + x₀.val := by
    simp only [x₀, x₁, fiberMap,
      qMap_total_fiber_one_level_eq 𝔽q β i (Nat.succ_le_of_lt i.isLt), Fin2ToF2,
      Fin.isValue, one_ne_zero, ↓reduceIte, zero_smul, one_smul, zero_add,
      Submodule.coe_add, get_sDomain_first_basis_eq_1]
  let P₀ := evenRefinement 𝔽q β h_ℓ_add_R_rate i coeffs
  let P₁ := oddRefinement 𝔽q β h_ℓ_add_R_rate i coeffs
  have h_P_i_eval := evaluation_poly_split_identity 𝔽q β h_ℓ_add_R_rate i coeffs
  change P_i.eval x₀.val * _ + P_i.eval x₁.val * _ = _
  simp only [h_P_i_eval, Fin.eta, Polynomial.eval_add, eval_comp,
        h_eval_qMap, Polynomial.eval_mul, Polynomial.eval_X, P_i, x₀, x₁]
  calc
    _ = P₀.eval y.val * (1 - r_chal) + P₁.eval y.val * r_chal := by
      rw [h_fiber_diff]
      ring1
    _ = _ := by
      simp +singlePass only [P_i_plus_1, new_coeffs, P₀, P₁, evenRefinement, oddRefinement,
        intermediateEvaluationPoly]
      simp only [Fin.eta, Polynomial.eval_finset_sum,
        Polynomial.eval_C_mul, Finset.sum_mul,
        ← Finset.sum_add_distrib]
      apply Finset.sum_congr rfl
      intro j _
      ring1
