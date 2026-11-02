theorem fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius (i : Fin ℓ) (steps : ℕ)
    [NeZero steps] (h_i_add_steps : i.val + steps ≤ ℓ)
    (f : OracleFunction 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩)
  (h_fw_dist_lt : fiberwiseClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate)
    (i := i) (steps := steps) (h_i_add_steps := h_i_add_steps) (f := f)) :
  hammingClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩ f := by
  let d_fw := fiberwiseDistance 𝔽q β (i := i) steps h_i_add_steps f
  let C_i := (BBF_Code 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩)
  obtain ⟨⟨g', hmem⟩, _, hg⟩ := Nat.sInf_mem (Set.univ_nonempty.image fun (g : C_i) =>
    (fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g).ncard)
  change _ = d_fw at hg
  have hΔ : hammingDist f g' ≤ d_fw * 2 ^ steps := by
    classical
    rw [← hg]
    let B := fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g'
    let decode : B × Fin (2 ^ steps) → _ := fun z => qMap_total_fiber 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩ steps
      (lt_add_of_pos_right_of_le _ _ _ h_i_add_steps) z.1 z.2
    rw [hammingDist, ← Fintype.card_subtype, ← Nat.card_eq_fintype_card]
    have hs : {x | f x ≠ g' x} ⊆ Set.range decode := by
      intro x hx
      exact ⟨(⟨_, x, rfl, hx⟩, _),
        (is_fiber_iff_generates_quotient_point 𝔽q β i steps h_i_add_steps x _).mp rfl⟩
    calc _ ≤ _ := Set.ncard_le_ncard hs
         _ ≤ _ := Finite.card_range_le decode
         _ = _ := by rw [Nat.card_prod, Nat.card_fin]; rfl
  have h3 := Nat.mul_le_mul_right (2 ^ steps) (Nat.le_of_lt_succ (WithTop.coe_lt_coe.1 h_fw_dist_lt))
  simp only [BBF_CodeDistance, Nat.add_sub_cancel, Nat.sub_mul, ← Nat.pow_add, Nat.mul_assoc,
    show ℓ + 𝓡 - (↑i + steps) + steps = ℓ + 𝓡 - i by omega,
    show ℓ - (↑i + steps) + steps = ℓ - i by omega] at h3
  exact (mul_le_mul_left' (le_trans (sInf_le ⟨g', hmem, le_rfl⟩) (ENat.coe_le_coe.2 hΔ) :
    Code.distFromCode f C_i ≤ _) 2).trans_lt (by exact_mod_cast Nat.lt_succ_of_le h3)
