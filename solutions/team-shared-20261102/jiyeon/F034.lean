lemma master_lemma
  [Nonempty ι]
  {φ : ι ↪ F} {dstar m : ℕ}
  {fs : Fin m → ι → F} {degs : Fin m → ℕ} (hdegs : ∀ i, degs i ≤ dstar)
  {δ : ℝ≥0}
  (hδLt : δ < (min (1 - (ReedSolomon.sqrtRate dstar φ))
    (1 - (rate (code φ dstar)) - 1 / Fintype.card ι)))
  {S : Finset ι}
  (hS_card : (1 - δ) * (Fintype.card ι) ≤ S.card)
  {v : (i : Fin m) → Fin (block_size dstar degs i) → Polynomial F}
  (hv_deg : ∀ i j, (v i j).degree < dstar)
  (hv_eval : ∀ i j, ∀ x ∈ S, (v i j).eval (φ x) = (φ x) ^ j.val * (fs i x))
  (i : Fin m)
  (j : Fin (block_size dstar degs i)) :
  (v i j).degree < degs i + j := by
  have hlt : dstar < Fintype.card ι := by
    by_contra contra
    have hh := lt_of_lt_of_le hδLt (min_le_right _ _)
    rw [ReedSolomon.rateOfLinearCode_eq_min_div, min_eq_right (Nat.le_of_not_gt contra)] at hh
    simp [Fintype.card_ne_zero] at hh
  rcases j with ⟨j, hj⟩
  simp only [block_size] at hj
  generalize hj': (dstar - degs i) - j = j'
  revert j
  induction j' with
  | zero =>
    intro j hj hj'
    have hd := hdegs i
    have he : degs i + j = dstar := by omega
    change (v i ⟨j,hj⟩).degree < ((degs i+j : ℕ) : WithBot ℕ)
    rw [he]
    exact hv_deg i ⟨j,hj⟩
  | succ j' ih =>
    intro j hj hj'
    have h_fin : j + 1 < dstar - degs i + 1 := by omega
    specialize ih (j + 1) h_fin (by omega)
    let q : Polynomial F := Polynomial.X * v i ⟨j, hj⟩
    have hq_deg : q.degree < dstar + 1 := by
      dsimp only [q]
      rw [Polynomial.degree_mul, Polynomial.degree_X, add_comm]
      exact (WithBot.add_lt_add_iff_right (by simp)).mpr (hv_deg i ⟨j, hj⟩)
    have hq_coincide :
      ∀ x ∈ S, q.eval (φ x) = (v i ⟨j + 1, h_fin⟩).eval (φ x) := by
      intro x hx
      simp only [q, Polynomial.eval_mul, Polynomial.eval_X, hv_eval i _ x hx, pow_succ]
      ring
    have hq_coincide :=
      Polynomial.eq_of_eval_eq_degree
        (q := v i ⟨j + 1, h_fin⟩)
        hq_deg (lt_trans (hv_deg _ _) (WithBot.coe_lt_coe.mpr (Nat.lt_succ_self dstar))) (Finset.image φ S) (by {
          simp only [Nat.cast_id, ge_iff_le, Order.add_one_le_iff]
          rw [Finset.card_image_of_injective _ φ.injective]
          have h : ↑(rate (code φ dstar)) + 1 / ↑(Fintype.card ι) < 1 - δ :=
            glorious_lemma
              (by simpa using hδLt)
              rfl
          have h :=
            le_trans
              (le_of_lt <|
                even_more_glorious_lemma (m := Fintype.card ι)
                  (by simp) (by {
                    rw [ReedSolomon.rateOfLinearCode_eq_min_div,
                        min_eq_left hlt.le] at h
                    simpa using h
                  }))
              hS_card
          norm_cast at h
        })
        (by
          intro x hx
          obtain ⟨y,hy,rfl⟩ := Finset.mem_image.mp hx
          exact hq_coincide y hy)
    simp only [q] at hq_coincide
    rw [←hq_coincide] at ih
    simp only [Polynomial.degree_mul, Polynomial.degree_X, WithBot.coe_add, WithBot.coe_one] at ih
    rw [←add_assoc, add_comm 1] at ih
    exact (WithBot.add_lt_add_iff_right (by simp)).mp ih
