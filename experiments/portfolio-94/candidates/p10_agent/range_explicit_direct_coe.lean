theorem fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius (i : Fin ℓ) (steps : ℕ)
    [NeZero steps] (h_i_add_steps : i.val + steps ≤ ℓ)
    (f : OracleFunction 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩)
  (h_fw_dist_lt : fiberwiseClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate)
    (i := i) (steps := steps) (h_i_add_steps := h_i_add_steps) (f := f)) :
  hammingClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩ f := by
  let d_fw := fiberwiseDistance 𝔽q β (i := i) steps h_i_add_steps f
  obtain ⟨⟨g', hmem⟩, _, hg⟩ : d_fw ∈ (_ : Set ℕ) :=
    Nat.sInf_mem (Set.univ_nonempty.image _)
  have hΔ : hammingDist f g' ≤ d_fw * 2 ^ steps := by
    let B := fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g'
    rw [hammingDist, ← Fintype.card_subtype, ← Nat.card_eq_fintype_card]
    have hs : {x | f x ≠ g' x} ⊆ Set.range (fun z : B × Fin (2 ^ steps) => qMap_total_fiber 𝔽q β ⟨i, i.isLt.trans (Nat.lt_of_add_right_lt h_ℓ_add_R_rate)⟩ steps (lt_add_of_pos_right_of_le _ _ _ h_i_add_steps) z.1 z.2) := by
      intro x hx
      exact ⟨(⟨_, x, rfl, hx⟩, _),
        (is_fiber_iff_generates_quotient_point 𝔽q β i steps h_i_add_steps x _).mp rfl⟩
    calc _ ≤ _ := Set.ncard_le_ncard hs
         _ ≤ _ := Finite.card_range_le _
         _ = _ := by rw [Nat.card_prod, Nat.card_fin, show Nat.card B = d_fw from hg]
  have h3 := Nat.mul_le_mul_right (2 ^ steps) (Nat.le_of_lt_succ (WithTop.coe_lt_coe.1 h_fw_dist_lt))
  simp (disch := omega) only [Nat.sub_mul, ← Nat.pow_add, Nat.mul_assoc,
    ← Nat.sub_add_comm, Nat.add_sub_add_right] at h3
  exact (mul_le_mul_left' ((distFromCode_le_dist_to_mem f g' hmem).trans
    (ENat.coe_le_coe.2 hΔ)) 2).trans_lt (ENat.coe_lt_coe.2 (Nat.lt_succ_of_le h3))
