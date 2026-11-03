theorem johnson_bound_alphabet_free [Field F]
    {B : Finset (Fin n → F)} {v : Fin n → F} {e : ℕ} (hB : 1 < B.card) :
    let d := sInf { d | ∃ u ∈ B, ∃ v ∈ B, u ≠ v ∧ hammingDist u v = d }
    let q : ℚ := card F
    let _frac := q / (q - 1)
    e ≤ n - ((n * (n - d)) : ℝ).sqrt →
    (B ∩ ({ x | Δ₀(x, v) ≤ e } : Finset _)).card ≤ q * d * n := by
  intro d q frac h
  let B' := B ∩ ({ x | Δ₀(x, v) ≤ e } : Finset _)
  have q_not_small : q ≥ (2 : ℚ) := by
    change (2 : ℚ) ≤ (card F : ℚ)
    exact_mod_cast Nat.succ_le_of_lt (show 1 < card F from by
      simpa [Fintype.one_lt_card_iff] using (⟨(0 : F), (1 : F), by simp⟩ : ∃ a b : F, a ≠ b))
  have hd_mem : d ∈ { k | ∃ u ∈ B, ∃ w ∈ B, u ≠ w ∧ hammingDist u w = k } :=
    Nat.sInf_mem (by
      obtain ⟨u, hu, w, hw, huw⟩ := one_lt_card.mp hB
      exact ⟨hammingDist u w, u, hu, w, hw, huw, rfl⟩)
  obtain ⟨u, hu, w, hw, huw, hd⟩ := hd_mem
  have d_not_small : 1 ≤ d := hd ▸ Nat.succ_le_of_lt (hammingDist_pos.mpr huw)
  have d_le_n : d ≤ n := by
    rw [← hd]
    simpa using hammingDist_le_card_fintype (x := u) (y := w)
  have n_not_small : n ≥ 1 := le_trans d_not_small d_le_n
  by_cases h_size : B'.card < 2
  · exact le_trans (show (B'.card : ℚ) ≤ 1 from by exact_mod_cast Nat.le_of_lt_succ h_size)
      (le_trans (by norm_num : (1 : ℚ) ≤ 2)
        (by simpa [mul_assoc] using johnson_qdn_ge_two q_not_small d_not_small n_not_small))
  · have hd_le_dB' : (d : ℚ) ≤ JohnsonBound.d B' := by
      let S' : Set ℕ := { d | ∃ u ∈ B', ∃ v ∈ B', u ≠ v ∧ hammingDist u v = d }
      have hS'nonempty : S'.Nonempty := by
        obtain ⟨u, hu, w, hw, huw⟩ := one_lt_card.mp (show 1 < B'.card by omega)
        exact ⟨hammingDist u w, u, hu, w, hw, huw, rfl⟩
      obtain ⟨u, hu, w, hw, huw, hd⟩ := Nat.sInf_mem hS'nonempty
      calc (d : ℚ)
          ≤ ↑(sInf S') := by
            exact_mod_cast (Nat.sInf_le
              ⟨u, (mem_inter.mp hu).1, w, (mem_inter.mp hw).1, huw, hd⟩ : d ≤ sInf S')
        _ ≤ JohnsonBound.d B' := by exact_mod_cast min_dist_le_d (B := B') (by omega)
    have hn_pos_nat : 0 < n := Nat.succ_le_iff.1 n_not_small
    have hn_pos : (0 : ℚ) < n := by exact_mod_cast hn_pos_nat
    have hq1_pos : (0 : ℚ) < q - 1 := by linarith only [q_not_small]
    have hq_pos : (0 : ℚ) < q := by linarith only [q_not_small]
    by_cases h_d_close_n : q / (q - 1) * (d / n) > 1
    · have hden_lb : (1 : ℚ) / (n * (q - 1)) ≤ JohnsonDenominator B' v :=
        le_trans (johnson_gap_frac_d_gt_one (B := B')
          (q_not_small := q_not_small) (n_not_small := n_not_small)
          (h_d_close_n := h_d_close_n) (hd_le_dB := hd_le_dB')) (by
          simpa only [JohnsonDenominator, mul_div_assoc] using
            johnson_den_ge_frac_d (B := B') (v := v))
      have h_strong : JohnsonConditionStrong B' v :=
        johnson_condition_strong_iff_johnson_denom_pos.2
          (lt_of_lt_of_le (one_div_pos.mpr (mul_pos hn_pos hq1_pos)) hden_lb)
      have hnum_nonneg : (0 : ℚ) ≤ frac * JohnsonBound.d B' / n :=
        div_nonneg (mul_nonneg (div_nonneg hq_pos.le hq1_pos.le)
          (le_trans (by exact_mod_cast Nat.zero_le d) hd_le_dB')) hn_pos.le
      refine le_trans (johnson_bound h_strong) ?_
      calc (frac * JohnsonBound.d B' / n) / JohnsonDenominator B' v
          ≤ (frac * JohnsonBound.d B' / n) / (1 / (n * (q - 1))) :=
            div_le_div_of_nonneg_left hnum_nonneg
              (one_div_pos.mpr (mul_pos hn_pos hq1_pos)) hden_lb
        _ = q * JohnsonBound.d B' := by
            dsimp only [frac]
            generalize JohnsonBound.d B' = D
            field_simp [hn_pos.ne', hq1_pos.ne']
            <;> ring
        _ ≤ q * d * n := by
            have hd_le_n := johnson_d_le_n (B := B') (le_of_not_gt h_size)
            have hd_ge1 : (1 : ℚ) ≤ (d : ℚ) := by exact_mod_cast d_not_small
            calc q * JohnsonBound.d B' ≤ q * n := mul_le_mul_of_nonneg_left hd_le_n hq_pos.le
                 _ ≤ q * d * n := by
                   simpa only [mul_one] using mul_le_mul_of_nonneg_right
                     (mul_le_mul_of_nonneg_left hd_ge1 hq_pos.le) hn_pos.le
    · have hn_nonneg : (0 : ℚ) ≤ n := hn_pos.le
      have hfrac_pos : (0 : ℚ) < frac := div_pos hq_pos hq1_pos
      have hfrac_gt1 : (1 : ℚ) < frac :=
        (one_lt_div hq1_pos).2 (sub_lt_self q zero_lt_one)
      have hn2_pos : (0 : ℚ) < (n : ℚ) ^ 2 := pow_pos hn_pos _
      have h_div'_real := JohnsonBound.johnson_hyp_implies_div_ineq hn_pos_nat d_le_n h
      have h_div'_q : (1 - (d / n : ℚ)) ≤ (1 - (e / n : ℚ)) ^ 2 := by
        have hc : ((1 - (d / n : ℚ)) : ℝ) ≤ ((1 - (e / n : ℚ)) ^ 2 : ℝ) := by
          simpa using h_div'_real
        exact_mod_cast hc
      have h_johnson_strong : JohnsonConditionStrong B' v := by
        have h_muln : (e : ℚ) / n ≤ 1 - ((1 - (d : ℚ) / n) : ℝ).sqrt := by
          have he_le : (e : ℝ) ≤ n := by
            linarith only [h, sqrt_nonneg ((n : ℝ) * (n - d))]
          have hnR : (0 : ℝ) < n := by exact_mod_cast hn_pos_nat
          have he_div : (e : ℝ) / n ≤ 1 := (div_le_one hnR).2 he_le
          have hroot : √(1 - (d : ℝ) / n) ≤ 1 - (e : ℝ) / n :=
            sqrt_le_iff.mpr ⟨sub_nonneg.mpr he_div, h_div'_real⟩
          push_cast
          linarith only [hroot]
        have h_J_bound : 1 - ((1 - (d : ℚ) / n) : ℝ).sqrt ≤ J q (d / n) := by
          simpa using sqrt_le_J (by linarith only [q_not_small] : q > 1)
            (div_nonneg (by exact_mod_cast Nat.cast_nonneg d) hn_nonneg)
            ((div_le_one hn_pos).2 (by exact_mod_cast d_le_n))
            (le_of_not_gt h_d_close_n)
        exact johnson_condition_weak_implies_strong
          (lt_of_le_of_ne (le_trans h_muln h_J_bound) (johnson_e_div_ne_J hn_pos_nat
            (Nat.succ_le_iff.1 d_not_small) (by linarith only [q_not_small]) h_muln h_J_bound
            (le_of_not_gt h_d_close_n)))
          (show 1 < B'.card by omega) (by exact_mod_cast (show (2 : ℚ) ≤ (card F : ℚ) from q_not_small))
      refine le_trans (johnson_bound h_johnson_strong) ?_
      set D0 : ℚ := d / n
      set E0 : ℚ := e / n
      set Den : ℚ := D0 - 2 * E0 + frac * E0 ^ 2
      have quad_nonneg : (0 : ℚ) ≤ D0 - 2 * E0 + E0 ^ 2 := by nlinarith only [h_div'_q]
      have frac_sub_one_eq : frac - 1 = (1 : ℚ) / (q - 1) := by
        dsimp only [frac]; field_simp; ring
      have one_div_q_le : (1 : ℚ) / q ≤ frac - 1 := by
        rw [frac_sub_one_eq]
        exact one_div_le_one_div_of_le hq1_pos (by linarith only : q - 1 ≤ q)
      have denom_expansion : JohnsonDenominator B' v =
          frac * (JohnsonBound.d B' / n - 2 * JohnsonBound.e B' v / n +
          frac * (JohnsonBound.e B' v / n) ^ 2) := by
        change (1 - frac * JohnsonBound.e B' v / n) ^ 2 -
          (1 - frac * JohnsonBound.d B' / n) = _
        ring
      have e_ineq : JohnsonBound.e B' v ≤ e := by
        simpa [B'] using JohnsonBound.e_ball_le_radius (B := B) (v := v) (r := (e : ℚ))
          (by simpa [B'] using show 0 < B'.card by omega)
      have hden1_pos : (0 : ℚ) <
          JohnsonBound.d B' / n - 2 * JohnsonBound.e B' v / n +
          frac * (JohnsonBound.e B' v / n) ^ 2 := by
        have hdenJ := johnson_condition_strong_iff_johnson_denom_pos.1 h_johnson_strong
        rw [denom_expansion] at hdenJ
        exact (mul_pos_iff_of_pos_left hfrac_pos).1 hdenJ
      have worst_case_bound :=
        johnson_worst_case_bound hn_pos (Nat.succ_le_iff.1 d_not_small) d_le_n h
          (le_of_not_gt h_d_close_n) hfrac_gt1 e_ineq hd_le_dB' quad_nonneg hden1_pos
      have hden_lb : (1 : ℚ) / (q * (n : ℚ) ^ 2) ≤ Den := by
        by_cases he0 : e = 0
        · subst he0; simpa [D0, E0, Den] using
            johnson_den_lb_e_zero hn_pos_nat (by linarith only [q_not_small]) (by exact_mod_cast d_not_small)
        · exact johnson_den_lb_e_pos hn_pos he0 one_div_q_le
            (sub_pos.mpr hfrac_gt1) quad_nonneg
      rw [denom_expansion, mul_div_assoc, mul_div_mul_left _ _ hfrac_pos.ne']
      refine le_trans worst_case_bound ?_
      suffices (d / n) / Den ≤ q * d * n by
        simpa only [Den, D0, E0, mul_div_assoc] using this
      calc (d / n) / Den
          ≤ (d / n) / ((1 : ℚ) / (q * (n : ℚ) ^ 2)) :=
            div_le_div_of_nonneg_left
              (div_nonneg (by exact_mod_cast Nat.zero_le d) hn_nonneg)
              (one_div_pos.mpr (mul_pos hq_pos hn2_pos)) hden_lb
        _ = q * d * n := by field_simp [ne_of_gt hq_pos, ne_of_gt hn_pos]
