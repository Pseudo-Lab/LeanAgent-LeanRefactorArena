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
  have hΔ : hammingDist f g' ≤ d_fw * 2 ^ steps := by
    classical
    rw [← hg]
    let B := fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g'
    let q := iteratedQuotientMap 𝔽q β h_ℓ_add_R_rate i steps h_i_add_steps
    let idx := pointToIterateQuotientIndex 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩ steps h_i_add_steps
    let decode := qMap_total_fiber 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩ steps
      (lt_add_of_pos_right_of_le _ _ _ h_i_add_steps)
    have hd x : decode (q x) (idx x) = x :=
      (is_fiber_iff_generates_quotient_point 𝔽q β i steps h_i_add_steps x _).mp rfl
    change hammingDist f g' ≤ Nat.card B * 2 ^ steps
    rw [hammingDist, ← Fintype.card_subtype, ← Nat.card_eq_fintype_card,
      ← Nat.card_fin (2 ^ steps), ← Nat.card_prod]
    refine Nat.card_le_card_of_injective (fun x => (⟨q x, x, rfl, x.2⟩, idx x)) ?_
    intro x y h
    apply Subtype.ext
    simpa only [hd] using congrArg (fun z : B × Fin (2 ^ steps) => decode z.1 z.2) h
  have h3 := Nat.mul_le_mul_right (2 ^ steps) (Nat.le_of_lt_succ (WithTop.coe_lt_coe.1 h_fw_dist_lt))
  simp only [BBF_CodeDistance, Nat.add_sub_cancel, Nat.sub_mul, ← Nat.pow_add, Nat.mul_assoc,
    show ℓ + 𝓡 - (↑i + steps) + steps = ℓ + 𝓡 - i by omega,
    show ℓ - (↑i + steps) + steps = ℓ - i by omega] at h3
  exact (mul_le_mul_left' (le_trans (sInf_le ⟨g', hmem, le_rfl⟩) (ENat.coe_le_coe.2 hΔ) :
    Code.distFromCode f C_i ≤ _) 2).trans_lt (WithTop.coe_lt_coe.2 (Nat.lt_succ_of_le h3))
