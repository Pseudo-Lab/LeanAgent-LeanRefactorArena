theorem fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius (i : Fin ℓ) (steps : ℕ)
    [NeZero steps] (h_i_add_steps : i.val + steps ≤ ℓ)
    (f : OracleFunction 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩)
  (h_fw_dist_lt : fiberwiseClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate)
    (i := i) (steps := steps) (h_i_add_steps := h_i_add_steps) (f := f)) :
  hammingClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩ f := by
  classical
  have hi : i.val < r := by omega
  have his : i.val + steps < r := by omega
  have he₁ : ℓ + 𝓡 - (i.val + steps) + steps = ℓ + 𝓡 - i.val := by omega
  have he₂ : ℓ - (i.val + steps) + steps = ℓ - i.val := by omega
  let a : Fin (ℓ + 1) := ⟨i, Nat.lt_succ_of_lt i.isLt⟩
  let b : Fin (ℓ + 1) := ⟨i.val + steps, Nat.lt_succ_of_le h_i_add_steps⟩
  let C := BBF_Code 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) a
  let d := fiberwiseDistance 𝔽q β i steps h_i_add_steps f
  haveI : Nonempty C := ⟨⟨0, C.zero_mem⟩⟩
  obtain ⟨g, _, hg⟩ := Nat.sInf_mem (Set.image_nonempty.mpr
    (Set.univ_nonempty : (Set.univ : Set C).Nonempty) :
      ((fun g : C => (fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g).ncard) '' Set.univ).Nonempty)
  have hmin : d = (fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g).ncard := hg.symm
  let Y := fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g
  let Q := fun (y : sDomain 𝔽q β h_ℓ_add_R_rate ⟨i.val + steps, his⟩) =>
    (Finset.univ : Finset (Fin (2 ^ steps))).image
      (qMap_total_fiber 𝔽q β (i := ⟨i, hi⟩) (steps := steps)
        (h_i_add_steps := fin_ℓ_steps_lt_ℓ_add_R i steps h_i_add_steps) (y := y))
  have hsub : Finset.univ.filter (fun x => f x ≠ g.val x) ⊆ Y.toFinset.biUnion Q := by
    intro x hx
    have hx' := (Finset.mem_filter.mp hx).2
    let y := iteratedQuotientMap 𝔽q β h_ℓ_add_R_rate i steps h_i_add_steps x
    apply Finset.mem_biUnion.mpr
    refine ⟨y, Set.mem_toFinset.mpr ?_, ?_⟩
    · exact ⟨x, rfl, hx'⟩
    · apply Finset.mem_image.mpr
      refine ⟨pointToIterateQuotientIndex (i := a) (steps := steps)
        (h_i_add_steps := h_i_add_steps) (x := x), Finset.mem_univ _, ?_⟩
      exact (is_fiber_iff_generates_quotient_point 𝔽q β i steps h_i_add_steps (x := x) (y := y)).mp rfl
  have hdist : hammingDist f g ≤ d * 2 ^ steps := by
    rw [hmin]
    change (Finset.univ.filter (fun x => f x ≠ g.val x)).card ≤ Y.ncard * 2 ^ steps
    calc
      _ ≤ (Y.toFinset.biUnion Q).card := Finset.card_le_card hsub
      _ ≤ Y.toFinset.card * 2 ^ steps := by
        apply Finset.card_biUnion_le_card_mul
        intro y hy
        exact (Finset.card_image_le).trans_eq (Finset.card_univ.trans (Fintype.card_fin _))
      _ = Y.ncard * 2 ^ steps := by
        simp only [Set.toFinset_card]
        rw [← Nat.card_coe_set_eq]
        simp only [Nat.card_eq_fintype_card]
  have hfw : 2 * d ≤ BBF_CodeDistance ℓ 𝓡 b - 1 :=
    Nat.le_of_lt_succ (WithTop.coe_lt_coe.1 h_fw_dist_lt)
  have hid : (BBF_CodeDistance ℓ 𝓡 b - 1) * 2 ^ steps =
      BBF_CodeDistance ℓ 𝓡 a - 1 := by
    dsimp [BBF_CodeDistance, a, b]
    rw [Nat.sub_mul, ←Nat.pow_add, ←Nat.pow_add, he₁, he₂]
  have hnat : 2 * hammingDist f g < BBF_CodeDistance ℓ 𝓡 a := by
    have hle := (Nat.mul_le_mul_left 2 hdist).trans
      (by simpa only [mul_assoc] using Nat.mul_le_mul_right (2 ^ steps) hfw)
    rw [hid] at hle
    exact Nat.lt_of_le_pred (Nat.zero_lt_succ _) hle
  unfold hammingClose
  calc
    _ ≤ 2 * (hammingDist f g : ℕ∞) := by
      apply mul_le_mul_left'
      apply sInf_le
      exact ⟨g, g.property, le_rfl⟩
    _ < _ := by
      change ((2 : ℕ) : ℕ∞) * (hammingDist f g : ℕ∞) < _
      rw [← ENat.coe_mul, ENat.coe_lt_coe]
      exact hnat
