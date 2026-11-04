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
  simp only
  intro y
  let fiberMap := qMap_total_fiber 𝔽q β (i := ⟨i, by omega⟩) (steps := 1)
    (h_i_add_steps := by simp only; omega) (y := y)
  let x₀ := fiberMap 0
  let x₁ := fiberMap 1
  let P := intermediateEvaluationPoly 𝔽q β h_ℓ_add_R_rate (i := ⟨i, by omega⟩) coeffs
  let P₀ := evenRefinement 𝔽q β h_ℓ_add_R_rate i coeffs
  let P₁ := oddRefinement 𝔽q β h_ℓ_add_R_rate i coeffs
  have hq (k : Fin 2) : (AdditiveNTT.qMap 𝔽q β ⟨i, by omega⟩).eval (fiberMap k).val = y := by
    have h := iteratedQuotientMap_k_eq_1_is_qMap 𝔽q β h_ℓ_add_R_rate i (by omega) (fiberMap k)
    simp only [Subtype.eq_iff] at h
    rw [h.symm]
    exact congrArg Subtype.val (generates_quotient_point_if_is_fiber_of_y 𝔽q β i 1
      (by omega) (fiberMap k) y ⟨k, rfl⟩).symm
  have hd : x₁.val - x₀.val = 1 := by
    have h₀ := qMap_total_fiber_one_level_eq 𝔽q β i (by omega) y 0
    have h₁ := qMap_total_fiber_one_level_eq 𝔽q β i (by omega) y 1
    dsimp only at h₀ h₁
    dsimp only [x₀, x₁, fiberMap]
    rw [h₁, h₀]
    simp only [Fin2ToF2, one_ne_zero, ↓reduceIte, zero_smul, one_smul, zero_add,
      Submodule.coe_add, get_sDomain_basis, add_zero,
      normalizedWᵢ_eval_βᵢ_eq_1, add_sub_cancel_right]
  have hs := evaluation_poly_split_identity 𝔽q β h_ℓ_add_R_rate ⟨i, by omega⟩ coeffs
  have he (k : Fin 2) : P.eval (fiberMap k).val =
      P₀.eval y.val + (fiberMap k).val * P₁.eval y.val := by
    simp only [P, hs, Fin.eta, Polynomial.eval_add, eval_comp, hq,
      Polynomial.eval_mul, Polynomial.eval_X, P₀, P₁]
  change P.eval x₀.val * ((1 - r_chal) * x₁.val - r_chal) +
    P.eval x₁.val * (r_chal - (1 - r_chal) * x₀.val) = _
  rw [he 0, he 1]
  calc
    _ = P₀.eval y.val * (1 - r_chal) + P₁.eval y.val * r_chal := by
      rw [sub_eq_iff_eq_add.mp hd]
      ring
    _ = _ := by
      simp only [P₀, P₁, evenRefinement, oddRefinement, intermediateEvaluationPoly,
        Polynomial.eval_finset_sum, Polynomial.eval_mul, Polynomial.eval_C,
        Finset.sum_mul]
      rw [←Finset.sum_add_distrib]
      apply Finset.sum_congr rfl
      intro j hj
      ring
