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
  have hi : i.val + 1 ≤ ℓ := i.isLt
  let fiberMap := qMap_total_fiber 𝔽q β (i := ⟨i, by omega⟩) 
    (h_i_add_steps := h_i_succ_lt) (y := y)
  let x₀ := fiberMap 0
  let x₁ := fiberMap 1
  let P := intermediateEvaluationPoly 𝔽q β h_ℓ_add_R_rate (i := ⟨i, by omega⟩) coeffs
  let P₀ := evenRefinement 𝔽q β h_ℓ_add_R_rate i coeffs
  let P₁ := oddRefinement 𝔽q β h_ℓ_add_R_rate i coeffs
  have hq (k : Fin 2) : (AdditiveNTT.qMap 𝔽q β ⟨i, by omega⟩).eval (fiberMap k).val = y.val := by
    have h := iteratedQuotientMap_k_eq_1_is_qMap 𝔽q β h_ℓ_add_R_rate i hi (fiberMap k)
    have h_res := generates_quotient_point_if_is_fiber_of_y 𝔽q β i 1 hi
      (fiberMap k) y ⟨k, rfl⟩
    exact (congrArg Subtype.val h).symm.trans $ congrArg Subtype.val h_res.symm
  have hd : x₁.val - x₀.val = 1 := by
    have hx₀ := qMap_total_fiber_one_level_eq 𝔽q β i hi y 0
    have hx₁ := qMap_total_fiber_one_level_eq 𝔽q β i hi y 1
    simp only [Fin2ToF2, one_ne_zero, ↓reduceIte, zero_smul,
      one_smul, zero_add] at hx₀ hx₁
    dsimp only [x₁, x₀, fiberMap]
    rw [hx₁, hx₀, Submodule.coe_add, add_sub_cancel_right]
    simp only [get_sDomain_basis]
    exact normalizedWᵢ_eval_βᵢ_eq_1 𝔽q β
  change P.eval x₀.val * ((1 - r_chal) * x₁.val - r_chal) +
      P.eval x₁.val * (r_chal - (1 - r_chal) * x₀.val) = _
  simp only [P, x₀, x₁, evaluation_poly_split_identity 𝔽q β   ,
    Polynomial.eval_add, eval_comp, hq, Polynomial.eval_mul, Polynomial.eval_X]
  calc
    _ = P₀.eval y.val * (1 - r_chal) + P₁.eval y.val * r_chal := by
      linear_combination (P₀.eval y.val * (1 - r_chal) + P₁.eval y.val * r_chal) * hd
    _ = _ := by
      simp only [P₀, P₁, evenRefinement, oddRefinement, intermediateEvaluationPoly,
        Polynomial.eval_finsetSum, Polynomial.eval_mul, Polynomial.eval_C]
      rw [Finset.sum_mul, Finset.sum_mul, ←Finset.sum_add_distrib]
      apply Finset.sum_congr rfl
      intro j hj
      ring1