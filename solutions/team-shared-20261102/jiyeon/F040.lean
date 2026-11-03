lemma ps_coprime_case_constant {F : Type} [Field F]
    (a_x a_y b_x b_y : ℕ) (n_x n_y : ℕ+)
    (h_bx_ge_ax : b_x ≥ a_x) (h_by_ge_ay : b_y ≥ a_y)
    (A B : F[X][Y]) (hA0 : A ≠ 0) (hB0 : B ≠ 0) (hrel : IsRelPrime A B)
    (h_f_degX : a_x ≥ degreeX A) (h_g_degX : b_x ≥ degreeX B)
    (h_f_degY : a_y ≥ natDegreeY A) (h_g_degY : b_y ≥ natDegreeY B)
    (P_x P_y : Finset F) [Nonempty P_x] [Nonempty P_y]
    (quot_x quot_y : F → F[X])
    (h_card_Px : n_x ≤ P_x.card) (h_card_Py : n_y ≤ P_y.card)
    (h_quot_x : ∀ y ∈ P_y, (quot_x y).natDegree ≤ (b_x - a_x) ∧
      evalY y B = (quot_x y) * (evalY y A))
    (h_quot_y : ∀ x ∈ P_x, (quot_y x).natDegree ≤ (b_y - a_y) ∧
      evalX x B = (quot_y x) * (evalX x A))
    (h_le_1 : 1 > (b_x : ℚ) / (n_x : ℚ) + (b_y : ℚ) / (n_y : ℚ)) :
    degreeX A = 0 ∧ natDegreeY A = 0 := by
  classical
  set mY := natDegreeY A with hmY; set mX := degreeX A with hmX
  set RY := resultant B A b_y mY with hRY
  set RX := resultant (swap B) (swap A) b_x mX with hRX
  have hA0' : swap A ≠ 0 := fun h ↦ hA0 (swap.injective (by simpa using h))
  have hRY0 : RY ≠ 0 := by
    simpa [RY, hRY, mY, hmY] using ps_resultant_ne_zero_of_is_rel_prime _ _ b_y
      (by simpa using h_g_degY) hA0 hrel
  have hRX0 : RX ≠ 0 := by
    rw [hRX, show mX = natDegreeY (swap A) from hmX.trans (ps_nat_degree_y_swap A).symm]
    simpa using ps_resultant_ne_zero_of_is_rel_prime _ _ b_x
      (by rw [ps_nat_degree_y_swap]; simpa using h_g_degX) hA0' (ps_is_rel_prime_swap hrel)
  have hcop : Pairwise fun x y : F ↦ IsCoprime (X - C x : F[X]) (X - C y) :=
    pairwise_coprime_X_sub_C fun _ _ h ↦ h
  have hprod_dvd_RY : (∏ x ∈ P_x, (X - C x) ^ mY) ∣ RY :=
    Finset.prod_dvd_of_coprime (fun _ _ _ _ hxy ↦ by simpa using (hcop hxy).pow) fun x hx ↦ by
      obtain ⟨hdegQ, hQ⟩ := h_quot_y x hx
      simpa [RY, hRY, mY, hmY] using ps_resultant_dvd_pow_eval_x _ _ _ _ b_y
        (by omega) (by simpa using h_g_degY) (by omega) hQ
  have hprod_dvd_RX : (∏ y ∈ P_y, (X - C y) ^ mX) ∣ RX :=
    Finset.prod_dvd_of_coprime (fun _ _ _ _ hyy' ↦ by simpa using (hcop hyy').pow) fun y hy ↦ by
      obtain ⟨hdegQ, hQ⟩ := h_quot_x y hy
      simpa [RX, hRX, mX, hmX] using ps_resultant_dvd_pow_eval_y A B y (quot_x y) b_x
        (by omega) (by simpa using h_g_degX) (by omega) hQ
  have hdeg_prod (S : Finset F) (m : ℕ) :
      (∏ x ∈ S, (X - C x) ^ m).natDegree = m * S.card := by
    rw [natDegree_prod _ _ (fun x _ ↦ pow_ne_zero _ (X_sub_C_ne_zero x))]
    simp [natDegree_pow, Finset.sum_const, smul_eq_mul, Nat.mul_comm]
  have hRY_le := le_trans
    (by simpa [RY, hRY] using ps_nat_degree_resultant_le A B mY b_y)
    (Nat.add_le_add (Nat.mul_le_mul_left _ h_g_degX) (le_of_eq (Nat.mul_comm b_y (degreeX A))))
  have hRX_le : RX.natDegree ≤ mX * b_y + mY * b_x := by
    have hdeg' : RX.natDegree ≤ mX * degreeX (swap B) + b_x * degreeX (swap A) := by
      simpa [RX, hRX] using ps_nat_degree_resultant_le (swap A) (swap B) mX b_x
    apply le_trans hdeg' (Nat.add_le_add ?_ ?_)
    · rw [ps_degree_x_swap B]; exact Nat.mul_le_mul_left _ (by simpa using h_g_degY)
    · rw [ps_degree_x_swap A]; exact le_of_eq (Nat.mul_comm b_x (natDegreeY A))
  have hmy_le_D : mY * (n_x : ℕ) ≤ mX * b_y + mY * b_x :=
    le_trans (le_trans (Nat.mul_le_mul_left _ h_card_Px)
      ((hdeg_prod P_x mY).symm ▸ natDegree_le_of_dvd hprod_dvd_RY hRY0)) (by linarith)
  have hmx_le_D : mX * (n_y : ℕ) ≤ mX * b_y + mY * b_x :=
    le_trans (le_trans (Nat.mul_le_mul_left _ h_card_Py)
      ((hdeg_prod P_y mX).symm ▸ natDegree_le_of_dvd hprod_dvd_RX hRX0)) hRX_le
  suffices mX * b_y + mY * b_x = 0 by
    constructor
    · change mX = 0
      have : mX * (n_y : ℕ) ≤ 0 := by omega
      exact (mul_eq_zero.mp (Nat.eq_zero_of_le_zero this)).resolve_right (Nat.ne_of_gt n_y.pos)
    · change mY = 0
      have : mY * (n_x : ℕ) ≤ 0 := by omega
      exact (mul_eq_zero.mp (Nat.eq_zero_of_le_zero this)).resolve_right (Nat.ne_of_gt n_x.pos)
  have hcross : b_x * (n_y : ℕ) + (n_x : ℕ) * b_y < (n_x : ℕ) * (n_y : ℕ) := by
    have hx : (0 : ℚ) < n_x := by exact_mod_cast n_x.pos
    have hy : (0 : ℚ) < n_y := by exact_mod_cast n_y.pos
    rw [div_add_div _ _ hx.ne' hy.ne'] at h_le_1
    exact_mod_cast (div_lt_one (mul_pos hx hy)).mp h_le_1
  have hx := Nat.mul_le_mul_right (b_x * (n_y : ℕ)) hmy_le_D
  have hy := Nat.mul_le_mul_right (b_y * (n_x : ℕ)) hmx_le_D
  by_contra hn
  have hlt := Nat.mul_lt_mul_of_pos_left hcross (Nat.pos_of_ne_zero hn)
  nlinarith only [hx, hy, hlt]
