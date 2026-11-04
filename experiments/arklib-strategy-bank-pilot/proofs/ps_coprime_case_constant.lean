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
  set mY := natDegreeY A
  set mX := degreeX A
  have bound (R : F[X]) (S : Finset F) (m n d : ℕ) (hn : n ≤ S.card)
      (hR : R ≠ 0) (hd : R.natDegree ≤ d)
      (hdiv : ∀ x ∈ S, (X - C x) ^ m ∣ R) : m * n ≤ d := by
    have hp := Finset.prod_dvd_of_coprime
      (fun _ _ _ _ hxy ↦ (pairwise_coprime_X_sub_C (fun _ _ h ↦ h) hxy).pow) hdiv
    have hdvd := natDegree_le_of_dvd hp hR
    rw [natDegree_prod _ _ (fun x _ ↦ pow_ne_zero _ (X_sub_C_ne_zero x))] at hdvd
    apply (Nat.mul_le_mul_left m hn).trans
    apply le_trans ?_ hd
    simpa only [natDegree_pow, natDegree_X_sub_C, Nat.mul_one, Finset.sum_const,
      smul_eq_mul, Nat.mul_comm] using hdvd
  have hmy_le_D : mY * (n_x : ℕ) ≤ mX * b_y + mY * b_x := by
    refine bound (resultant B A b_y mY) P_x mY n_x _ h_card_Px
      (ps_resultant_ne_zero_of_is_rel_prime _ _ b_y h_g_degY hA0 hrel) ?_ ?_
    · exact (ps_nat_degree_resultant_le A B mY b_y).trans
        (by simpa only [Nat.add_comm] using (Nat.add_le_add
          (Nat.mul_le_mul_left mY h_g_degX) (le_of_eq (Nat.mul_comm b_y (degreeX A)))))
    · intro x hx
      exact ps_resultant_dvd_pow_eval_x A B x (quot_y x) b_y
        (h_f_degY.trans h_by_ge_ay) h_g_degY
        ((h_quot_y x hx).1.trans (Nat.sub_le_sub_left h_f_degY b_y)) (h_quot_y x hx).2
  have hmx_le_D : mX * (n_y : ℕ) ≤ mX * b_y + mY * b_x := by
    refine bound (resultant (swap B) (swap A) b_x mX) P_y mX n_y _ h_card_Py ?_ ?_ ?_
    · dsimp [mX]
      rw [← ps_nat_degree_y_swap A]
      exact ps_resultant_ne_zero_of_is_rel_prime _ _ b_x
        (by rw [ps_nat_degree_y_swap]; exact h_g_degX)
        (fun h ↦ hA0 (swap.injective (by simpa using h))) (ps_is_rel_prime_swap hrel)
    · apply le_trans (ps_nat_degree_resultant_le (swap A) (swap B) mX b_x)
      apply Nat.add_le_add
      · rw [ps_degree_x_swap B]; exact Nat.mul_le_mul_left _ h_g_degY
      · rw [ps_degree_x_swap A]; exact le_of_eq (Nat.mul_comm b_x (natDegreeY A))
    · intro y hy
      exact ps_resultant_dvd_pow_eval_y A B y (quot_x y) b_x
        (h_f_degX.trans h_bx_ge_ax) h_g_degX
        ((h_quot_x y hy).1.trans (Nat.sub_le_sub_left h_f_degX b_x)) (h_quot_x y hy).2
  suffices mX * b_y + mY * b_x = 0 by
    exact ⟨(mul_eq_zero.mp (Nat.eq_zero_of_le_zero (hmx_le_D.trans_eq this))).resolve_right n_y.ne_zero,
      (mul_eq_zero.mp (Nat.eq_zero_of_le_zero (hmy_le_D.trans_eq this))).resolve_right n_x.ne_zero⟩
  have hn_x0 : (0 : ℚ) < n_x := by exact_mod_cast n_x.pos
  have hn_y0 : (0 : ℚ) < n_y := by exact_mod_cast n_y.pos
  have hsmall : (b_x : ℚ) * n_y + (b_y : ℚ) * n_x < (n_x : ℚ) * n_y := by
    apply (div_lt_one (mul_pos hn_x0 hn_y0)).mp
    simpa only [div_add_div _ _ (ne_of_gt hn_x0) (ne_of_gt hn_y0), mul_comm] using h_le_1
  have hs : b_x * (n_y : ℕ) + b_y * (n_x : ℕ) < (n_x : ℕ) * n_y := by exact_mod_cast hsmall
  by_contra hD0
  have hp := Nat.mul_lt_mul_of_pos_left hs (Nat.pos_of_ne_zero hD0)
  have hy := Nat.mul_le_mul_right (b_x * (n_y : ℕ)) hmy_le_D
  have hx := Nat.mul_le_mul_right (b_y * (n_x : ℕ)) hmx_le_D
  simp only [mul_add, add_mul, mul_assoc, mul_left_comm, mul_comm] at hp hy hx
  clear * - hp hy hx
  omega
