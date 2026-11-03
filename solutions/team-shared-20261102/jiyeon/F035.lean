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
    exact_mod_cast (Nat.succ_le_iff.2 (Fintype.one_lt_card : 1 < card F))
  have d_not_small : d ≥ 1 := by
    let S : Set ℕ := { d | ∃ u ∈ B, ∃ v ∈ B, u ≠ v ∧ hammingDist u v = d }
    simpa [S] using sInf.le_sInf_of_LB (S := S) (i := 1)
      (by obtain ⟨u, hu, v, hv, huv⟩ := one_lt_card.mp hB
          exact ⟨hammingDist u v, u, hu, v, hv, huv, rfl⟩)
      (fun s ⟨u, _, v, _, huv, hdist⟩ => hdist ▸ Nat.succ_le_of_lt (hammingDist_pos.mpr huv))
  have d_le_n : d ≤ n := by
    obtain ⟨u, hu, w, hw, huw⟩ := one_lt_card.mp hB
    exact le_trans (Nat.sInf_le ⟨u, hu, w, hw, huw, rfl⟩)
      (by simpa using hammingDist_le_card_fintype (x := u) (y := w))
  have n_not_small : n ≥ 1 := d_not_small.trans d_le_n
  have qdn_not_small : (q * d * n) ≥ 2 := by
    simpa [mul_assoc] using johnson_qdn_ge_two q_not_small d_not_small n_not_small
  by_cases h_size : B'.card < 2
  · exact le_trans (show (B'.card : ℚ) ≤ 1 from by exact_mod_cast Nat.le_of_lt_succ h_size)
      (le_trans (by norm_num : (1 : ℚ) ≤ 2) qdn_not_small)
  · have hd_le_dB' : (d : ℚ) ≤ JohnsonBound.d B' := by
      let S : Set ℕ := { d | ∃ u ∈ B, ∃ v ∈ B, u ≠ v ∧ hammingDist u v = d }
      let S' : Set ℕ := { d | ∃ u ∈ B', ∃ v ∈ B', u ≠ v ∧ hammingDist u v = d }
      have hsubset : S' ⊆ S := fun _ ⟨u, hu, w, hw, huw, hd⟩ =>
        ⟨u, (mem_inter.mp hu).1, w, (mem_inter.mp hw).1, huw, hd⟩
      have hS'nonempty : S'.Nonempty := by
        obtain ⟨u, hu, w, hw, huw⟩ := one_lt_card.mp (show 1 < B'.card by omega)
        exact ⟨hammingDist u w, u, hu, w, hw, huw, rfl⟩
      calc (d : ℚ)
          ≤ ↑(sInf S') := by exact_mod_cast Nat.sInf_le (hsubset (Nat.sInf_mem hS'nonempty))
        _ ≤ JohnsonBound.d B' := by exact_mod_cast min_dist_le_d (B := B') (by omega)
    have hn_pos_nat : 0 < n := Nat.succ_le_iff.1 n_not_small
    have hn_pos : (0 : ℚ) < n := by exact_mod_cast hn_pos_nat
    have hq1_pos : (0 : ℚ) < q - 1 := by linarith
    by_cases h_d_close_n : q / (q - 1) * (d / n) > 1
    · have h_strong : JohnsonConditionStrong B' v := by
        simpa [JohnsonConditionStrong, q, mul_div_assoc] using
          lt_of_lt_of_le (show (1 - (q / (q - 1)) * (JohnsonBound.d B' / n) : ℚ) < 0 from by
            linarith [lt_of_lt_of_le h_d_close_n (mul_le_mul_of_nonneg_left
              (div_le_div_of_nonneg_right hd_le_dB' (by exact_mod_cast Nat.cast_nonneg n))
              (div_nonneg (by linarith) (by linarith)))]) (sq_nonneg _)
      have hden_ge : JohnsonDenominator B' v ≥ frac * JohnsonBound.d B' / n - 1 := by
        simpa [JohnsonDenominator, q, frac, mul_div_assoc] using
          johnson_den_ge_frac_d (B := B') (v := v)
      have hgap : frac * JohnsonBound.d B' / (n : ℚ) - 1 ≥ 1 / (n * (q - 1)) := by
        simpa [q, frac] using johnson_gap_frac_d_gt_one (B := B')
          (q_not_small := by simpa [q] using q_not_small)
          (n_not_small := n_not_small)
          (h_d_close_n := by simpa [q, frac] using h_d_close_n)
          (hd_le_dB := hd_le_dB')
      have hden_lb : (1 : ℚ) / (n * (q - 1)) ≤ JohnsonDenominator B' v := by linarith
      have hnum_nonneg : (0 : ℚ) ≤ frac * JohnsonBound.d B' / n :=
        div_nonneg (mul_nonneg (div_nonneg (by linarith) (by linarith))
          (le_trans (by exact_mod_cast Nat.zero_le d) hd_le_dB')) hn_pos.le
      calc (B'.card : ℚ)
          ≤ (frac * JohnsonBound.d B' / n) / JohnsonDenominator B' v := by
            simpa using johnson_bound h_strong
        _ ≤ (frac * JohnsonBound.d B' / n) / (1 / (n * (q - 1))) :=
            div_le_div_of_nonneg_left hnum_nonneg
              (one_div_pos.mpr (mul_pos hn_pos hq1_pos)) hden_lb
        _ = q * JohnsonBound.d B' := by
            dsimp [frac]
            field_simp
            <;> ring
        _ ≤ q * d * n := by
            have hd_le_n := johnson_d_le_n (B := B') (le_of_not_gt h_size)
            have hd_ge1 : (1 : ℚ) ≤ (d : ℚ) := by exact_mod_cast d_not_small
            have hq_nn : (0 : ℚ) ≤ q := by linarith
            nlinarith [mul_le_mul_of_nonneg_left hd_le_n hq_nn,
              mul_le_mul_of_nonneg_left hd_ge1 (mul_nonneg hq_nn (le_of_lt hn_pos))]
    · have hn_nonneg : (0 : ℚ) ≤ n := hn_pos.le
      have hq_pos : (0 : ℚ) < q := by linarith
      have hfrac_pos : (0 : ℚ) < frac := div_pos hq_pos hq1_pos
      have hfrac_gt1 : (1 : ℚ) < frac := by
        simpa [frac] using (one_lt_div hq1_pos).2 (by linarith : q - 1 < q)
      have hn2_pos : (0 : ℚ) < (n : ℚ) ^ 2 := pow_pos hn_pos _
      have h_div'_q : (1 - (d / n : ℚ)) ≤ (1 - (e / n : ℚ)) ^ 2 := by
        have hr : ((1 - (d / n : ℚ)) : ℝ) ≤ ((1 - (e / n : ℚ)) : ℝ) ^ 2 := by
          simpa using johnson_hyp_implies_div_ineq hn_pos_nat d_le_n h
        exact_mod_cast hr
      have denom_expansion : JohnsonDenominator B' v =
          frac * (JohnsonBound.d B' / n - 2 * JohnsonBound.e B' v / n +
          frac * (JohnsonBound.e B' v / n) ^ 2) := by
        dsimp [JohnsonDenominator, q, frac]
        ring
      have e_ineq : JohnsonBound.e B' v ≤ e := by
        simpa [B'] using JohnsonBound.e_ball_le_radius (B := B) (v := v) (r := (e : ℚ))
          (by simpa [B'] using show 0 < B'.card by omega)
      have hden1_pos : (0 : ℚ) <
          JohnsonBound.d B' / n - 2 * JohnsonBound.e B' v / n +
            frac * (JohnsonBound.e B' v / n) ^ 2 := by
        have he1 : (e : ℚ) / n ≤ 1 := by
          apply (div_le_one hn_pos).2
          exact_mod_cast h.trans (sub_le_self _ (sqrt_nonneg _))
        have heB := div_le_div_of_nonneg_right e_ineq hn_pos.le
        have hdB := div_le_div_of_nonneg_right hd_le_dB' hn_pos.le
        have hquad : (0 : ℚ) ≤ JohnsonBound.d B' / n -
            2 * (JohnsonBound.e B' v / n) + (JohnsonBound.e B' v / n) ^ 2 := by
          nlinarith only [h_div'_q, hdB, mul_nonneg (sub_nonneg.mpr heB)
            (show (0 : ℚ) ≤ 2 - (e : ℚ) / n - JohnsonBound.e B' v / n by linarith)]
        by_cases hz : JohnsonBound.e B' v / n = 0
        · simpa only [mul_div_assoc, hz, mul_zero, zero_pow (by decide : 2 ≠ 0), sub_zero,
            add_zero] using lt_of_lt_of_le
              (div_pos (by exact_mod_cast (Nat.succ_le_iff.1 d_not_small)) hn_pos) hdB
        · have hp := mul_pos (sub_pos.mpr hfrac_gt1) (sq_pos_of_ne_zero hz)
          simp only [mul_div_assoc]
          nlinarith only [hquad, hp]
      have h_johnson_strong : JohnsonConditionStrong B' v :=
        johnson_condition_strong_iff_johnson_denom_pos.2
          (by rw [denom_expansion]; exact mul_pos hfrac_pos hden1_pos)
      calc (B'.card : ℚ)
          ≤ (frac * JohnsonBound.d B' / n) / JohnsonDenominator B' v := by
            simpa using johnson_bound h_johnson_strong
        _ ≤ q * (d : ℚ) * n := by
            set D0 : ℚ := d / n
            set E0 : ℚ := e / n
            set Den : ℚ := D0 - 2 * E0 + frac * E0 ^ 2
            have quad_nonneg : (0 : ℚ) ≤ D0 - 2 * E0 + E0 ^ 2 := by
              change (0 : ℚ) ≤ d / n - 2 * (e / n) + (e / n) ^ 2
              nlinarith only [h_div'_q]
            have frac_sub_one_eq : frac - 1 = (1 : ℚ) / (q - 1) := by
              dsimp [frac]
              field_simp [hq1_pos.ne']
              <;> ring
            have one_div_q_le : (1 : ℚ) / q ≤ frac - 1 := by
              simpa [frac_sub_one_eq] using
                (one_div_le_one_div_of_le hq1_pos (by linarith : q - 1 ≤ q))
            have term_simplification : (frac * JohnsonBound.d B' / (n : ℚ)) /
                JohnsonDenominator B' v =
                (JohnsonBound.d B' / n) /
                (JohnsonBound.d B' / n - 2 * JohnsonBound.e B' v / n +
                frac * (JohnsonBound.e B' v / n) ^ 2) := by
                  rw [denom_expansion, mul_div_assoc]
                  exact mul_div_mul_left _ _ hfrac_pos.ne'
            have worst_case_bound :
                (JohnsonBound.d B' / n) /
                (JohnsonBound.d B' / n - 2 * JohnsonBound.e B' v / n +
                  frac * (JohnsonBound.e B' v / n) ^ 2) ≤
                (d / n) / (d / n - 2 * e / n + frac * (e / n) ^ 2) :=
              johnson_worst_case_bound hn_pos (Nat.succ_le_iff.1 d_not_small) d_le_n h
                (le_of_not_gt h_d_close_n) hfrac_gt1 e_ineq hd_le_dB' quad_nonneg hden1_pos
            have hden_lb : (1 : ℚ) / (q * (n : ℚ) ^ 2) ≤ Den := by
              by_cases he0 : e = 0
              · subst he0; simpa [D0, E0, Den] using
                  johnson_den_lb_e_zero hn_pos_nat (by linarith) (by exact_mod_cast d_not_small)
              · exact johnson_den_lb_e_pos hn_pos he0 one_div_q_le
                  (by linarith) quad_nonneg
            rw [term_simplification]
            calc (JohnsonBound.d B' / n) /
                    (JohnsonBound.d B' / n - 2 * JohnsonBound.e B' v / n +
                      frac * (JohnsonBound.e B' v / n) ^ 2)
                ≤ (d / n) / (d / n - 2 * e / n + frac * (e / n) ^ 2) := worst_case_bound
              _ = (d / n) / Den := by simp [Den, D0, E0, mul_div_assoc]
              _ ≤ (d / n) / ((1 : ℚ) / (q * (n : ℚ) ^ 2)) :=
                  div_le_div_of_nonneg_left
                    (div_nonneg (by exact_mod_cast Nat.zero_le d) hn_nonneg)
                    (one_div_pos.mpr (mul_pos hq_pos hn2_pos)) hden_lb
              _ = q * d * n := by field_simp [ne_of_gt hq_pos, ne_of_gt hn_pos]
