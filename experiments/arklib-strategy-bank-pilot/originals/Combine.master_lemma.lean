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
    aesop
      (add simp [ReedSolomon.rateOfLinearCode_eq_min_div, min_eq_right])
  rcases j with ⟨j, hj⟩
  simp only [block_size] at hj
  simp only [gt_iff_lt]
  generalize hj': (dstar - degs i) - j = j'
  revert j
  induction j' with
  | zero =>
    intro j hj hj'
    conv_rhs =>
      rw [show j = (dstar - degs i) by omega]
    rw [←WithBot.coe_natCast,
        show WithBot.some (dstar - degs i) = Nat.cast (dstar - degs i) by rfl,
        ←WithBot.coe_natCast, ←WithBot.coe_add, ←Nat.cast_add,
        Nat.add_sub_of_le (hdegs _)]
    exact hv_deg i ⟨j, hj⟩
  | succ j' ih =>
    intro j hj hj'
    have hj' : j = dstar - degs i - j' - 1 := by omega
    have h_fin : j + 1 < dstar - degs i + 1 := by omega
    specialize ih (j + 1) h_fin (by omega)
    let q : Polynomial F := Polynomial.X * v i ⟨j, hj⟩
    have hq_deg : q.degree < dstar + 1 := by
      rw [WithBot.lt_def]
      by_cases hv: v i ⟨j, hj⟩ = 0
      · aesop
      · right
        simp only [Polynomial.degree_mul, Polynomial.degree_X, q]
        rw [Polynomial.degree_eq_natDegree hv]
        exists (1 + (v i ⟨j ,hj⟩).natDegree)
        aesop
          (add unsafe (by rw [add_comm]))
          (add unsafe forward [Nat.add_lt_add_right])
          (add simp [Polynomial.natDegree_lt_iff_degree_lt])
    have hq_coincide :
      ∀ x ∈ S, q.eval (φ x) = (v i ⟨j + 1, h_fin⟩).eval (φ x) := by
      aesop
        (add simp [q])
        (add safe (by ring_nf))
    have hq_coincide :=
      Polynomial.eq_of_eval_eq_degree
        (q := v i ⟨j + 1, h_fin⟩)
        hq_deg (lt_trans (hv_deg _ _) <| by
          rw [WithBot.lt_def]
          right
          exists dstar, (dstar + 1)
          aesop
        ) (Finset.image φ S) (by {
          simp only [Nat.cast_id, ge_iff_le, Order.add_one_le_iff]
          rw [Finset.card_image_of_injective _ (fun x y hxy ↦ by aesop)]
          have h : ↑(rate (code φ dstar)) + 1 / ↑(Fintype.card ι) < 1 - δ :=
            glorious_lemma
              (by simpa using hδLt)
              (by {
                simp only [rate]
                rfl
              })
          have h :=
            le_trans
              (le_of_lt <|
                even_more_glorious_lemma (m := Fintype.card ι)
                  (by simp) (by {
                    rw [ReedSolomon.rateOfLinearCode_eq_min_div,
                        min_eq_left (by omega)] at h
                    simpa using h
                  }))
              hS_card
          norm_cast at h
        })
        (by aesop)
    simp only [q] at hq_coincide
    rw [←hq_coincide] at ih
    simp only [Polynomial.degree_mul, Polynomial.degree_X, WithBot.coe_add, WithBot.coe_one] at ih
    rw [←add_assoc, add_comm 1] at ih
    exact (WithBot.add_lt_add_iff_right (by simp)).mp ih