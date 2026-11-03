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
    by_contra! hn
    have hh := (lt_min_iff.mp hδLt).2
    simp [ReedSolomon.rateOfLinearCode_eq_min_div, min_eq_right hn] at hh
  have hcard : dstar + 1 ≤ (Finset.image φ S).card := by
    rw [Finset.card_image_of_injective _ φ.injective]
    have h : ↑(rate (code φ dstar)) + 1 / ↑(Fintype.card ι) < 1 - δ :=
      glorious_lemma (by simpa using hδLt) (by simp only [rate]; rfl)
    rw [ReedSolomon.rateOfLinearCode_eq_min_div, min_eq_left hlt.le] at h
    exact_mod_cast (even_more_glorious_lemma (m := Fintype.card ι) (by simp) (by simpa using h)).le.trans hS_card
  rcases j with ⟨j, hj⟩
  simp only [block_size] at hj
  generalize he : dstar - degs i - j = k
  revert j
  induction k with
  | zero =>
    intro j hj he
    have h : degs i + j = dstar := by have := hdegs i; omega
    change (v i ⟨j, hj⟩).degree < ((degs i + j : ℕ) : WithBot ℕ)
    rw [h]
    exact hv_deg i ⟨j, hj⟩
  | succ k ih =>
    intro j hj he
    have hj1 : j + 1 < dstar - degs i + 1 := by omega
    specialize ih (j + 1) hj1 (by omega)
    have hp : v i ⟨j, hj⟩ * Polynomial.X = v i ⟨j + 1, hj1⟩ := by
      apply Polynomial.eq_of_eval_eq_degree (n := dstar + 1)
      · rw [Polynomial.degree_mul, Polynomial.degree_X, WithBot.coe_add, WithBot.coe_one]
        exact (WithBot.add_lt_add_iff_right (by simp : (1 : WithBot ℕ) ≠ ⊥)).2 (hv_deg i ⟨j, hj⟩)
      · exact lt_trans (hv_deg _ _) (WithBot.coe_lt_coe.mpr (Nat.lt_succ_self dstar))
      · exact hcard
      · intro y hy
        obtain ⟨x, hx, rfl⟩ := Finset.mem_image.mp hy
        simp only [Polynomial.eval_mul, Polynomial.eval_X, hv_eval _ _ x hx, pow_succ]
        ring
    rw [←hp] at ih
    simp only [Polynomial.degree_mul, Polynomial.degree_X, WithBot.coe_add, WithBot.coe_one, ←add_assoc] at ih
    exact (WithBot.add_lt_add_iff_right (by simp)).mp ih
